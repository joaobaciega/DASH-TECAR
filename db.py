"""Camada de dados do app (Streamlit).

Lê da seção [mysql] do .streamlit/secrets.toml: nesta máquina é o MySQL local;
no Streamlit Cloud, os dados da Aiven. O SQL fica em tecar/banco.py.

Teste de conexão fora do Streamlit:  python db.py
"""

import pandas as pd
import streamlit as st

from tecar import banco


@st.cache_resource
def get_engine():
    return banco.criar_engine(dict(st.secrets["mysql"]))


@st.cache_data(ttl=60)
def ler_base() -> pd.DataFrame:
    """Base do dashboard (view vw_base): uma linha por pessoa/loja/mês."""
    return banco.ler_base(get_engine())


@st.cache_data(ttl=60)
def ler_historico() -> pd.DataFrame:
    return banco.ler_historico(get_engine())


def _online():
    try:
        cfg = st.secrets.get("mysql_online")
    except Exception:
        return None
    return dict(cfg) if banco.online_preenchido(cfg) else None


def salvar_correcao(loja_id, mes, pessoa_id, vendas) -> dict:
    """Corrige as vendas no banco do app e, se houver [mysql_online] preenchido
    (só na máquina local), também no Aiven. Devolve {rótulo: mudanças | erro}."""
    resultado = {"banco do app": banco.salvar_correcao(get_engine(), int(loja_id), mes,
                                                       int(pessoa_id), int(vendas))}
    online = _online()
    if online is not None:
        try:
            eng = banco.criar_engine(online)
            # o mesmo id pode não existir no Aiven: localiza pela loja/nome
            resultado["Aiven"] = _corrigir_por_nome(eng, loja_id, mes, pessoa_id, vendas)
            eng.dispose()
        except Exception as e:
            resultado["Aiven"] = f"{type(e).__name__}: {e}"
    ler_base.clear()
    ler_historico.clear()
    return resultado


def _corrigir_por_nome(eng_online, loja_id, mes, pessoa_id, vendas):
    from sqlalchemy import text
    with get_engine().connect() as c:
        chave_loja, chave_pessoa = c.execute(text(
            "SELECT lo.chave, p.chave FROM pessoas p JOIN lojas lo ON lo.id = p.loja_id "
            "WHERE p.id = :p AND lo.id = :l"), {"p": int(pessoa_id), "l": int(loja_id)}).one()
    with eng_online.connect() as c:
        ids = c.execute(text(
            "SELECT lo.id, p.id FROM pessoas p JOIN lojas lo ON lo.id = p.loja_id "
            "WHERE lo.chave = :l AND p.chave = :p"), {"l": chave_loja, "p": chave_pessoa}).one_or_none()
    if ids is None:
        raise ValueError("pessoa não encontrada no Aiven (rode o atualizar.py antes)")
    return banco.salvar_correcao(eng_online, ids[0], mes, ids[1], int(vendas))


if __name__ == "__main__":
    cfg = banco.ler_secrets()["mysql"]
    eng = banco.criar_engine(cfg)
    base = banco.ler_base(eng)
    print(f"Conectado em {banco.descrever(cfg)}: {len(base)} linhas na vw_base.")
