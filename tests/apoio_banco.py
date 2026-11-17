"""Banco de TESTE: `dashboard_tecar_teste` no MySQL LOCAL.

Os testes nunca tocam o Aiven nem o `dashboard_tecar` de verdade: o host é
conferido aqui e o nome do banco é sempre trocado.
"""

import unittest

from tecar import banco

BANCO_TESTE = "dashboard_tecar_teste"
HOSTS_LOCAIS = {"127.0.0.1", "localhost", "::1"}


def cfg_teste() -> dict:
    cfg = dict(banco.ler_secrets()["mysql"])
    assert str(cfg.get("host")) in HOSTS_LOCAIS, "Testes só rodam contra o MySQL local."
    cfg["database"] = BANCO_TESTE
    return cfg


def mysql_disponivel() -> bool:
    try:
        with banco.criar_engine(cfg_teste(), com_banco=False).connect():
            return True
    except Exception:
        return False


def banco_limpo():
    """Recria as tabelas do banco de teste e devolve a engine."""
    cfg = cfg_teste()
    banco.aplicar_schema(cfg, recriar=True)
    return banco.criar_engine(cfg)


precisa_mysql = unittest.skipUnless(mysql_disponivel(), "MySQL local indisponível")
