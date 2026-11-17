"""Páginas públicas com a base de outubro/2026 (preço padrão R$ 199)."""

import io
import unittest

from openpyxl import load_workbook

from tests.apoio_app import escrever_driver, rodar
from tests.fabrica import DADOS_OUTUBRO, pessoas_outubro

P = pessoas_outubro()   # nomes reais lidos de tests/dados (fora do Git)

SEM_PRECO_BRASILIA = '''
from dataclasses import replace
LOJAS =[replace(l, preco_diant=None) if l.chave == "MERCEDES BRASILIA" else l for l in LOJAS]
BASE = base_de_lotes(lotes_outubro(), LOJAS)
'''


def metricas(app):
    return {m.label: m.value for m in app.metric}


def downloads(app):
    return app.get("download_button")


def tabela_com(app, coluna):
    return next(t.value for t in app.dataframe if coluna in t.value.columns)


@unittest.skipUnless(DADOS_OUTUBRO.exists(), "cópias de outubro ausentes")
class PaginasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = escrever_driver("paginas")
        cls.driver_sem_preco = escrever_driver("sem_preco", preparo=SEM_PRECO_BRASILIA)

    def test_dashboard_outubro(self):
        app = rodar(self.driver, "Dashboard")
        self.assertFalse(app.exception, app.exception)
        m = metricas(app)
        self.assertEqual(m["Nº Refil Diant. (Out/2026)"], "104")
        self.assertEqual(m["Faturamento total (Out/2026)"], "R$ 20.696,00")
        self.assertEqual(m["Passagens (Out/2026)"], "—")
        self.assertEqual(m["Aproveitamento Diant. (Out/2026)"], "—")
        self.assertEqual(len(downloads(app)), 1)
        cargo = next(w for w in app.sidebar.multiselect if w.label == "Cargo")
        self.assertEqual(cargo.options, ["Consultor", "Técnico", "Vendedor de Peças"])
        loja = next(w for w in app.sidebar.multiselect if w.label == "Loja")
        self.assertEqual(len(loja.options), 4)
        cargo.set_value(["Técnico"]).run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(metricas(app)["Nº Refil Diant. (Out/2026)"], "42")

    def test_faturamento_sem_preco(self):
        app = rodar(self.driver_sem_preco, "Dashboard")
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(metricas(app)["Faturamento total (Out/2026)"], "—")
        self.assertTrue(any("Mercedes Brasília" in c.value for c in app.caption))
        next(w for w in app.sidebar.multiselect if w.label == "Loja").set_value(["Jeep Goiânia"]).run()
        self.assertEqual(metricas(app)["Faturamento total (Out/2026)"], "R$ 3.980,00")

    def test_relatorio_gerente_outubro(self):
        app = rodar(self.driver, "Relatório por Gerente")
        self.assertFalse(app.exception, app.exception)
        t = tabela_com(app, "Vendas equipe")
        nomes = list(t["Gerente"])
        for g in (P["gerente_pecas_jeep"], P["gerente_pos_jeep"],
                  P["chefe_mgo"]):
            self.assertIn(g, nomes)
        self.assertEqual(nomes.count("(sem gerente)"), 2)
        total = t[t["Gerente"] == "TOTAL"].iloc[0]
        self.assertEqual(total["Vendas equipe"], "104")
        self.assertEqual(total["A Receber"], "R$ 295,00")
        self.assertEqual(total["Total Geral"], "R$ 20.696,00")
        kleuber = t[t["Gerente"] == P["chefe_mgo"]].iloc[0]
        self.assertEqual((kleuber["Vendas equipe"], kleuber["Equipe"], kleuber["A Receber"]),
                         ("19", "Técnico", "R$ 95,00"))
        self.assertEqual(len(downloads(app)), 1)

    def test_relatorio_colaborador_filtro_cargo(self):
        app = rodar(self.driver, "Relatório por Colaborador")
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(len(tabela_com(app, "Colaborador")), 25)      # 24 + TOTAL
        next(w for w in app.multiselect if w.label == "Cargo").set_value(["Técnico"]).run()
        self.assertFalse(app.exception, app.exception)
        t = tabela_com(app, "Colaborador")
        self.assertEqual(len(t), 13)
        self.assertEqual(t.iloc[-1]["Colaborador"], "TOTAL")
        self.assertEqual(t.iloc[-1]["Refil Diant."], "42")
        self.assertEqual(set(t.iloc[:-1]["Cargo"]), {"Técnico"})
        self.assertEqual(len(downloads(app)), 1)

    def test_verbas_outubro(self):
        app = rodar(self.driver, "Verbas")
        self.assertFalse(app.exception, app.exception)
        self.assertEqual([m.value for m in app.metric],
                         ["R$ 1.310,00", "R$ 295,00", "R$ 1.605,00", "104"])
        self.assertEqual(len(downloads(app)), 1)

    def test_verbas_excel(self):
        from paginas import verbas
        from tecar.config import carregar_lojas
        from tests.fabrica import base_de_lotes, lotes_outubro
        base = base_de_lotes(lotes_outubro(), carregar_lojas())
        dados = verbas.gerar_excel("Outubro/2026", verbas.tabela_por_loja(base),
                                   verbas.tabela_mensal(base), verbas.tabela_pessoas(base))
        wb = load_workbook(io.BytesIO(dados))
        self.assertEqual(wb.sheetnames, ["Por loja", "Mês a mês", "Por pessoa"])
        ws = wb["Por loja"]
        self.assertEqual(ws.cell(ws.max_row, 1).value, "TOTAL")
        self.assertEqual(ws.cell(ws.max_row, ws.max_column).value, 1605)


if __name__ == "__main__":
    unittest.main()
