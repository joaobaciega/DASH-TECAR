"""App: navegação por lista única, área restrita e agregações comuns."""

import time
import unittest

import pandas as pd

from tests.apoio_app import escrever_driver, rodar
from tests.fabrica import DADOS_OUTUBRO

PUBLICAS = ["Dashboard", "Relatório por Gerente", "Relatório por Colaborador", "Verbas"]
RESTRITAS = ["📝 Lançamento", "🗂️ Histórico"]


class ComumTest(unittest.TestCase):
    def test_formatos(self):
        from paginas.comum import fmt_int, fmt_money, fmt_pct
        self.assertEqual(fmt_money(20696), "R$ 20.696,00")
        self.assertEqual(fmt_money(float("nan")), "—")
        self.assertEqual(fmt_money(None), "—")
        self.assertEqual(fmt_int(1605.0), "1.605")
        self.assertEqual(fmt_pct(float("nan")), "—")
        self.assertEqual(fmt_pct(0.255), "25,5%")

    def test_agg_sem_preco_nao_soma_zero(self):
        from paginas.comum import agg_por, agg_total, lojas_sem_preco
        df = pd.DataFrame({
            "loja": ["A", "A", "B"], "passagens": [float("nan")] * 3,
            "refil_diant": [2.0, 3.0, 4.0], "refil_tras": [0.0] * 3,
            "a_receber": [20.0, 30.0, 40.0], "total_diant": [10.0, 15.0, float("nan")],
            "total_tras": [0.0] * 3, "total_geral": [10.0, 15.0, float("nan")]})
        g = agg_por(df, "loja").set_index("loja")
        self.assertEqual(g.loc["A", "total_geral"], 25.0)
        self.assertTrue(pd.isna(g.loc["B", "total_geral"]))
        self.assertTrue(pd.isna(g.loc["A", "passagens"]))
        self.assertTrue(pd.isna(g.loc["A", "aproveitamento"]))
        t = agg_total(df)
        self.assertEqual(t["refil_diant"], 9.0)
        self.assertEqual(t["a_receber"], 90.0)
        self.assertTrue(pd.isna(t["total_geral"]))
        self.assertEqual(lojas_sem_preco(df), ["B"])


@unittest.skipUnless(DADOS_OUTUBRO.exists(), "cópias de outubro ausentes")
class NavegacaoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = escrever_driver("nav")

    def test_menu_publico(self):
        app = rodar(self.driver)
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.sidebar.radio[0].options, PUBLICAS)

    def test_restritas_com_acesso(self):
        app = rodar(self.driver, restrito=True)
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.sidebar.radio[0].options, PUBLICAS + RESTRITAS)

    def test_lista_unica(self):
        driver = escrever_driver("lista", pos='scope["PAGINAS"].append(scope["Pagina"]('
                                              '"Página Teste", lambda: st.write("teste"), False))')
        app = rodar(driver)
        self.assertEqual(app.sidebar.radio[0].options, PUBLICAS + ["Página Teste"])
        app.sidebar.radio[0].set_value("Página Teste").run()
        self.assertFalse(app.exception, app.exception)
        self.assertIn("teste", [m.value for m in app.markdown])

    def test_sessao_expirada(self):
        app = rodar(self.driver, pagina="🗂️ Histórico", restrito=True)
        app.session_state["lanc_visto"] = time.monotonic() - 1801
        app.run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.sidebar.radio[0].options, PUBLICAS)
        self.assertEqual(app.sidebar.radio[0].value, "Dashboard")

    def test_cadeado_senha_errada_e_certa(self):
        app = rodar(self.driver)
        app.button(key="btn_cadeado").click().run()
        self.assertFalse(app.exception, app.exception)
        app.text_input[0].set_value("incorreta")
        # AppTest refaz o script inteiro; no navegador o formulário refaz só o
        # diálogo. Reabre o diálogo para processar a submissão (como no Dahruj).
        app.session_state["pedir_senha_restrita"] = True
        next(b for b in app.button if b.label == "Entrar").click().run()
        self.assertEqual(app.sidebar.radio[0].options, PUBLICAS)
        self.assertTrue(app.error)
        app.text_input[0].set_value("senha-de-teste")
        app.session_state["pedir_senha_restrita"] = True
        next(b for b in app.button if b.label == "Entrar").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.sidebar.radio[0].options, PUBLICAS + RESTRITAS)
        self.assertEqual(app.sidebar.radio[0].value, "📝 Lançamento")

    def test_cadeado_trava_de_novo(self):
        app = rodar(self.driver, pagina="📝 Lançamento", restrito=True)
        app.button(key="btn_cadeado").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.sidebar.radio[0].options, PUBLICAS)
        self.assertEqual(app.sidebar.radio[0].value, "Dashboard")


if __name__ == "__main__":
    unittest.main()
