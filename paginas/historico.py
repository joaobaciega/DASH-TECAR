"""Histórico (restrito): cada importação (atualizar.py) e cada correção manual."""

import datetime as dt

import pandas as pd
import streamlit as st

import db
from paginas.comum import (F_INT, F_MOEDA, botao_excel, erro_banco, excel_abas, fmt_int,
                           fmt_money, mlabel)

TIPOS = {"importacao": "Importação", "correcao": "Correção"}
COLUNAS = [  # (título, coluna, formato tela, formato Excel)
    ("Registrado em", "registrado_em", lambda v: pd.Timestamp(v).strftime("%d/%m/%Y %H:%M"),
     "dd/mm/yyyy hh:mm"),
    ("Tipo", "tipo_lbl", str, None), ("Loja", "loja", str, None), ("Mês", "mes_lbl", str, None),
    ("Pessoa", "pessoa", lambda v: "" if pd.isna(v) else v, None),
    ("Cargo", "cargo", lambda v: "" if pd.isna(v) else v, None),
    ("Vendas antes", "vendas_antes", fmt_int, F_INT),
    ("Vendas depois", "vendas_depois", fmt_int, F_INT),
    ("A Receber antes", "a_receber_antes", fmt_money, F_MOEDA),
    ("A Receber depois", "a_receber_depois", fmt_money, F_MOEDA),
    ("Arquivo", "arquivo", lambda v: "" if pd.isna(v) else v, None),
    ("Detalhe", "detalhe", lambda v: "" if pd.isna(v) else v, None),
]


def gerar_excel(h: pd.DataFrame, filtros_txt: str) -> bytes:
    linhas = []
    for _, r in h.iterrows():
        lin = []
        for _, col, _, fmt in COLUNAS:
            v = r[col]
            if col == "registrado_em":
                v = pd.Timestamp(v).to_pydatetime()
            lin.append(None if (not isinstance(v, str) and pd.isna(v)) else v)
        linhas.append(lin)
    return excel_abas([{"nome": "Histórico", "titulo": "Histórico — Grupo TECAR",
                        "subtitulo": f"Filtros: {filtros_txt}",
                        "cabecalho": [c[0] for c in COLUNAS], "linhas": linhas,
                        "formatos": [c[3] for c in COLUNAS],
                        "larguras": [17, 12, 20, 10, 32, 18, 11, 11, 14, 14, 40, 40]}])


def pagina():
    if not st.session_state.get("lanc_ok"):
        st.error("Área restrita. Libere o acesso no cadeado da barra lateral.")
        return
    st.title("🗂️ Histórico")
    st.caption("Cada importação do atualizar.py (uma linha por loja e mês) e cada correção "
               "manual da página Lançamento (uma linha por pessoa alterada).")
    try:
        h = db.ler_historico()
    except Exception:
        erro_banco()
        return
    if h.empty:
        st.info("Nenhum registro ainda.")
        return
    h = h.copy()
    h["tipo_lbl"] = h["tipo"].map(TIPOS).fillna(h["tipo"])
    h["mes_lbl"] = h["mes"].apply(mlabel)

    meses = [mlabel(m) for m in sorted(h["mes"].unique(), reverse=True)]
    c1, c2, c3 = st.columns(3)
    sel_mes = c1.multiselect("Mês", list(dict.fromkeys(meses)), key="hist_mes", placeholder="Todos")
    sel_loja = c2.multiselect("Loja", sorted(h["loja"].unique()), key="hist_loja",
                              placeholder="Todas")
    sel_tipo = c3.multiselect("Tipo", list(TIPOS.values()), key="hist_tipo", placeholder="Todos")
    f = h
    if sel_mes:
        f = f[f["mes_lbl"].isin(sel_mes)]
    if sel_loja:
        f = f[f["loja"].isin(sel_loja)]
    if sel_tipo:
        f = f[f["tipo_lbl"].isin(sel_tipo)]
    f = f.sort_values(["registrado_em", "id"], ascending=False)
    if f.empty:
        st.warning("Nenhum registro para estes filtros.")
        return

    corr = f[f["tipo"] == "correcao"]
    k = st.columns(3)
    k[0].metric("Importações", fmt_int((f["tipo"] == "importacao").sum()))
    k[1].metric("Correções", fmt_int(len(corr)))
    k[2].metric("Pessoas corrigidas", fmt_int(corr["pessoa"].nunique()))

    partes = [f"{n}: {', '.join(v)}" for n, v in (("Meses", sel_mes), ("Lojas", sel_loja),
                                                    ("Tipos", sel_tipo)) if v]
    _, cexp = st.columns([3, 1])
    with cexp:
        botao_excel("📥 Exportar histórico (Excel)", gerar_excel(f, " · ".join(partes) or "Todos"),
                    f"Historico_TECAR_{dt.date.today().isoformat()}.xlsx")
    st.dataframe(pd.DataFrame([{t: fmt(r[c]) for t, c, fmt, _ in COLUNAS}
                               for _, r in f.iterrows()]), width="stretch", hide_index=True)
