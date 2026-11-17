"""Configuração de lojas e cargos (config/lojas.toml e config/cargos.toml)."""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from tecar.config import ConfigInvalida, carregar_cargos, carregar_lojas, chave


def _toml(texto):
    pasta = tempfile.mkdtemp()
    caminho = Path(pasta) / "x.toml"
    caminho.write_text(texto, encoding="utf-8")
    return caminho


class ChaveTest(unittest.TestCase):
    def test_chave_normaliza(self):
        self.assertEqual(chave(" Técnico "), "TECNICO")
        self.assertEqual(chave("TECNICO"), "TECNICO")
        self.assertEqual(chave("Gerente  Peças"), "GERENTE PECAS")
        self.assertEqual(chave(None), "")


class LojasTest(unittest.TestCase):
    def test_lojas_padrao(self):
        lojas = carregar_lojas()
        self.assertEqual([l.nome for l in lojas],
                         ["Jeep Goiânia", "Mercedes Brasília", "Mercedes Goiânia",
                          "Mercedes Uberlândia"])
        self.assertTrue(all(l.preco_diant == Decimal("199") for l in lojas))
        self.assertTrue(all(l.preco_tras is None for l in lojas))
        self.assertEqual(lojas[0].chave, "JEEP GOIANIA")

    def test_preco_texto_virgula(self):
        p = _toml('[[loja]]\narquivo="X"\nnome="X"\nmarca="M"\ncidade="C"\n'
                  'preco_diant = "12,50"\npreco_tras = ""\n')
        self.assertEqual(carregar_lojas(p)[0].preco_diant, Decimal("12.50"))

    def test_preco_invalido(self):
        p = _toml('[[loja]]\narquivo="X"\nnome="X"\nmarca="M"\ncidade="C"\n'
                  'preco_diant = "doze"\n')
        with self.assertRaises(ConfigInvalida) as ctx:
            carregar_lojas(p)
        self.assertIn("doze", str(ctx.exception))


class CargosTest(unittest.TestCase):
    def test_cargos_padrao(self):
        cargos = carregar_cargos()
        grupos = {c.nome: c.grupo for c in cargos.values()}
        self.assertEqual(grupos, {
            "Consultor": "colaborador", "Vendedor de Peças": "colaborador",
            "Técnico": "colaborador", "Gerente Peças": "gerente",
            "Gerente Pós Vendas": "gerente", "Chefe de oficina": "gerente"})
        self.assertEqual(cargos["GERENTE PECAS"].equipe, ("Consultor", "Vendedor de Peças"))
        self.assertEqual(cargos["CHEFE DE OFICINA"].equipe, ("Técnico",))

    def test_equipe_com_cargo_inexistente(self):
        p = _toml('[[cargo]]\nnome="Chefe"\ngrupo="gerente"\nequipe=["Mecânico"]\n')
        with self.assertRaises(ConfigInvalida) as ctx:
            carregar_cargos(p)
        self.assertIn("Mecânico", str(ctx.exception))

    def test_grupo_desconhecido(self):
        p = _toml('[[cargo]]\nnome="Estagiário"\ngrupo="aprendiz"\n')
        with self.assertRaises(ConfigInvalida) as ctx:
            carregar_cargos(p)
        self.assertIn("aprendiz", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
