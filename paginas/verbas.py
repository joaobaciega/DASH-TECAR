"""Verbas: quanto cada pessoa tem A RECEBER (VERBA × VENDAS), por loja e por mês.

A verba dos gerentes entra no total de verbas; as vendas deles não entram no
total de vendas (repetem as da equipe).
"""

import pandas as pd
import plotly.express as px
import streamlit as st

import db
from paginas.comum import (F_INT, F_MOEDA, MESES_PT, botao_excel, erro_banco, excel_abas,
                           fmt_int, fmt_money, label_mes, layout_grafico, mlabel)


def _resumo(df: pd.DataFrame, por) -> pd.DataFrame:
    colab = df["grupo"] == "colaborador"
    t = pd.DataFrame({
        "vendas": df["refil_diant"].where(colab, 0),
        "colab": df["a_receber"].where(colab, 0),
        "ger": df["a_receber"].where(~colab, 0),
    })
    t[por] = df[por]
    g = t.groupby(por, as_index=False).sum()
    g["total"] = g["colab"] + g["ger"]
    return g


def tabela_por_loja(df: pd.DataFrame) -> pd.DataFrame:
    return _resumo(df, "loja").sort_values("loja")


def tabela_mensal(df: pd.DataFrame) -> pd.DataFrame:
    return _resumo(df, "mes").sort_values("mes")


def tabela_pessoas(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["mes", "loja", "grupo", "pessoa"], ascending=[True, True, False, True])[
        ["pessoa", "cargo", "grupo", "loja", "mes", "verba", "refil_diant", "a_receber"]]


def gerar_excel(periodo, por_loja, mensal, pessoas) -> bytes:
    def com_total(t, rotulo_col):
        linhas = [[r[rotulo_col], r["vendas"], r["colab"], r["ger"], r["total"]]
                  for _, r in t.iterrows()]
        linhas.append(["TOTAL", t["vendas"].sum(), t["colab"].sum(), t["ger"].sum(),
                       t["total"].sum()])
        return linhas

    cab = ["Vendas (sem gerentes)", "A receber colaboradores", "A receber gerentes",
           "Total a receber"]
    fmts = [None, F_INT, F_MOEDA, F_MOEDA, F_MOEDA]
    mensal = mensal.assign(rotulo=mensal["mes"].apply(label_mes))
    return excel_abas([
        {"nome": "Por loja", "titulo": "Verbas por loja — Grupo TECAR", "subtitulo": periodo,
         "cabecalho": ["Loja"] + cab, "linhas": com_total(por_loja, "loja"), "total": True,
         "formatos": fmts, "larguras": [24, 14, 18, 16, 16]},
        {"nome": "Mês a mês", "titulo": "Verbas mês a mês — Grupo TECAR", "subtitulo": periodo,
         "cabecalho": ["Mês"] + cab, "linhas": com_total(mensal, "rotulo"), "total": True,
         "formatos": fmts, "larguras": [18, 14, 18, 16, 16]},
        {"nome": "Por pessoa", "titulo": "Verbas por pessoa — Grupo TECAR", "subtitulo": periodo,
         "cabecalho": ["Nome", "Cargo", "Grupo", "Loja", "Mês", "Verba (R$/venda)", "Vendas",
                       "A Receber (R$)"],
         "linhas": [[r.pessoa, r.cargo, r.grupo.title(), r.loja, mlabel(r.mes), r.verba,
                     r.refil_diant, r.a_receber] for r in pessoas.itertuples()],
         "formatos": [None, None, None, None, None, F_MOEDA, F_INT, F_MOEDA],
         "larguras": [34, 18, 12, 20, 10, 15, 9, 14]},
    ])


def _tela(t, rotulo_col, titulo):
    linhas = [{titulo: r[rotulo_col], "Vendas (sem gerentes)": fmt_int(r["vendas"]),
               "A receber colaboradores": fmt_money(r["colab"]),
               "A receber gerentes": fmt_money(r["ger"]), "Total a receber": fmt_money(r["total"])}
              for _, r in t.iterrows()]
    linhas.append({titulo: "TOTAL", "Vendas (sem gerentes)": fmt_int(t["vendas"].sum()),
                   "A receber colaboradores": fmt_money(t["colab"].sum()),
                   "A receber gerentes": fmt_money(t["ger"].sum()),
                   "Total a receber": fmt_money(t["total"].sum())})
    st.dataframe(pd.DataFrame(linhas), width="stretch", hide_index=True)


def pagina():
    st.title("💰 Verbas")
    try:
        base = db.ler_base()
    except Exception:
        erro_banco()
        return
    if base.empty:
        st.info("As informações de verbas ainda não estão disponíveis.")
        return

    ca, cm, cl = st.columns([1, 1.5, 2.5])
    ano = ca.selectbox("Ano", sorted(base["mes"].dt.year.unique(), reverse=True))
    do_ano = base[base["mes"].dt.year == ano]
    meses = sorted(do_ano["mes"].unique(), reverse=True)
    escolha = cm.selectbox("📅 Mês", ["Ano todo"] + [MESES_PT[pd.Timestamp(m).month] for m in meses])
    lojas = cl.multiselect("Loja", sorted(do_ano["loja"].unique()), key="loja_verbas",
                           placeholder="Todas")
    if lojas:
        do_ano = do_ano[do_ano["loja"].isin(lojas)]
    periodo_df = do_ano if escolha == "Ano todo" else \
        do_ano[do_ano["mes"].dt.month == MESES_PT.index(escolha)]
    periodo = str(ano) if escolha == "Ano todo" else f"{escolha}/{ano}"
    if periodo_df.empty:
        st.warning("Sem dados para estes filtros.")
        return
    st.caption(f"Período: {periodo}" + (f" · Lojas: {', '.join(lojas)}" if lojas else "")
               + " · A RECEBER = VERBA (R$ por venda) × VENDAS, como nas planilhas de verbas.")

    loja_t = tabela_por_loja(periodo_df)
    st.subheader(f"A receber — {periodo}")
    c = st.columns(4)
    c[0].metric("A receber — Colaboradores", fmt_money(loja_t["colab"].sum()))
    c[1].metric("A receber — Gerentes", fmt_money(loja_t["ger"].sum()))
    c[2].metric("Total a receber", fmt_money(loja_t["total"].sum()))
    c[3].metric("Vendas (refis)", fmt_int(loja_t["vendas"].sum()),
                help="Vendas dos colaboradores. As vendas dos gerentes são a soma da equipe "
                     "e não entram de novo.")

    mensal_t = tabela_mensal(do_ano)
    pessoas_t = tabela_pessoas(periodo_df)
    _, cexp = st.columns([3, 1])
    with cexp:
        botao_excel("📥 Exportar relatório (Excel)",
                    gerar_excel(periodo, loja_t, mensal_t, pessoas_t),
                    f"Verbas_TECAR_{periodo.replace('/', '-')}.xlsx")

    st.subheader("Por loja")
    _tela(loja_t, "loja", "Loja")

    st.subheader(f"Mês a mês — {ano}")
    _tela(mensal_t.assign(rotulo=mensal_t["mes"].apply(label_mes)), "rotulo", "Mês")

    st.subheader("A receber mês a mês")
    graf = mensal_t.assign(Mês=mensal_t["mes"].apply(mlabel)).rename(
        columns={"colab": "Colaboradores", "ger": "Gerentes"})
    fig = px.bar(graf, x="Mês", y=["Colaboradores", "Gerentes"], barmode="group",
                 color_discrete_sequence=["#000000", "#9E9E9E"])
    layout_grafico(fig, altura=320)
    fig.update_yaxes(tickprefix="R$ ")
    fig.update_traces(hovertemplate="%{x}<br>R$ %{y:,.2f}<extra>%{fullData.name}</extra>")
    st.plotly_chart(fig, width="stretch")

    st.subheader(f"Por pessoa — {periodo}")
    st.dataframe(pd.DataFrame({
        "Nome": pessoas_t["pessoa"], "Cargo": pessoas_t["cargo"],
        "Grupo": pessoas_t["grupo"].str.title(), "Loja": pessoas_t["loja"],
        "Mês": pessoas_t["mes"].apply(mlabel),
        "Verba (R$/venda)": pessoas_t["verba"].map(fmt_money),
        "Vendas": pessoas_t["refil_diant"].map(fmt_int),
        "A Receber": pessoas_t["a_receber"].map(fmt_money)}), width="stretch", hide_index=True)
    st.caption("Para gerentes, Vendas = soma das vendas da equipe (não entra no total de vendas).")
