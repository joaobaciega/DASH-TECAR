"""Gravação idempotente, totais, correção manual e leituras (MySQL local de teste)."""

import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from tecar import banco
from tecar.config import carregar_cargos, carregar_lojas
from tecar.leitura import ler_pasta
from tests.apoio_banco import banco_limpo, precisa_mysql
from tests.fabrica import DADOS_OUTUBRO

from tests.fabrica import pessoas_outubro

P = pessoas_outubro()   # nomes reais lidos de tests/dados (fora do Git)

OUT = date(2026, 10, 1)
LOJAS = carregar_lojas()
CARGOS = carregar_cargos()


def _escalar(eng, sql, **p):
    with eng.connect() as c:
        return c.execute(text(sql), p).scalar()


def _pessoa(eng, nome):
    return _escalar(eng, "SELECT id FROM pessoas WHERE nome = :n", n=nome)


def _loja_id(eng, chave):
    return _escalar(eng, "SELECT id FROM lojas WHERE chave = :c", c=chave)


def _lanc(eng, nome):
    with eng.connect() as c:
        return c.execute(text("SELECT l.refil_diant, l.a_receber FROM lancamentos l "
                              "JOIN pessoas p ON p.id = l.pessoa_id WHERE p.nome = :n"),
                         {"n": nome}).one()


@precisa_mysql
@unittest.skipUnless(DADOS_OUTUBRO.exists(), "cópias de outubro ausentes")
class GravacaoTest(unittest.TestCase):
    def setUp(self):
        self.eng = banco_limpo()
        self.lotes = ler_pasta(DADOS_OUTUBRO, LOJAS, CARGOS, 2026)
        banco.gravar(self.eng, self.lotes, LOJAS, CARGOS)

    def tearDown(self):
        self.eng.dispose()

    def test_gravar_e_totais_outubro(self):
        totais = banco.totais_por_loja(self.eng, OUT)
        self.assertEqual(totais, {l.loja.chave: l.totais() for l in self.lotes})
        self.assertEqual(sum(t["vendas"] for t in totais.values()), 104)

    def test_gravar_duas_vezes_nao_duplica(self):
        banco.gravar(self.eng, self.lotes, LOJAS, CARGOS)
        self.assertEqual(_escalar(self.eng, "SELECT COUNT(*) FROM lancamentos"), 27)
        self.assertEqual(_escalar(self.eng, "SELECT COUNT(*) FROM pessoas"), 27)
        self.assertEqual(banco.totais_por_loja(self.eng, OUT),
                         {l.loja.chave: l.totais() for l in self.lotes})
        self.assertEqual(_escalar(self.eng, "SELECT COUNT(*) FROM historico "
                                            "WHERE tipo = 'importacao'"), 8)
        self.assertEqual(_escalar(self.eng, "SELECT vendas_antes FROM historico "
                                            "WHERE loja = 'Jeep Goiânia' ORDER BY id DESC LIMIT 1"), 20)

    def test_faturamento_padrao_199(self):
        base = banco.ler_base(self.eng)
        self.assertEqual(base.loc[base.pessoa == P["consultor_jeep"], "total_geral"].item(), 1592.0)
        colab = base[base.grupo == "colaborador"]
        self.assertEqual(colab["total_geral"].sum(), 20696.0)
        self.assertEqual(set(colab["mes_label"]), {"10/2026"})
        self.assertTrue(colab["passagens"].isna().all())
        self.assertTrue(colab["aproveitamento"].isna().all())
        self.assertEqual(len(base), 27)

    def test_sincroniza_preco(self):
        lojas = [replace(l, preco_diant=Decimal("30")) if l.chave == "JEEP GOIANIA"
                 else replace(l, preco_diant=None) if l.chave == "MERCEDES BRASILIA" else l
                 for l in LOJAS]
        banco.gravar(self.eng, [], lojas, CARGOS)
        base = banco.ler_base(self.eng)
        self.assertEqual(base.loc[base.pessoa == P["consultor_jeep"], "total_geral"].item(), 240.0)
        self.assertTrue(base.loc[base.loja == "Mercedes Brasília", "total_geral"].isna().all())

    def test_correcao_recalcula_gerentes(self):
        mud = banco.salvar_correcao(self.eng, _loja_id(self.eng, "JEEP GOIANIA"), OUT,
                                    _pessoa(self.eng, P["consultor_jeep"]), 10)
        self.assertEqual(len(mud), 3)
        self.assertEqual(mud[0], {"pessoa": P["consultor_jeep"], "cargo": "Consultor",
                                  "vendas_antes": 8, "vendas_depois": 10,
                                  "a_receber_antes": Decimal("80.00"),
                                  "a_receber_depois": Decimal("100.00")})
        self.assertEqual(_lanc(self.eng, P["consultor_jeep"]), (10, Decimal("100.00")))
        self.assertEqual(_lanc(self.eng, P["gerente_pecas_jeep"]), (22, Decimal("110.00")))
        self.assertEqual(_lanc(self.eng, P["gerente_pos_jeep"]), (22, Decimal("110.00")))
        self.assertEqual(banco.totais_por_loja(self.eng, OUT)["JEEP GOIANIA"]["vendas"], 22)
        self.assertEqual(_escalar(self.eng, "SELECT COUNT(*) FROM historico WHERE tipo='correcao'"), 3)
        self.assertEqual(banco.correcoes_existentes(self.eng, "JEEP GOIANIA", OUT),
                         [P["consultor_jeep"]])

    def test_correcao_consultor_nao_mexe_chefe_oficina(self):
        mud = banco.salvar_correcao(self.eng, _loja_id(self.eng, "MERCEDES GOIANIA"), OUT,
                                    _pessoa(self.eng, P["consultor_mgo"]), 6)
        self.assertEqual([m["pessoa"] for m in mud], [P["consultor_mgo"]])
        self.assertEqual(_lanc(self.eng, P["chefe_mgo"])[0], 19)

    def test_correcao_tecnico_recalcula_chefe_oficina(self):
        banco.salvar_correcao(self.eng, _loja_id(self.eng, "MERCEDES GOIANIA"), OUT,
                              _pessoa(self.eng, P["tecnico_zero_mgo"]), 2)
        self.assertEqual(_lanc(self.eng, P["chefe_mgo"]), (21, Decimal("105.00")))

    def test_correcao_de_gerente_recusada(self):
        with self.assertRaises(ValueError):
            banco.salvar_correcao(self.eng, _loja_id(self.eng, "JEEP GOIANIA"), OUT,
                                  _pessoa(self.eng, P["gerente_pecas_jeep"]), 5)

    def test_correcao_vendas_negativa_recusada(self):
        with self.assertRaises(ValueError):
            banco.salvar_correcao(self.eng, _loja_id(self.eng, "JEEP GOIANIA"), OUT,
                                  _pessoa(self.eng, P["consultor_jeep"]), -1)

    def test_reimportar_substitui_correcao(self):
        banco.salvar_correcao(self.eng, _loja_id(self.eng, "JEEP GOIANIA"), OUT,
                              _pessoa(self.eng, P["consultor_jeep"]), 10)
        banco.gravar(self.eng, self.lotes, LOJAS, CARGOS)
        self.assertEqual(banco.totais_por_loja(self.eng, OUT)["JEEP GOIANIA"]["vendas"], 20)
        self.assertEqual(banco.correcoes_existentes(self.eng, "JEEP GOIANIA", OUT), [])

    def test_ler_historico(self):
        h = banco.ler_historico(self.eng)
        self.assertEqual(len(h), 4)
        self.assertEqual(set(h["tipo"]), {"importacao"})
        self.assertEqual(h["vendas_depois"].sum(), 104)


if __name__ == "__main__":
    unittest.main()
