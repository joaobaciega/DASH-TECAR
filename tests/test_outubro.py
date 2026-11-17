"""As 4 planilhas reais de outubro/2026 (cópias em tests/dados/outubro).

Totais esperados calculados direto das planilhas e informados no pedido.
"""

import unittest
from datetime import date
from decimal import Decimal

from tecar.config import carregar_cargos, carregar_lojas
from tecar.leitura import ler_pasta
from tests.fabrica import DADOS_OUTUBRO

ESPERADO = {  # chave da loja: (vendas, A RECEBER colaboradores, A RECEBER gerentes)
    "JEEP GOIANIA": (20, Decimal("200"), Decimal("200")),
    "MERCEDES BRASILIA": (24, Decimal("360"), Decimal("0")),
    "MERCEDES GOIANIA": (38, Decimal("475"), Decimal("95")),
    "MERCEDES UBERLANDIA": (22, Decimal("275"), Decimal("0")),
}


@unittest.skipUnless(DADOS_OUTUBRO.exists(), "cópias de outubro ausentes em tests/dados/outubro")
class OutubroTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lotes = ler_pasta(DADOS_OUTUBRO, carregar_lojas(), carregar_cargos(), 2026)
        cls.por_loja = {l.loja.chave: l for l in cls.lotes}

    def test_sem_erros_e_mes(self):
        self.assertEqual(len(self.lotes), 4)
        for l in self.lotes:
            self.assertEqual(l.erros, [], l.arquivo.name)
            self.assertEqual(l.mes, date(2026, 10, 1))

    def test_totais_por_loja(self):
        for k, (vendas, colab, ger) in ESPERADO.items():
            t = self.por_loja[k].totais()
            self.assertEqual((t["vendas"], t["a_receber_colaboradores"], t["a_receber_gerentes"]),
                             (vendas, colab, ger), k)

    def test_totais_grupo(self):
        tot = [l.totais() for l in self.lotes]
        self.assertEqual(sum(t["vendas"] for t in tot), 104)
        self.assertEqual(sum(t["a_receber_colaboradores"] + t["a_receber_gerentes"] for t in tot),
                         Decimal("1605"))

    def test_gerentes(self):
        cargos = {k: sorted(g.cargo for g in l.gerentes) for k, l in self.por_loja.items()}
        self.assertEqual(cargos, {"JEEP GOIANIA": ["Gerente Peças", "Gerente Pós Vendas"],
                                  "MERCEDES BRASILIA": [], "MERCEDES GOIANIA": ["Chefe de oficina"],
                                  "MERCEDES UBERLANDIA": []})
        for l in self.lotes:
            self.assertFalse([a for a in l.avisos if "equipe" in a], l.arquivo.name)
            self.assertFalse([a for a in l.avisos if "sem preço" in a], l.arquivo.name)


if __name__ == "__main__":
    unittest.main()
