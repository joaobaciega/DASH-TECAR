"""Relatório por Colaborador: ranking do mês (Consultores, Vendedores de Peças
e Técnicos juntos, cada um com o seu cargo), com a verba de cada um."""

import pandas as pd
import streamlit as st

import db
from paginas.comum import (F_INT, F_MOEDA, F_PCT, agg_por, agg_total, aviso_preco, botao_excel,
                           colaboradores, erro_banco, excel_abas, fmt_int, fmt_money, fmt_pct,
                           label_mes)

COLUNAS = [  # (título, chave, formato tela, formato Excel)
    ("Seq", "seq", str, F_INT), ("Colaborador", "pessoa", str, None),
    ("Cargo", "cargo", str, None), ("Loja", "loja", str, None),
    ("Passagens", "passagens", fmt_int, F_INT), ("Refil Diant.", "refil_diant", fmt_int, F_INT),
    ("% Aprov (D)", "aproveitamento", fmt_pct, F_PCT),
    ("Total Diant.", "total_diant", fmt_money, F_MOEDA),
    ("Refil Tras.", "refil_tras", fmt_int, F_INT),
    ("% Aprov (T)", "aproveitamento_tras", fmt_pct, F_PCT),
    ("Total Tras.", "total_tras", fmt_money, F_MOEDA),
    ("Total Geral", "total_geral", fmt_money, F_MOEDA), ("Part %", "part", fmt_pct, F_PCT),
    ("Verba (R$/venda)", "verba", fmt_money, F_MOEDA),
    ("A Receber", "a_receber", fmt_money, F_MOEDA),
]
ORDEM = {"Vendas": "refil_diant", "A Receber": "a_receber", "Faturamento": "total_geral"}


def montar(df_mes: pd.DataFrame, ordenar: str = "Vendas"):
    g = agg_por(df_mes, ["pessoa_id", "pessoa", "cargo", "loja"])
    g = g.merge(df_mes.groupby("pessoa_id", as_index=False)["verba"].max(), on="pessoa_id")
    tot_v = g["refil_diant"].sum()
    g["part"] = g["refil_diant"] / tot_v if tot_v else float("nan")
    g = g.sort_values([ORDEM[ordenar], "pessoa"], ascending=[False, True], na_position="last")
    linhas = g.to_dict("records")
    for i, x in enumerate(linhas, 1):
        x["seq"] = str(i)
    t = agg_total(df_mes)
    total = {**t.to_dict(), "seq": "", "pessoa": "TOTAL", "cargo": "", "loja": "",
             "part": 1.0 if tot_v else float("nan"), "verba": float("nan")}
    return linhas, total


def gerar_excel(linhas, total, mes_lbl, filtros_txt) -> bytes:
    return excel_abas([{
        "nome": "Relatório Colaborador",
        "titulo": f"Resultado por Colaborador — Grupo TECAR {mes_lbl}",
        "subtitulo": f"Filtros: {filtros_txt}", "cabecalho": [c[0] for c in COLUNAS],
        "linhas": [[x[c[1]] if c[1] != "seq" else (int(x["seq"]) if x["seq"] else "")
                    for c in COLUNAS] for x in linhas + [total]],
        "formatos": [c[3] for c in COLUNAS], "total": True,
        "larguras": [5, 34, 18, 20, 10, 11, 10, 14, 10, 10, 13, 14, 8, 14, 13]}])


def pagina():
    st.title("🧑‍💼 Relatório por Colaborador")
    st.caption("Ranking dos colaboradores no mês, com a verba de cada um.")
    try:
        base = db.ler_base()
    except Exception:
        erro_banco()
        return
    df = colaboradores(base) if not base.empty else base
    if df.empty:
        st.info("Ainda não há dados no banco.")
        return
    meses = sorted(df["mes"].unique(), reverse=True)
    por_rotulo = {label_mes(m): m for m in meses}
    TODAS = "Todas as lojas"
    c1, c2, c3, c4 = st.columns([1.4, 1.4, 1.6, 1.6])
    mes_lbl = c1.selectbox("Mês", list(por_rotulo))
    loja = c2.selectbox("Loja", [TODAS] + sorted(df["loja"].unique()))
    cargos = c3.multiselect("Cargo", sorted(df["cargo"].unique()), key="cargo_colab",
                            placeholder="Todos")
    ordenar = c4.radio("Ordenar por", list(ORDEM), horizontal=True)

    f = df[df["mes"] == por_rotulo[mes_lbl]]
    if loja != TODAS:
        f = f[f["loja"] == loja]
    if cargos:
        f = f[f["cargo"].isin(cargos)]
    if f.empty:
        st.warning("Sem dados para estes filtros neste mês.")
        return
    linhas, total = montar(f, ordenar)

    k = st.columns(4)
    k[0].metric("Refil Diant. (vendas)", fmt_int(total["refil_diant"]))
    k[1].metric("Colaboradores", fmt_int(len(linhas)))
    k[2].metric("A receber", fmt_money(total["a_receber"]))
    k[3].metric("Faturamento total", fmt_money(total["total_geral"]))

    filtros_txt = " · ".join(p for p in (loja if loja != TODAS else "",
                                         ("Cargos: " + ", ".join(cargos)) if cargos else "") if p) \
        or "Todos"
    _, cexp = st.columns([3, 1])
    with cexp:
        botao_excel("📥 Exportar relatório (Excel)", gerar_excel(linhas, total, mes_lbl, filtros_txt),
                    f"Relatorio_Colaborador_TECAR_{pd.Timestamp(por_rotulo[mes_lbl]):%Y-%m}.xlsx")
    tela = pd.DataFrame([{c[0]: c[2](x[c[1]]) if c[2] is not str else str(x[c[1]])
                          for c in COLUNAS} for x in linhas + [total]])
    st.dataframe(tela, width="stretch", hide_index=True)
    st.caption("Verba = R$ por venda, da planilha de verbas; A Receber = Verba × vendas. "
               "Part % = participação do colaborador nas vendas do recorte.")
    aviso_preco(f)
