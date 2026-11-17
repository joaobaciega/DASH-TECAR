"""Páginas restritas: Lançamento (correção manual) e Histórico."""

import unittest
from datetime import date
from unittest.mock import patch

from tests.apoio_app import escrever_driver, rodar
from tests.fabrica import DADOS_OUTUBRO

from tests.fabrica import pessoas_outubro

P = pessoas_outubro()   # nomes reais lidos de tests/dados (fora do Git)


class BloqueioTest(unittest.TestCase):
    def test_paginas_bloqueadas_sem_acesso(self):
        from paginas import historico, lancamento
        for modulo, leitura in ((lancamento, "ler_base"), (historico, "ler_historico")):
            with patch.object(modulo.st, "session_state", {}), \
                 patch.object(modulo.st, "error") as erro, \
                 patch.object(modulo.db, leitura) as consulta:
                modulo.pagina()
                erro.assert_called_once()
                consulta.assert_not_called()


@unittest.skipUnless(DADOS_OUTUBRO.exists(), "cópias de outubro ausentes")
class RestritasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = escrever_driver("restritas")

    def test_lancamento_previa_gerentes_e_salvar(self):
        app = rodar(self.driver, "📝 Lançamento", restrito=True)
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.selectbox(key="lanc_loja").value, "Jeep Goiânia")
        self.assertEqual(app.selectbox(key="lanc_mes").value, "Outubro/2026")
        app.selectbox(key="lanc_pessoa").set_value(f"{P['consultor_jeep']} — Consultor").run()
        app.number_input[0].set_value(10).run()
        self.assertFalse(app.exception, app.exception)
        previa = next(t.value for t in app.dataframe if "Vendas (depois)" in t.value.columns)
        depois = dict(zip(previa["Pessoa"], previa["Vendas (depois)"]))
        self.assertEqual(depois, {P["consultor_jeep"]: "10", P["gerente_pecas_jeep"]: "22",
                                  P["gerente_pos_jeep"]: "22"})
        receber = dict(zip(previa["Pessoa"], previa["A Receber (depois)"]))
        self.assertEqual(receber[P["gerente_pecas_jeep"]], "R$ 110,00")
        next(b for b in app.button if b.label == "Salvar correção").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.session_state["_chamadas_correcao"], [(1, date(2026, 10, 1), 1, 10)])
        self.assertTrue(app.success)

    def test_lancamento_exporta_mes_da_loja(self):
        import io
        from openpyxl import load_workbook
        from paginas import lancamento
        app = rodar(self.driver, "📝 Lançamento", restrito=True)
        self.assertEqual(len(app.get("download_button")), 1)
        from tecar.config import carregar_lojas
        from tests.fabrica import base_de_lotes, lotes_outubro
        base = base_de_lotes(lotes_outubro(), carregar_lojas())
        jeep = base[base["loja"] == "Jeep Goiânia"]
        wb = load_workbook(io.BytesIO(lancamento.gerar_excel(jeep, "Jeep Goiânia", "Outubro/2026")))
        ws = wb.active
        self.assertEqual(ws.max_row - 4, 6)                      # 5 pessoas + TOTAL
        self.assertEqual(ws.cell(ws.max_row, 1).value, "TOTAL")
        self.assertEqual(ws.cell(ws.max_row, ws.max_column).value, 400)

    def test_lancamento_tecnico_mexe_so_chefe(self):
        app = rodar(self.driver, "📝 Lançamento", restrito=True)
        app.selectbox(key="lanc_loja").set_value("Mercedes Goiânia").run()
        app.selectbox(key="lanc_pessoa").set_value(f"{P['tecnico_zero_mgo']} — Técnico").run()
        app.number_input[0].set_value(2).run()
        previa = next(t.value for t in app.dataframe if "Vendas (depois)" in t.value.columns)
        self.assertEqual(dict(zip(previa["Pessoa"], previa["Vendas (depois)"])),
                         {P["tecnico_zero_mgo"]: "2",
                          P["chefe_mgo"]: "21"})

    def test_historico_exporta(self):
        app = rodar(self.driver, "🗂️ Histórico", restrito=True)
        self.assertFalse(app.exception, app.exception)
        m = {x.label: x.value for x in app.metric}
        self.assertEqual((m["Importações"], m["Correções"], m["Pessoas corrigidas"]), ("4", "3", "3"))
        self.assertEqual(len(app.get("download_button")), 1)
        tabela = next(t.value for t in app.dataframe if "Tipo" in t.value.columns)
        self.assertEqual(len(tabela), 7)
        app.multiselect(key="hist_tipo").set_value(["Correção"]).run()
        tabela = next(t.value for t in app.dataframe if "Tipo" in t.value.columns)
        self.assertEqual(len(tabela), 3)


if __name__ == "__main__":
    unittest.main()
