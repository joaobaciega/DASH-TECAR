"""Lançamento (restrito): correção manual das vendas de um colaborador num mês.

Os gerentes cuja equipe inclui o cargo dele são recalculados (vendas = soma da
equipe; A RECEBER = verba × vendas). Cada correção vai para o Histórico.
Reimportar a loja/mês pelo atualizar.py substitui a correção.
"""

from decimal import Decimal

import pandas as pd
import streamlit as st

import db
from paginas.comum import (F_INT, F_MOEDA, botao_excel, erro_banco, excel_abas, fmt_int,
                           fmt_money, label_mes)
from tecar.config import ConfigInvalida, carregar_cargos, chave

ORIGEM = {"importacao": "Planilha", "correcao": "Correção manual"}


def gerar_excel(df_mes: pd.DataFrame, loja: str, mes_lbl: str) -> bytes:
    """Lançamentos da loja no mês, como estão no banco (com a origem de cada um)."""
    df = df_mes.sort_values(["grupo", "pessoa"], ascending=[True, True])
    linhas = [[r.pessoa, r.cargo, r.grupo.title(), ORIGEM.get(r.origem, r.origem), r.verba,
               r.refil_diant, r.a_receber] for r in df.itertuples()]
    colab = df[df["grupo"] == "colaborador"]
    linhas.append(["TOTAL", "", "", "", None, colab["refil_diant"].sum(), df["a_receber"].sum()])
    return excel_abas([{
        "nome": "Lançamentos", "titulo": f"Lançamentos — {loja} — {mes_lbl}",
        "subtitulo": "Vendas do TOTAL = colaboradores; A Receber do TOTAL = todos",
        "cabecalho": ["Nome", "Cargo", "Grupo", "Origem", "Verba (R$/venda)", "Vendas",
                      "A Receber (R$)"],
        "linhas": linhas, "total": True,
        "formatos": [None, None, None, None, F_MOEDA, F_INT, F_MOEDA],
        "larguras": [34, 18, 12, 16, 15, 9, 14]}])


def previa(df_loja_mes: pd.DataFrame, pessoa_id, vendas: int, equipes: dict) -> list[dict]:
    """O que a correção vai mudar: a pessoa + os gerentes afetados (mesma regra
    de tecar.banco.salvar_correcao, calculada em memória)."""
    alvo = df_loja_mes[df_loja_mes["pessoa_id"] == pessoa_id].iloc[0]
    colab = df_loja_mes[df_loja_mes["grupo"] == "colaborador"].copy()
    colab.loc[colab["pessoa_id"] == pessoa_id, "refil_diant"] = vendas

    def linha(r, v):
        return {"Pessoa": r["pessoa"], "Cargo": r["cargo"],
                "Vendas (antes)": fmt_int(r["refil_diant"]), "Vendas (depois)": fmt_int(v),
                "A Receber (antes)": fmt_money(r["a_receber"]),
                "A Receber (depois)": fmt_money(float(Decimal(str(r["verba"])) * v))}

    saida = [linha(alvo, vendas)]
    for _, g in df_loja_mes[df_loja_mes["grupo"] == "gerente"].sort_values("pessoa").iterrows():
        membros = {chave(x) for x in equipes.get(chave(g["cargo"]), ())}
        if chave(alvo["cargo"]) in membros:
            soma = int(colab.loc[colab["cargo"].map(chave).isin(membros), "refil_diant"].sum())
            saida.append(linha(g, soma))
    return saida


def pagina():
    if not st.session_state.get("lanc_ok"):
        st.error("Área restrita. Libere o acesso no cadeado da barra lateral.")
        return
    st.title("📝 Lançamento — correção manual")
    st.caption("Corrige as vendas de um colaborador num mês. O A RECEBER é recalculado "
               "(verba × vendas), e os gerentes da equipe dele também.")
    try:
        base = db.ler_base()
    except Exception:
        erro_banco()
        return
    if base.empty:
        st.info("Ainda não há dados no banco. Rode a atualização mensal (atualizar.py).")
        return
    try:
        equipes = {k: c.equipe for k, c in carregar_cargos().items()}
    except ConfigInvalida as e:
        st.error(f"config/cargos.toml com problema: {e}")
        return

    loja = st.selectbox("Loja", sorted(base["loja"].unique()), key="lanc_loja")
    da_loja = base[base["loja"] == loja]
    meses = sorted(da_loja["mes"].unique(), reverse=True)
    por_rotulo = {label_mes(m): m for m in meses}
    mes_lbl = st.selectbox("Mês", list(por_rotulo), key="lanc_mes")
    df_mes = da_loja[da_loja["mes"] == por_rotulo[mes_lbl]]
    colab = df_mes[df_mes["grupo"] == "colaborador"].sort_values("pessoa")
    _, cexp = st.columns([3, 1])
    with cexp:
        botao_excel("📥 Exportar lançamentos do mês (Excel)", gerar_excel(df_mes, loja, mes_lbl),
                    f"Lancamentos_TECAR_{chave(loja).replace(' ', '_')}_"
                    f"{pd.Timestamp(por_rotulo[mes_lbl]):%Y-%m}.xlsx")
    if colab.empty:
        st.warning("Nenhum colaborador nesta loja neste mês.")
        return
    opcoes = {f"{r.pessoa} — {r.cargo}": r for r in colab.itertuples()}
    escolha = st.selectbox("Colaborador", list(opcoes), key="lanc_pessoa")
    r = opcoes[escolha]

    st.divider()
    c = st.columns(3)
    c[0].metric("Verba (R$/venda)", fmt_money(r.verba))
    c[1].metric("Vendas atuais", fmt_int(r.refil_diant))
    c[2].metric("A Receber atual", fmt_money(r.a_receber))
    mes_date = pd.Timestamp(por_rotulo[mes_lbl]).date()
    novas = int(st.number_input("Vendas corrigidas", min_value=0, step=1,
                                value=int(r.refil_diant), key=f"vendas_{r.pessoa_id}_{mes_date}"))

    st.subheader("Prévia da correção")
    st.dataframe(pd.DataFrame(previa(df_mes, r.pessoa_id, novas, equipes)), width="stretch",
                 hide_index=True)
    st.warning("Se este mês da loja for importado de novo pelo atualizar.py, a planilha "
               "substitui esta correção (a prévia do atualizar.py avisa antes).")

    if st.button("Salvar correção", type="primary", width="stretch"):
        try:
            resultado = db.salvar_correcao(int(r.loja_id), mes_date, int(r.pessoa_id), novas)
        except Exception as e:
            st.error(f"Não foi possível salvar: {type(e).__name__}: {e}")
            return
        for rotulo, res in resultado.items():
            if isinstance(res, str):
                st.error(f"❌ {rotulo}: não gravou ({res}).")
            else:
                st.success(f"✅ {rotulo}: {len(res)} registro(s) atualizado(s).")
        st.toast("Correção registrada no Histórico.", icon="✅")
