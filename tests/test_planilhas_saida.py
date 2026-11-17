"""Excel espelho (BASE GRUPO TECAR.xlsx) e Excel de conferência."""

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from tecar.config import carregar_lojas
from tecar.conferencia import comparar, escrever_conferencia
from tecar.espelho import escrever_espelho
from tests.fabrica import DADOS_OUTUBRO, base_de_lotes, lotes_outubro

LOJAS = carregar_lojas()


def _coluna(ws, titulo):
    cab = [c.value for c in ws[1]]
    j = cab.index(titulo)
    return [r[j] for r in ws.iter_rows(min_row=2, values_only=True)]


@unittest.skipUnless(DADOS_OUTUBRO.exists(), "cópias de outubro ausentes")
class SaidaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lotes = lotes_outubro()
        cls._tmp = tempfile.TemporaryDirectory()
        cls.pasta = Path(cls._tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_espelho_outubro(self):
        caminho = self.pasta / "BASE GRUPO TECAR.xlsx"
        escrever_espelho(base_de_lotes(self.lotes, LOJAS), LOJAS, caminho)
        wb = load_workbook(caminho)
        self.assertEqual(wb.sheetnames, ["Consultores", "Gerentes", "Preço por Unidade"])
        cons, ger, preco = wb["Consultores"], wb["Gerentes"], wb["Preço por Unidade"]
        self.assertEqual(cons.max_row - 1, 24)
        self.assertEqual(ger.max_row - 1, 3)
        self.assertEqual(cons.cell(1, 1).value, "Consultor")
        self.assertEqual(ger.cell(1, 1).value, "Gerente")
        self.assertEqual([c.value for c in cons[1]][-3:], ["Cargo", "Verba (R$/venda)", "A Receber (R$)"])
        self.assertEqual([c.value for c in ger[1]][-3:], ["Cargo", "Verba (R$/venda)", "A Receber (R$)"])
        self.assertEqual(sum(_coluna(cons, "A Receber (R$)")), 1310)
        self.assertEqual(sum(_coluna(ger, "A Receber (R$)")), 295)
        self.assertEqual(sum(_coluna(cons, "Refil Diant. (qtd)")), 104)
        self.assertEqual(sum(_coluna(cons, "Total Geral (R$)")), 20696)
        self.assertTrue(all(v is None for v in _coluna(cons, "Passagens")))
        self.assertTrue(all(v is None for v in _coluna(cons, "Aproveitamento")))
        self.assertEqual(preco.max_row - 1, 4)
        self.assertEqual(_coluna(preco, "Preço Diant. (R$)"), [199] * 4)
        textos = {str(c.value) for ws in wb for row in ws.iter_rows() for c in row}
        self.assertFalse({"Volkswagen", "Loja 1", "Loja 2"} & textos)

    def test_comparar_ok_e_divergencia(self):
        local = {l.loja.chave: l.totais() for l in self.lotes}
        linhas = comparar(self.lotes, local, None)
        self.assertEqual(len(linhas), 4)
        self.assertEqual({l["status"] for l in linhas}, {"Aiven não gravado"})
        linhas = comparar(self.lotes, local, local)
        self.assertEqual({l["status"] for l in linhas}, {"OK"})
        ruim = {k: dict(v) for k, v in local.items()}
        ruim["JEEP GOIANIA"]["vendas"] = 19
        linhas = {l["loja"]: l for l in comparar(self.lotes, ruim, local)}
        self.assertEqual(linhas["Jeep Goiânia"]["status"], "DIVERGE: local")
        self.assertEqual(linhas["Jeep Goiânia"]["local_vendas"], 19)
        self.assertEqual(linhas["Mercedes Brasília"]["status"], "OK")
        sem_loja = {k: v for k, v in local.items() if k != "MERCEDES UBERLANDIA"}
        linhas = {l["loja"]: l for l in comparar(self.lotes, local, sem_loja)}
        self.assertEqual(linhas["Mercedes Uberlândia"]["status"], "DIVERGE: aiven")

    def test_escrever_conferencia(self):
        local = {l.loja.chave: l.totais() for l in self.lotes}
        caminho = self.pasta / "conferencia_2026-10.xlsx"
        escrever_conferencia(caminho, date(2026, 10, 1), comparar(self.lotes, local, None),
                             ["aviso de teste"])
        wb = load_workbook(caminho)
        self.assertEqual(wb.sheetnames, ["Conferência", "Avisos"])
        ws = wb["Conferência"]
        self.assertEqual(ws.max_row - 1, 5)
        self.assertEqual(ws.cell(ws.max_row, 1).value, "GRUPO")
        self.assertEqual(ws.cell(ws.max_row, 2).value, "=SUM(B2:B5)")
        self.assertEqual(_coluna(ws, "Vendas — arquivo")[:4], [20, 24, 38, 22])
        self.assertIn("aviso de teste", [c.value for c in wb["Avisos"]["A"]])


if __name__ == "__main__":
    unittest.main()
