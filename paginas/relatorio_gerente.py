"""Relatório por Gerente: uma linha por gerente no mês (vendas da equipe e a
verba dele), mais uma linha "(sem gerente)" para cada loja sem gerente.

O TOTAL soma as vendas dos COLABORADORES do grupo (sem dupla contagem: dois
gerentes da mesma loja dividem a mesma equipe) e o A RECEBER dos gerentes.
"""

import pandas as pd
import streamlit as st

import db
from paginas.comum import (F_INT, F_MOEDA, F_PCT, agg_por, agg_total, aviso_preco, botao_excel,
                           colaboradores, erro_banco, excel_abas, fmt_int, fmt_money, fmt_pct,
                           label_mes)
from tecar.config import ConfigInvalida, carregar_cargos, chave

COLUNAS = [  # (título, chave, formato tela, formato Excel)
    ("Seq", "seq", str, F_INT), ("Gerente", "gerente", str, None), ("Cargo", "cargo", str, None),
    ("Loja", "loja", str, None), ("Marca", "marca", str, None), ("Equipe", "equipe", str, None),
    ("Passagens", "passagens", fmt_int, F_INT), ("Vendas equipe", "vendas", fmt_int, F_INT),
    ("% Aprov", "aprov", fmt_pct, F_PCT), ("Total Diant.", "total_diant", fmt_money, F_MOEDA),
    ("Refil Tras.", "refil_tras", fmt_int, F_INT), ("Total Geral", "total_geral", fmt_money, F_MOEDA),
    ("Part %", "part", fmt_pct, F_PCT), ("Verba (R$/venda)", "verba", fmt_money, F_MOEDA),
    ("A Receber", "a_receber", fmt_money, F_MOEDA),
]
NAN = float("nan")


def _equipes():
    try:
        return {k: ", ".join(c.equipe) for k, c in carregar_cargos().items()}
    except ConfigInvalida:
        return {}


def montar(df_mes: pd.DataFrame, ordenar: str = "Vendas da equipe"):
    """(linhas, total) do mês. Cada linha é um dict com as chaves de COLUNAS."""
    colab = colaboradores(df_mes)
    ger = df_mes[df_mes["grupo"] == "gerente"]
    total_vendas = colab["refil_diant"].sum()
    equipes = _equipes()
    linhas = []
    for r in ger.itertuples():
        linhas.append({"gerente": r.pessoa, "cargo": r.cargo, "loja": r.loja, "marca": r.marca,
                       "equipe": equipes.get(chave(r.cargo), "—"), "passagens": r.passagens,
                       "vendas": r.refil_diant, "aprov": NAN, "total_diant": r.total_diant,
                       "refil_tras": r.refil_tras, "total_geral": r.total_geral,
                       "part": r.refil_diant / total_vendas if total_vendas else NAN,
                       "verba": r.verba, "a_receber": r.a_receber})
    com_gerente = set(ger["loja"])
    for loja, g in colab.groupby("loja"):
        if loja in com_gerente:
            continue
        a = agg_total(g)
        linhas.append({"gerente": "(sem gerente)", "cargo": "—", "loja": loja,
                       "marca": g["marca"].iloc[0], "equipe": "toda a loja",
                       "passagens": a["passagens"], "vendas": a["refil_diant"],
                       "aprov": a["aproveitamento"], "total_diant": a["total_diant"],
                       "refil_tras": a["refil_tras"], "total_geral": a["total_geral"],
                       "part": a["refil_diant"] / total_vendas if total_vendas else NAN,
                       "verba": NAN, "a_receber": NAN})
    col = "vendas" if ordenar == "Vendas da equipe" else "a_receber"
    linhas.sort(key=lambda x: (-(x[col] if pd.notna(x[col]) else -1), x["loja"], x["gerente"]))
    for i, x in enumerate(linhas, 1):
        x["seq"] = str(i)
    t = agg_total(colab) if not colab.empty else None
    total = {"seq": "", "gerente": "TOTAL", "cargo": "", "loja": "", "marca": "", "equipe": "",
             "passagens": t["passagens"] if t is not None else NAN, "vendas": total_vendas,
             "aprov": t["aproveitamento"] if t is not None else NAN,
             "total_diant": t["total_diant"] if t is not None else NAN,
             "refil_tras": t["refil_tras"] if t is not None else NAN,
             "total_geral": t["total_geral"] if t is not None else NAN,
             "part": 1.0 if total_vendas else NAN, "verba": NAN,
             "a_receber": ger["a_receber"].sum()}
    return linhas, total


def gerar_excel(linhas, total, mes_lbl, ordenar) -> bytes:
    return excel_abas([{
        "nome": "Relatório por Gerente", "titulo": f"Resultado por Gerente — Grupo TECAR {mes_lbl}",
        "subtitulo": f"Ordenado por {ordenar}",
        "cabecalho": [c[0] for c in COLUNAS],
        "linhas": [[x[c[1]] if c[1] != "seq" else (int(x["seq"]) if x["seq"] else "")
                    for c in COLUNAS] for x in linhas + [total]],
        "formatos": [c[3] for c in COLUNAS], "total": True,
        "larguras": [5, 32, 18, 20, 14, 26, 10, 12, 8, 14, 10, 14, 8, 14, 13]}])


def pagina():
    st.title("📅 Relatório por Gerente")
    st.caption("Gerentes do mês com as vendas da equipe e a verba de cada um.")
    try:
        base = db.ler_base()
    except Exception:
        erro_banco()
        return
    if base.empty:
        st.info("Ainda não há dados no banco.")
        return
    meses = sorted(base["mes"].unique(), reverse=True)
    por_rotulo = {label_mes(m): m for m in meses}
    c1, c2 = st.columns([2, 1])
    mes_lbl = c1.selectbox("Mês", list(por_rotulo))
    ordenar = c2.radio("Ordenar por", ["Vendas da equipe", "A Receber"], horizontal=True)
    df_mes = base[base["mes"] == por_rotulo[mes_lbl]]
    linhas, total = montar(df_mes, ordenar)

    k = st.columns(4)
    k[0].metric("Vendas (colaboradores)", fmt_int(total["vendas"]))
    k[1].metric("Gerentes", fmt_int(sum(1 for x in linhas if x["gerente"] != "(sem gerente)")))
    k[2].metric("A receber — gerentes", fmt_money(total["a_receber"]))
    k[3].metric("Faturamento total", fmt_money(total["total_geral"]))

    _, cexp = st.columns([3, 1])
    with cexp:
        botao_excel("📥 Exportar relatório (Excel)", gerar_excel(linhas, total, mes_lbl, ordenar),
                    f"Relatorio_Gerente_TECAR_{pd.Timestamp(por_rotulo[mes_lbl]):%Y-%m}.xlsx")
    tela = pd.DataFrame([{c[0]: c[2](x[c[1]]) if c[2] is not str else str(x[c[1]])
                          for c in COLUNAS} for x in linhas + [total]])
    st.dataframe(tela, width="stretch", hide_index=True)
    st.caption("Vendas equipe = soma das vendas da equipe do gerente (Gerente Peças e Pós "
               "Vendas: Consultores e Vendedores de Peças; Chefe de oficina: Técnicos). "
               "TOTAL de vendas = colaboradores do grupo, sem contar duas vezes a mesma "
               "equipe; TOTAL A Receber = verba dos gerentes. Part % = participação nas vendas "
               "do grupo.")
    aviso_preco(df_mes)
