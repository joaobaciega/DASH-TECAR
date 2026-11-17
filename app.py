"""
Dashboard Grupo TECAR — Refis para Palhetas (Streamlit + MySQL).

Páginas públicas: Dashboard, Relatório por Gerente, Relatório por Colaborador
e Verbas. Páginas restritas (cadeado no fim da barra lateral): Lançamento
(correção manual de vendas) e Histórico (importações e correções).

PÁGINA NOVA: crie paginas/<nome>.py com uma função pagina() e acrescente UMA
linha na lista PAGINAS abaixo. O menu e a navegação saem só dessa lista.

Como rodar (na pasta do projeto, com .streamlit/secrets.toml configurado):
    streamlit run app.py
"""

import base64
import hmac
import time
from collections import namedtuple
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Grupo TECAR — Refis para Palhetas", page_icon="📊",
                   layout="wide")

from paginas import (dashboard, historico, lancamento, relatorio_colaborador,  # noqa: E402
                     relatorio_gerente, verbas)

ASSETS = Path(__file__).resolve().parent / "assets"
LOGO = ASSETS / "logo.png"

# ------------------------------------------------------------- páginas
# titulo  -> texto do menu | funcao -> o que desenha | restrita -> só com senha
Pagina = namedtuple("Pagina", "titulo funcao restrita")
PAGINAS = [
    Pagina("Dashboard", dashboard.pagina, False),
    Pagina("Relatório por Gerente", relatorio_gerente.pagina, False),
    Pagina("Relatório por Colaborador", relatorio_colaborador.pagina, False),
    Pagina("Verbas", verbas.pagina, False),
    Pagina("📝 Lançamento", lancamento.pagina, True),
    Pagina("🗂️ Histórico", historico.pagina, True),
]

_TTL_ACESSO = 30 * 60        # segundos sem uso até travar de novo
_MAX_TENTATIVAS = 3
_ESPERA_BLOQUEIO = 60        # segundos de espera após 3 senhas erradas


# ---------------------------------------------------------- identidade
def _logo_base64():
    try:
        return base64.b64encode(LOGO.read_bytes()).decode()
    except OSError:
        return None


def _injetar_css():
    """Preto (primária) e branco (secundária): barra lateral e cabeçalho pretos
    com a logo; conteúdo branco com texto preto; cartões em destaque pretos."""
    logo = _logo_base64()
    fundo_cab = (f'#000 url("data:image/png;base64,{logo}") no-repeat center / auto 62%'
                 if logo else "#000")
    st.markdown(f"""
        <style>
        header[data-testid="stHeader"] {{ background: {fundo_cab}; }}
        header[data-testid="stHeader"] * {{ color: #FFF !important; }}
        section[data-testid="stSidebar"] {{ background: #000; }}
        section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3, section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] small,
        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
        section[data-testid="stSidebar"] button svg {{ color: #FFF !important; }}
        section[data-testid="stSidebar"] [data-baseweb="select"] span,
        section[data-testid="stSidebar"] [data-baseweb="select"] input,
        section[data-testid="stSidebar"] [data-baseweb="tag"] span {{ color: #000 !important; }}
        section[data-testid="stSidebar"] hr {{ border-color: #444 !important; }}
        section[data-testid="stSidebar"] [data-baseweb="radio"] > div:first-child {{
            background: #000 !important; border: 2px solid #FFF !important; }}
        section[data-testid="stSidebar"] [data-baseweb="radio"] > div:first-child > div {{
            background: #000 !important; }}
        section[data-testid="stSidebar"] [data-baseweb="radio"]:has(input:checked) > div:first-child > div {{
            background: #FFF !important; }}
        section[data-testid="stSidebar"] [data-baseweb="radio"]:has(input:checked) p {{
            font-weight: 700; }}
        div[data-testid="stMetric"] {{
            background: #000; border-radius: 8px; padding: 14px 16px; }}
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] *,
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {{ color: #FFF !important; }}
        hr {{ border-color: #BDBDB8 !important; }}
        </style>
    """, unsafe_allow_html=True)


def mostrar_logo():
    if LOGO.exists():
        st.sidebar.image(str(LOGO), width="stretch")
    else:
        st.sidebar.markdown("## Grupo TECAR")


# ------------------------------------------------------- área restrita
def _senha_esperada():
    """Senha em [acesso] senha_lancamento do secrets; None se não houver."""
    try:
        senha = str(st.secrets["acesso"]["senha_lancamento"]).strip()
    except (KeyError, FileNotFoundError, AttributeError):
        return None
    return senha or None


def _senha_correta(senha):
    esperada = _senha_esperada()
    return bool(senha) and esperada is not None and hmac.compare_digest(
        senha.encode("utf-8"), esperada.encode("utf-8"))


def _travar():
    for chave in ("lanc_ok", "lanc_visto", "lanc_erros", "lanc_espera"):
        st.session_state.pop(chave, None)


def _revalidar_acesso():
    """Diz se a área restrita está liberada e renova o relógio de inatividade.
    Chamar uma vez por execução, antes do menu."""
    if not st.session_state.get("lanc_ok"):
        return False
    agora = time.monotonic()
    if agora - st.session_state.get("lanc_visto", agora) > _TTL_ACESSO:
        _travar()
        return False
    st.session_state["lanc_visto"] = agora
    return True


@st.dialog("Área restrita")
def _dialogo_senha():
    st.caption("Informe a senha para acessar Lançamento e Histórico.")
    if _senha_esperada() is None:
        st.error("Senha não configurada: preencha [acesso] senha_lancamento no "
                 ".streamlit/secrets.toml (ou nos Secrets do Streamlit Cloud).")
        return
    with st.form("form_senha", clear_on_submit=True, border=False):
        senha = st.text_input("Senha", type="password", label_visibility="collapsed",
                              placeholder="Senha")
        enviou = st.form_submit_button("Entrar", type="primary", width="stretch")
    if not enviou:
        return
    restante = st.session_state.get("lanc_espera", 0.0) - time.monotonic()
    if restante > 0:
        st.error(f"Muitas tentativas. Aguarde {int(restante) + 1}s.")
        return
    if _senha_correta(senha):
        st.session_state["lanc_ok"] = True
        st.session_state["lanc_visto"] = time.monotonic()
        st.session_state["lanc_ir"] = True
        st.session_state.pop("lanc_erros", None)
        st.rerun()
    erros = st.session_state.get("lanc_erros", 0) + 1
    if erros >= _MAX_TENTATIVAS:
        st.session_state["lanc_espera"] = time.monotonic() + _ESPERA_BLOQUEIO
        st.session_state["lanc_erros"] = 0
        st.error("Muitas tentativas. Aguarde 1 minuto antes de tentar de novo.")
    else:
        st.session_state["lanc_erros"] = erros
        st.error(f"Senha incorreta. Tentativa {erros} de {_MAX_TENTATIVAS}.")


def _clicar_cadeado():
    if st.session_state.get("lanc_ok"):
        _travar()
    else:
        st.session_state["pedir_senha_restrita"] = True


def _barra_acesso():
    """Cadeado discreto no fim da barra lateral."""
    st.sidebar.divider()
    liberado = bool(st.session_state.get("lanc_ok"))
    st.sidebar.button("🔓" if liberado else "🔒", key="btn_cadeado", type="tertiary",
                      on_click=_clicar_cadeado,
                      help="Bloquear área restrita" if liberado else "Área restrita")
    if st.session_state.pop("pedir_senha_restrita", False):
        _dialogo_senha()


# ============================ NAVEGAÇÃO
_injetar_css()
mostrar_logo()

publicas = [p.titulo for p in PAGINAS if not p.restrita]
restritas = [p.titulo for p in PAGINAS if p.restrita]

# Normaliza ANTES de criar o menu (depois, escrever em menu_pagina dá erro).
_ir_para_restrita = st.session_state.pop("lanc_ir", False)
_liberado = _revalidar_acesso()
if _liberado and _ir_para_restrita and restritas:
    st.session_state["menu_pagina"] = restritas[0]
elif not _liberado and st.session_state.get("menu_pagina") in restritas:
    st.session_state["menu_pagina"] = publicas[0]

opcoes = publicas + (restritas if _liberado else [])
if st.session_state.get("menu_pagina") not in opcoes:
    st.session_state["menu_pagina"] = opcoes[0]
escolhida = st.sidebar.radio("Menu", opcoes, key="menu_pagina")
st.sidebar.divider()

destinos = {p.titulo: p.funcao for p in PAGINAS}
try:
    destinos[escolhida]()
finally:
    _barra_acesso()                      # o cadeado sobrevive a erro na página
