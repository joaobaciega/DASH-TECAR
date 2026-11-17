"""Fluxo mensal `atualizar.py` ponta a ponta, contra o MySQL LOCAL de teste.

O "online" destes testes é vazio ou 127.0.0.1:1 (inalcançável) — nunca o Aiven.
"""

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import text

import atualizar
from tecar import banco
from tests.apoio_banco import banco_limpo, cfg_teste, precisa_mysql
from tests.fabrica import DADOS_OUTUBRO, criar_planilha

from tests.fabrica import pessoas_outubro

P = pessoas_outubro()   # nomes reais lidos de tests/dados (fora do Git)

OUT = date(2026, 10, 1)


def _toml_secao(nome, cfg):
    linhas = [f"[{nome}]"]
    for k, v in cfg.items():
        linhas.append(f"{k} = {v}" if isinstance(v, int) else f'{k} = "{v}"')
    return "\n".join(linhas) + "\n"


@precisa_mysql
@unittest.skipUnless(DADOS_OUTUBRO.exists(), "cópias de outubro ausentes")
class AtualizarTest(unittest.TestCase):
    def setUp(self):
        self.eng = banco_limpo()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.entrada = self.tmp / "entrada"
        self.entrada.mkdir()
        self.saida = self.tmp / "conferencias"
        self.saida.mkdir()
        self.espelho = self.tmp / "BASE GRUPO TECAR.xlsx"
        self.secrets(online={"host": "", "port": 0, "user": "", "password": "",
                             "database": "dashboard_tecar_teste"})

    def tearDown(self):
        self.eng.dispose()
        self._tmp.cleanup()

    def secrets(self, online):
        caminho = self.tmp / "secrets.toml"
        caminho.write_text(_toml_secao("mysql", cfg_teste()) + _toml_secao("mysql_online", online),
                           encoding="utf-8")
        self.caminho_secrets = caminho

    def copiar_outubro(self):
        for p in DADOS_OUTUBRO.glob("*.xlsx"):
            shutil.copy(p, self.entrada / p.name)

    def rodar(self, *extra, entrada=lambda _: "s"):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = atualizar.main(["--ano", "2026", "--pasta", str(self.entrada),
                                 "--secrets", str(self.caminho_secrets),
                                 "--espelho", str(self.espelho),
                                 "--conferencias", str(self.saida), *extra], entrada=entrada)
        return rc, buf.getvalue()

    def contar(self):
        with self.eng.connect() as c:
            return c.execute(text("SELECT COUNT(*) FROM lancamentos")).scalar()

    def test_bloqueio_nao_grava(self):
        self.copiar_outubro()
        criar_planilha(self.entrada / "VERBAS NOVEMBRO TECAR JEEP GOIANIA.xlsx",
                       [("A", "Consultor", 10, 1, 10), ("B", "Estagiário", 5, 1, 5)])
        rc, out = self.rodar("--sim")
        self.assertEqual(rc, 1, out)
        self.assertIn("BLOQUEADA", out)
        self.assertIn("linha 3", out)
        self.assertEqual(self.contar(), 0)

    def test_cancelar_na_confirmacao(self):
        self.copiar_outubro()
        rc, out = self.rodar(entrada=lambda _: "n")
        self.assertEqual(rc, 1, out)
        self.assertIn("Jeep Goiânia", out)          # a prévia apareceu
        self.assertEqual(self.contar(), 0)

    def test_outubro_sim_grava_e_confere(self):
        self.copiar_outubro()
        rc, out = self.rodar("--sim")
        self.assertEqual(rc, 0, out)
        self.assertIn("Aiven não configurado", out)
        self.assertIn("banco local OK", out)
        self.assertIn("104", out)
        self.assertIn("R$ 1.605,00", out)
        self.assertIn("R$ 20.696,00", out)
        self.assertTrue((self.saida / "conferencia_2026-10.xlsx").exists())
        self.assertTrue(self.espelho.exists())
        self.assertEqual(self.contar(), 27)

    def test_duas_execucoes_mesmos_totais(self):
        self.copiar_outubro()
        self.rodar("--sim")
        primeiro = banco.totais_por_loja(self.eng, OUT)
        rc, out = self.rodar("--sim")
        self.assertEqual(rc, 0, out)
        self.assertEqual(banco.totais_por_loja(self.eng, OUT), primeiro)
        self.assertEqual(self.contar(), 27)

    def test_aviso_de_correcao_que_sera_substituida(self):
        self.copiar_outubro()
        self.rodar("--sim")
        with self.eng.connect() as c:
            loja, pessoa = c.execute(text(
                "SELECT l.loja_id, l.pessoa_id FROM lancamentos l JOIN pessoas p "
                "ON p.id = l.pessoa_id WHERE p.nome = :n"), {"n": P["consultor_jeep"]}).one()
        banco.salvar_correcao(self.eng, loja, OUT, pessoa, 10)
        rc, out = self.rodar(entrada=lambda _: "n")
        self.assertIn("correção manual", out)
        self.assertIn(P["consultor_jeep"], out)

    def test_aiven_falha_grava_so_local(self):
        self.secrets(online={**cfg_teste(), "host": "127.0.0.1", "port": 1})
        self.copiar_outubro()
        rc, out = self.rodar("--sim")
        self.assertEqual(rc, 0, out)
        self.assertIn("Aiven FALHOU", out)
        self.assertIn("SÓ no banco local", out)
        self.assertEqual(self.contar(), 27)

    def test_espelho_aberto(self):
        self.copiar_outubro()
        with patch.object(atualizar, "escrever_espelho", side_effect=PermissionError("aberto")):
            rc, out = self.rodar("--sim")
        self.assertEqual(rc, 0, out)
        self.assertIn("feche o arquivo", out)
        self.assertEqual(self.contar(), 27)

    def test_falha_ao_conferir_aiven_nao_derruba(self):
        # "online" = o próprio banco local de TESTE (nunca o Aiven); a 2ª leitura falha
        self.secrets(online=cfg_teste())
        self.copiar_outubro()
        real, chamadas = banco.totais_por_loja, []

        def falha_na_segunda(eng, mes):
            chamadas.append(1)
            if len(chamadas) == 2:
                raise RuntimeError("conexão caiu")
            return real(eng, mes)

        with patch.object(atualizar.banco, "totais_por_loja", side_effect=falha_na_segunda):
            rc, out = self.rodar("--sim")
        self.assertEqual(rc, 0, out)
        self.assertIn("não consegui ler de volta", out)
        self.assertTrue((self.saida / "conferencia_2026-10.xlsx").exists())
        self.assertTrue(self.espelho.exists())

    def test_espelho_oserror(self):
        self.copiar_outubro()
        with patch.object(atualizar, "escrever_espelho", side_effect=OSError("arquivo travado")):
            rc, out = self.rodar("--sim")
        self.assertEqual(rc, 0, out)
        self.assertIn("não consegui escrever", out)
        self.assertEqual(self.contar(), 27)

    def test_pasta_vazia_sincroniza_cadastro(self):
        rc, out = self.rodar("--sim")
        self.assertEqual(rc, 0, out)
        self.assertIn("Nenhum arquivo", out)
        with self.eng.connect() as c:
            self.assertEqual(c.execute(text("SELECT COUNT(*) FROM lojas")).scalar(), 4)


if __name__ == "__main__":
    unittest.main()
