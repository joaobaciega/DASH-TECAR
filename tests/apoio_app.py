"""Executa o app.py de verdade (streamlit AppTest) com o banco substituído por
dados de outubro montados em memória. Mesmo padrão do Dahruj: o driver
executa o app.py em duas partes e troca as funções antes da navegação."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "tests" / "__pycache__"

DRIVER = '''
import sys
from pathlib import Path
raiz = Path(r"{raiz}")
if str(raiz) not in sys.path:
    sys.path.insert(0, str(raiz))
import pandas as pd
import streamlit as st
import db
from tecar.config import carregar_lojas
from tests.fabrica import base_de_lotes, lotes_outubro, historico_exemplo
LOJAS = carregar_lojas()
BASE = base_de_lotes(lotes_outubro(), LOJAS)
HIST = historico_exemplo()
CHAMADAS = []
{preparo}
db.ler_base = lambda: BASE
db.ler_historico = lambda: HIST
def _salvar(*a):
    CHAMADAS.append(a)
    st.session_state["_chamadas_correcao"] = list(CHAMADAS)
    return {{"local": [{{"pessoa": "x", "cargo": "Consultor", "vendas_antes": 1, "vendas_depois": 2,
                       "a_receber_antes": 0, "a_receber_depois": 0}}]}}
db.salvar_correcao = _salvar
source = raiz / "app.py"
code = source.read_text(encoding="utf-8")
offset = code.index("# ============================ NAVEGAÇÃO")
scope = {{"__name__": "__main__", "__file__": str(source)}}
exec(compile(code[:offset], str(source), "exec"), scope)
scope["_senha_esperada"] = lambda: "senha-de-teste"
{pos}
exec(compile(code[offset:], str(source), "exec"), scope)
'''


def escrever_driver(nome: str, preparo: str = "", pos: str = "") -> Path:
    PASTA.mkdir(exist_ok=True)
    caminho = PASTA / f"driver_{nome}.py"
    caminho.write_text(DRIVER.format(raiz=RAIZ, preparo=preparo, pos=pos), encoding="utf-8")
    return caminho


def rodar(caminho: Path, pagina: str | None = None, restrito: bool = False):
    import time

    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(caminho), default_timeout=30)
    if pagina:
        app.session_state["menu_pagina"] = pagina
    if restrito:
        app.session_state["lanc_ok"] = True
        app.session_state["lanc_visto"] = time.monotonic()
    return app.run()
