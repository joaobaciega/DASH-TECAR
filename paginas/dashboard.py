"""Dashboard: trimestre móvel por colaborador, loja e marca (disposição do Dahruj).

Só colaboradores: as vendas dos gerentes repetem as da equipe e não entram nos
totais. Passagens e aproveitamento aparecem como "—" (a TECAR não envia).
"""

import datetime as dt

import pandas as pd
import plotly.express as px
import streamlit as st

import db
from paginas.comum import (PALETA, PRETO, F_INT, F_MOEDA, F_PCT, agg_por, agg_total,
                           aviso_preco, botao_excel, colaboradores, delta_str, erro_banco,
                           excel_abas, fmt_int, fmt_money, fmt_pct, layout_grafico, mlabel)

N_MESES = 3


def janela(df, mes_fim, n=N_MESES):
    """Os n meses que terminam em mes_fim (trimestre móvel)."""
    meses = sorted(df["mes"].unique())
    i = meses.index(mes_fim) if mes_fim in meses else len(meses) - 1
    keep = meses[max(0, i - n + 1): i + 1]
    return df[df["mes"].isin(keep)].copy(), keep


def gerar_excel_ranking(f, periodo, filtros_txt) -> bytes:
    rk = agg_por(f, ["pessoa_id", "pessoa", "cargo", "loja", "marca"]) \
        .sort_values(["refil_diant", "pessoa"], ascending=[False, True])
    tot = agg_total(f)
    linhas = [[i, r.pessoa, r.cargo, r.loja, r.marca, r.passagens, r.refil_diant,
               r.aproveitamento, r.refil_tras, r.total_geral, r.a_receber]
              for i, r in enumerate(rk.itertuples(), 1)]
    linhas.append(["", "TOTAL", "", "", "", tot["passagens"], tot["refil_diant"],
                   tot["aproveitamento"], tot["refil_tras"], tot["total_geral"], tot["a_receber"]])
    mensal = agg_por(f, "mes").sort_values("mes")
    return excel_abas([
        {"nome": "Ranking Trimestre", "titulo": "Ranking Refis para Palhetas — Grupo TECAR",
         "subtitulo": f"Período: {periodo} · Filtros: {filtros_txt}",
         "cabecalho": ["#", "Colaborador", "Cargo", "Loja", "Marca", "Passagens",
                       "Refil Diant.", "Aprov. Diant.", "Refil Tras.", "Faturamento (R$)",
                       "A Receber (R$)"],
         "linhas": linhas, "total": True,
         "formatos": [F_INT, None, None, None, None, F_INT, F_INT, F_PCT, F_INT, F_MOEDA, F_MOEDA],
         "larguras": [5, 34, 18, 20, 14, 11, 12, 12, 11, 16, 15]},
        {"nome": "Resumo Mensal", "titulo": "Resumo mensal", "subtitulo": f"Filtros: {filtros_txt}",
         "cabecalho": ["Mês", "Passagens", "Refil Diant.", "Aprov. Diant.", "Refil Tras.",
                       "Fat. Diant. (R$)", "Fat. Tras. (R$)", "Fat. Total (R$)", "A Receber (R$)"],
         "linhas": [[mlabel(r.mes), r.passagens, r.refil_diant, r.aproveitamento, r.refil_tras,
                     r.total_diant, r.total_tras, r.total_geral, r.a_receber]
                    for r in mensal.itertuples()],
         "formatos": [None, F_INT, F_INT, F_PCT, F_INT, F_MOEDA, F_MOEDA, F_MOEDA, F_MOEDA],
         "larguras": [12, 11, 12, 12, 11, 15, 15, 15, 15]},
    ])


def _linha(dfp, ycol, titulo, hover, cor, ordem):
    if dfp[ycol].isna().all():
        st.caption(f"**{titulo}** — sem dados no período"
                   + (" (a TECAR não envia passagens)." if ycol in ("passagens", "aproveitamento")
                      else " (loja sem preço)." if ycol == "total_geral" else "."))
        return
    fig = px.line(dfp, x="mes_lbl", y=ycol, color=cor, markers=True,
                  color_discrete_sequence=PALETA, category_orders={"mes_lbl": ordem})
    fig.update_traces(hovertemplate="%{x}<br>" + hover + "<extra>%{fullData.name}</extra>")
    layout_grafico(fig, titulo=titulo)
    fig.update_yaxes(rangemode="tozero", tickformat=".0%" if ycol == "aproveitamento" else None)
    st.plotly_chart(fig, width="stretch")


def _barras(dados, xcol, ycol, texto, hover, xfmt, titulo_x):
    fig = px.bar(dados, x=xcol, y=ycol, orientation="h", color_discrete_sequence=[PRETO],
                 text=texto)
    fig.update_traces(hovertemplate=hover, textposition="outside", cliponaxis=False)
    layout_grafico(fig, altura=max(320, 28 * len(dados)))
    fig.update_layout(xaxis_title=titulo_x)
    if xfmt:
        fig.update_xaxes(tickformat=xfmt)
    st.plotly_chart(fig, width="stretch")


METRICAS = {  # rótulo: (coluna, formato do texto, hover, tickformat)
    "Nº Refil Dianteiro": ("refil_diant", fmt_int, "%{x:,.0f}<extra></extra>", None),
    "Faturamento (R$)": ("total_geral", fmt_money, "R$ %{x:,.2f}<extra></extra>", None),
    "Aproveitamento": ("aproveitamento", fmt_pct, "%{x:.1%}<extra></extra>", ".0%"),
    "Passagens": ("passagens", fmt_int, "%{x:,.0f}<extra></extra>", None),
}


def pagina():
    st.title("📊 Análise de Vendas — Grupo TECAR")
    try:
        base = db.ler_base()
    except Exception:
        erro_banco()
        return
    df = colaboradores(base) if not base.empty else base
    if df.empty:
        st.info("Ainda não há dados no banco. Rode a atualização mensal (atualizar.py).")
        return

    meses = sorted(df["mes"].dropna().unique())
    por_rotulo = {mlabel(m): m for m in meses}
    csel, _ = st.columns([2, 3])
    mes_lbl = csel.selectbox("📅 Mês de referência", [mlabel(m) for m in reversed(meses)],
                             help="KPIs do mês escolhido; gráficos do trimestre móvel "
                                  "encerrado nele.")
    mes_sel = por_rotulo[mes_lbl]
    win, keep = janela(df, mes_sel)
    ordem = [mlabel(m) for m in sorted(keep)]
    periodo = " · ".join(ordem)
    st.caption(f"Acompanhamento trimestral móvel · {periodo}")

    # ---- filtros (barra lateral)
    st.sidebar.header("Filtros")
    st.sidebar.caption(f"Trimestre vigente: **{periodo}**")
    sel_marca = st.sidebar.multiselect("Marca", sorted(win["marca"].unique()), placeholder="Todas")
    b = win[win["marca"].isin(sel_marca)] if sel_marca else win
    sel_loja = st.sidebar.multiselect("Loja", sorted(b["loja"].unique()), placeholder="Todas")
    b = b[b["loja"].isin(sel_loja)] if sel_loja else b
    sel_cargo = st.sidebar.multiselect("Cargo", sorted(b["cargo"].unique()), placeholder="Todos")
    b = b[b["cargo"].isin(sel_cargo)] if sel_cargo else b
    sel_pessoa = st.sidebar.multiselect("Colaborador", sorted(b["pessoa"].unique()),
                                        placeholder="Todos")
    st.sidebar.caption("Sem colaborador selecionado, mostra o agregado do filtro. "
                       "Selecionando colaboradores, cada um vira uma linha.")
    f = b[b["pessoa"].isin(sel_pessoa)] if sel_pessoa else b
    if f.empty:
        st.warning("Nenhum dado para os filtros selecionados.")
        return

    partes = [f"{n}: {', '.join(v)}" for n, v in (("Marcas", sel_marca), ("Lojas", sel_loja),
                                                    ("Cargos", sel_cargo),
                                                    ("Colaboradores", sel_pessoa)) if v]
    filtros_txt = " · ".join(partes) or "Todos"
    _, cexp = st.columns([3, 1])
    with cexp:
        botao_excel("📥 Exportar relatório (Excel)", gerar_excel_ranking(f, periodo, filtros_txt),
                    f"Ranking_TECAR_{dt.date.today().isoformat()}.xlsx")

    # ---- KPIs
    mensal = agg_por(f, "mes").sort_values("mes")
    mensal["mes_lbl"] = mensal["mes"].apply(mlabel)
    atual = mensal.iloc[-1]
    ant = mensal.iloc[-2] if len(mensal) > 1 else None

    def d(col, tipo):
        return delta_str(atual[col] - ant[col], tipo) if ant is not None else None

    r1 = st.columns(3)
    r1[0].metric(f"Passagens ({mes_lbl})", fmt_int(atual["passagens"]), d("passagens", "int"))
    r1[1].metric(f"Nº Refil Diant. ({mes_lbl})", fmt_int(atual["refil_diant"]),
                 d("refil_diant", "int"))
    r1[2].metric(f"Aproveitamento Diant. ({mes_lbl})", fmt_pct(atual["aproveitamento"]))
    r2 = st.columns(3)
    r2[0].metric(f"Faturamento total ({mes_lbl})", fmt_money(atual["total_geral"]),
                 d("total_geral", "money"))
    r2[1].metric(f"Nº Refil Tras. ({mes_lbl})", fmt_int(atual["refil_tras"]),
                 d("refil_tras", "int"))
    r2[2].metric(f"Aproveitamento Tras. ({mes_lbl})", fmt_pct(atual["aproveitamento_tras"]))
    st.caption("Variação comparada ao mês anterior dentro da janela. Passagens e "
               "aproveitamento aparecem como — porque a TECAR não envia passagens.")
    aviso_preco(f)
    st.divider()

    # ---- evolução
    st.subheader("Evolução no trimestre")
    if sel_pessoa:
        evo = agg_por(f, ["mes", "pessoa"]).sort_values("mes")
        evo["mes_lbl"] = evo["mes"].apply(mlabel)
        cor = "pessoa"
    else:
        evo, cor = mensal, None
    c1, c2 = st.columns(2)
    with c1:
        _linha(evo, "passagens", "Passagens", "%{y:,.0f}", cor, ordem)
    with c2:
        _linha(evo, "refil_diant", "Nº Refil Dianteiro", "%{y:,.0f}", cor, ordem)
    c3, c4 = st.columns(2)
    with c3:
        _linha(evo, "aproveitamento", "Aproveitamento", "%{y:.1%}", cor, ordem)
    with c4:
        _linha(evo, "total_geral", "Faturamento (R$)", "R$ %{y:,.2f}", cor, ordem)
    st.divider()

    # ---- por loja
    ctit, cord = st.columns([3, 1])
    escolha = cord.radio("Ordenar por", ["Refis vendidos", "Faturamento", "Aproveitamento"],
                         key="ord_loja")
    col = {"Refis vendidos": "refil_diant", "Faturamento": "total_geral",
           "Aproveitamento": "aproveitamento"}[escolha]
    ctit.subheader(f"{escolha} por loja")
    ctit.caption(f"{escolha} somado no trimestre, por loja.")
    pl = agg_por(f, "loja").dropna(subset=[col]).sort_values(col)
    if pl.empty:
        st.caption("Sem dados suficientes no período para este gráfico"
                   + (" (a TECAR não envia passagens)." if col == "aproveitamento"
                      else " (loja sem preço)." if col == "total_geral" else "."))
    else:
        rot = {"refil_diant": "Nº Refil Dianteiro", "total_geral": "Faturamento (R$)",
               "aproveitamento": "Aproveitamento"}[col]
        _, fmt, hover, xfmt = METRICAS[rot]
        _barras(pl, col, "loja", pl[col].map(fmt), "%{y}<br>" + hover, xfmt, escolha)
    st.divider()

    # ---- ranking
    st.subheader("Ranking no trimestre")
    cr1, cr2 = st.columns([2, 1])
    metrica = cr1.selectbox("Ordenar por", list(METRICAS))
    col, fmt, hover, xfmt = METRICAS[metrica]
    rk = agg_por(f, ["pessoa_id", "pessoa", "cargo"])
    rk["rotulo"] = rk["pessoa"] + " (" + rk["cargo"] + ")"
    n = len(rk)
    topn = cr2.slider("Quantos exibir", 5, n, min(15, n)) if n > 5 else n
    rk = rk.dropna(subset=[col]).sort_values(col, ascending=False).head(topn).sort_values(col)
    if rk.empty:
        st.caption("Sem dados para esta métrica"
                   + (" (a TECAR não envia passagens)." if col in ("passagens", "aproveitamento")
                      else " (loja sem preço)."))
    else:
        _barras(rk, col, "rotulo", rk[col].map(fmt), hover, xfmt, metrica)
    st.divider()

    # ---- detalhe
    with st.expander("Ver dados detalhados (filtro aplicado)"):
        show = f.sort_values(["mes", "loja", "pessoa"])
        tabela = pd.DataFrame({
            "Colaborador": show["pessoa"], "Cargo": show["cargo"], "Loja": show["loja"],
            "Mês": show["mes"].apply(mlabel), "Passagens": show["passagens"].map(fmt_int),
            "Refil Diant.": show["refil_diant"].map(fmt_int),
            "Refil Tras.": show["refil_tras"].map(fmt_int),
            "Aproveitamento": show["aproveitamento"].map(fmt_pct),
            "Total Diant.": show["total_diant"].map(fmt_money),
            "Total Tras.": show["total_tras"].map(fmt_money),
            "Total Geral": show["total_geral"].map(fmt_money)})
        st.dataframe(tabela, width="stretch", hide_index=True)
