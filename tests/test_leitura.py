"""Leitura das planilhas de verbas: nome do arquivo, cargos, bloqueios e avisos."""

import tempfile
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from tecar.config import carregar_cargos, carregar_lojas
from tecar.leitura import identificar_arquivo, ler_arquivo, ler_pasta
from tests.fabrica import criar_planilha

LOJAS = carregar_lojas()
CARGOS = carregar_cargos()
JEEP = "VERBAS OUTUBRO TECAR JEEP GOIANIA.xlsx"


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def lote(self, linhas, nome=JEEP, lojas=LOJAS, **kw):
        return ler_arquivo(criar_planilha(self.pasta / nome, linhas, **kw), lojas, CARGOS, 2026)


class NomeArquivoTest(unittest.TestCase):
    def test_identificar_outubro(self):
        mes, loja, erros = identificar_arquivo(JEEP, LOJAS, 2026)
        self.assertEqual((mes, loja.nome, erros), (date(2026, 10, 1), "Jeep Goiânia", []))
        mes, loja, erros = identificar_arquivo("verbas março tecar mercedes brasília.xlsx", LOJAS, 2026)
        self.assertEqual((mes, loja.nome, erros), (date(2026, 3, 1), "Mercedes Brasília", []))

    def test_mes_ilegivel(self):
        mes, _, erros = identificar_arquivo("VERBAS OUTUBR TECAR JEEP GOIANIA.xlsx", LOJAS, 2026)
        self.assertIsNone(mes)
        self.assertTrue(any("mês" in e for e in erros), erros)

    def test_loja_fora_config(self):
        for nome in ("VERBAS OUTUBRO TECAR VW ANAPOLIS.xlsx", "VERBAS SETEMBRO.xlsx"):
            _, loja, erros = identificar_arquivo(nome, LOJAS, 2026)
            self.assertIsNone(loja)
            self.assertTrue(any("loja" in e for e in erros), (nome, erros))


class LeituraTest(Base):
    def test_cargo_normalizado(self):
        l = self.lote([("A", "Consultor ", 10, 1, 10), ("B", "Tecnico", 5, 1, 5),
                       ("C", "TÉCNICO", 5, 0, 0)])
        self.assertEqual(l.erros, [])
        self.assertEqual([x.cargo for x in l.linhas], ["Consultor", "Técnico", "Técnico"])
        self.assertEqual([x.grupo for x in l.linhas], ["colaborador"] * 3)

    def test_nome_com_espacos_e_valores(self):
        l = self.lote([("  Maria  da Silva ", "Técnico", 5, 3, 15)])
        x = l.linhas[0]
        self.assertEqual((x.linha, x.nome, x.verba, x.vendas, x.a_receber),
                         (2, "Maria da Silva", Decimal("5"), 3, Decimal("15")))

    def test_cargo_desconhecido_bloqueia(self):
        l = self.lote([("A", "Consultor", 10, 1, 10), ("B", "Estagiário", 5, 1, 5)])
        self.assertTrue(any("linha 3" in e and "Estagiário" in e for e in l.erros), l.erros)

    def test_nome_repetido_bloqueia(self):
        l = self.lote([("Ana Silva", "Consultor", 10, 1, 10), ("ana silva ", "Técnico", 5, 1, 5)])
        self.assertTrue(any("linhas 2 e 3" in e for e in l.erros), l.erros)

    def test_a_receber_divergente_bloqueia(self):
        l = self.lote([("A", "Consultor", 10, 3, 31)])
        self.assertTrue(any("linha 2" in e and "A RECEBER" in e for e in l.erros), l.erros)

    def test_a_receber_vazio_bloqueia(self):
        l = self.lote([("A", "Consultor", 10, 2, None)])
        self.assertTrue(any("linha 2" in e and "Excel" in e for e in l.erros), l.erros)

    def test_a_receber_vazio_zero_ok(self):
        l = self.lote([("A", "Consultor", 10, 0, None)])
        self.assertEqual(l.erros, [])
        self.assertEqual(l.linhas[0].a_receber, Decimal("0"))

    def test_formula_sem_valor_calculado_bloqueia(self):
        # arquivo salvo por ferramenta que não calcula: a fórmula vem sem valor
        l = self.lote([("A", "Consultor", 10, 2, 20),
                       ("G", "Gerente Peças", 5, "=SUM(D2:D2)", "=C3*D3")])
        self.assertTrue(any("linha 3" in e and "Excel" in e for e in l.erros), l.erros)

    def test_valores_arredondados_em_centavos(self):
        l = self.lote([("A", "Consultor", 2.3, 3, 6.8999999999999995)])
        self.assertEqual(l.erros, [])
        self.assertEqual((str(l.linhas[0].verba), str(l.linhas[0].a_receber)), ("2.30", "6.90"))

    def test_verba_com_mais_de_dois_decimais_bloqueia(self):
        l = self.lote([("A", "Consultor", 3.3333, 3, 9.9999)])
        self.assertTrue(any("linha 2" in e and "VERBA" in e for e in l.erros), l.erros)

    def test_linha_com_valores_sem_nome_e_cargo_bloqueia(self):
        l = self.lote([("A", "Consultor", 10, 1, 10), (None, None, 10, 5, 50)])
        self.assertTrue(any("linha 3" in e for e in l.erros), l.erros)

    def test_valor_nao_numerico_bloqueia(self):
        l = self.lote([("A", "Consultor", "dez", 2, 20)])
        self.assertTrue(any("linha 2" in e and "VERBA" in e for e in l.erros), l.erros)

    def test_vendas_negativa_ou_fracionada_bloqueia(self):
        l = self.lote([("A", "Consultor", 10, -1, -10), ("B", "Consultor", 10, 1.5, 15)])
        self.assertTrue(any("linha 2" in e for e in l.erros), l.erros)
        self.assertTrue(any("linha 3" in e for e in l.erros), l.erros)

    def test_vendas_vazia_vira_zero_com_aviso(self):
        l = self.lote([("A", "Consultor", 10, None, 0)])
        self.assertEqual(l.erros, [])
        self.assertEqual(l.linhas[0].vendas, 0)
        self.assertTrue(any("linha 2" in a for a in l.avisos), l.avisos)

    def test_linhas_vazias_ignoradas(self):
        l = self.lote([("A", "Consultor", 10, 1, 10), (None,) * 5,
                       ("B", "Técnico", 5, 1, 5), (None,) * 5, (None,) * 5])
        self.assertEqual(l.erros, [])
        self.assertEqual(len(l.linhas), 2)

    def test_cabecalho_em_outra_linha(self):
        l = self.lote([("A", "Consultor", 10, 1, 10)], linha_cabecalho=3)
        self.assertEqual(l.erros, [])
        self.assertEqual(l.linhas[0].linha, 4)

    def test_sem_cabecalho_bloqueia(self):
        l = self.lote([("A", "Consultor", 10, 1, 10)], cabecalho=("X", "Y", "Z", "W", "K"))
        self.assertTrue(any("cabeçalho" in e for e in l.erros), l.erros)

    def test_gerente_diferente_da_equipe_avisa(self):
        l = self.lote([("A", "Consultor", 10, 5, 50), ("B", "Vendedor de Peças", 10, 3, 30),
                       ("C", "Técnico", 5, 4, 20), ("G", "Gerente Peças", 5, 9, 45)])
        self.assertEqual(l.erros, [])
        self.assertTrue(any("G" in a and "9" in a and "8" in a for a in l.avisos), l.avisos)

    def test_gerente_igual_a_equipe_sem_aviso(self):
        l = self.lote([("A", "Consultor", 10, 5, 50), ("G", "Gerente Peças", 5, 5, 25)])
        self.assertFalse(any("equipe" in a for a in l.avisos), l.avisos)

    def test_sem_preco_avisa(self):
        sem_preco = [replace(x, preco_diant=None) for x in LOJAS]
        l = self.lote([("A", "Consultor", 10, 1, 10)], lojas=sem_preco)
        self.assertEqual(l.erros, [])
        self.assertTrue(any("sem preço" in a for a in l.avisos), l.avisos)

    def test_totais_excluem_vendas_de_gerente(self):
        l = self.lote([("A", "Consultor", 10, 8, 80), ("B", "Consultor", 10, 4, 40),
                       ("G", "Gerente Peças", 5, 12, 60)])
        self.assertEqual(l.totais(), {"vendas": 12, "a_receber_colaboradores": Decimal("120"),
                                      "a_receber_gerentes": Decimal("60")})
        self.assertEqual([g.nome for g in l.gerentes], ["G"])
        self.assertEqual(len(l.colaboradores), 2)


class PastaTest(Base):
    def test_duplicado_na_pasta_bloqueia(self):
        criar_planilha(self.pasta / JEEP, [("A", "Consultor", 10, 1, 10)])
        criar_planilha(self.pasta / "VERBAS OUTUBRO TECAR JEEP GOIANIA (1).xlsx",
                       [("A", "Consultor", 10, 1, 10)])
        lotes = ler_pasta(self.pasta, LOJAS, CARGOS, 2026)
        self.assertEqual(len(lotes), 2)
        self.assertTrue(all(any("mesma loja" in e for e in l.erros) for l in lotes),
                        [l.erros for l in lotes])

    def test_ignora_arquivo_temporario_do_excel(self):
        criar_planilha(self.pasta / JEEP, [("A", "Consultor", 10, 1, 10)])
        (self.pasta / ("~$" + JEEP)).write_bytes(b"lock")
        (self.pasta / "leia-me.txt").write_text("x")
        lotes = ler_pasta(self.pasta, LOJAS, CARGOS, 2026)
        self.assertEqual([l.arquivo.name for l in lotes], [JEEP])
        self.assertEqual(lotes[0].erros, [])


if __name__ == "__main__":
    unittest.main()
