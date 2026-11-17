"""Conexões, destinos e aplicação do schema (só no MySQL local de teste)."""

import unittest

from sqlalchemy import text

from tecar import banco
from tests.apoio_banco import banco_limpo, cfg_teste, precisa_mysql

ONLINE_OK = {"host": "x.aivencloud.com", "port": 123, "user": "u", "password": "p",
             "database": "dashboard_tecar"}


class DestinosTest(unittest.TestCase):
    def test_online_preenchido(self):
        self.assertFalse(banco.online_preenchido(None))
        self.assertFalse(banco.online_preenchido({"host": "", "port": 0, "user": "", "password": "",
                                                  "database": "dashboard_tecar"}))
        self.assertTrue(banco.online_preenchido(ONLINE_OK))
        self.assertFalse(banco.online_preenchido({**ONLINE_OK, "port": 0}))

    def test_destinos_sem_online(self):
        local = {"host": "127.0.0.1"}
        self.assertEqual(banco.destinos({"mysql": local, "mysql_online": {"host": ""}}),
                         [("local", local)])
        self.assertEqual([d for d, _ in banco.destinos({"mysql": local, "mysql_online": ONLINE_OK})],
                         ["local", "aiven"])

    def test_ssl_ca_relativo_vai_para_connect_args(self):
        eng = banco.criar_engine({**ONLINE_OK, "ssl_ca": "certs/aiven-ca.pem"})
        self.assertEqual(eng.dialect.create_connect_args(eng.url)[1]["ssl"]["ca"],
                         str(banco.RAIZ / "certs" / "aiven-ca.pem"))
        eng = banco.criar_engine({**ONLINE_OK, "ssl_ca": ""})
        self.assertNotIn("ssl", eng.dialect.create_connect_args(eng.url)[1])


@precisa_mysql
class SchemaTest(unittest.TestCase):
    def test_aplicar_schema_cria_objetos(self):
        banco_limpo()
        objetos = banco.aplicar_schema(cfg_teste())
        self.assertTrue({"lojas", "cargos", "pessoas", "lancamentos", "historico",
                         "vw_base"} <= set(objetos), objetos)

    def test_aplicar_schema_idempotente(self):
        eng = banco_limpo()
        with eng.begin() as c:
            c.execute(text("INSERT INTO lojas (chave, nome, marca, cidade) "
                           "VALUES ('X', 'X', 'M', 'C')"))
        banco.aplicar_schema(cfg_teste())
        with eng.connect() as c:
            self.assertEqual(c.execute(text("SELECT COUNT(*) FROM lojas")).scalar(), 1)


if __name__ == "__main__":
    unittest.main()
