"""Cria o banco do dashboard e as tabelas, sem precisar escrever SQL.

    python criar_banco.py              banco LOCAL  (seção [mysql] do secrets)
    python criar_banco.py --online     banco da AIVEN (seção [mysql_online])
    python criar_banco.py --recriar    APAGA as tabelas e cria de novo (pede confirmação)

Rodar de novo sem --recriar não apaga nada: só cria o que estiver faltando.
"""

import argparse
import sys

from tecar import banco


def main(argv=None, entrada=input) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Cria o banco do dashboard Grupo TECAR.")
    p.add_argument("--online", action="store_true", help="cria no Aiven ([mysql_online])")
    p.add_argument("--recriar", action="store_true", help="APAGA as tabelas e recria")
    args = p.parse_args(argv)

    try:
        secrets = banco.ler_secrets()
    except FileNotFoundError:
        print(f"Não achei {banco.SECRETS}. Copie secrets.example.toml para secrets.toml "
              "e preencha (veja o README).")
        return 1

    if args.online:
        cfg = secrets.get("mysql_online")
        if not banco.online_preenchido(cfg):
            print("A seção [mysql_online] do .streamlit/secrets.toml não está preenchida "
                  "(host, port, user, password, database). Preencha com os dados da Aiven "
                  "e rode de novo.")
            return 1
        rotulo = "AIVEN"
    else:
        cfg = secrets["mysql"]
        rotulo = "LOCAL"

    print(f"Banco {rotulo}: {banco.descrever(cfg)}")
    if args.recriar:
        resp = entrada("Isto APAGA todos os dados do dashboard neste banco. "
                       "Digite APAGAR para continuar: ")
        if resp.strip() != "APAGAR":
            print("Cancelado. Nada foi alterado.")
            return 1

    try:
        objetos = banco.aplicar_schema(cfg, recriar=args.recriar)
    except Exception as e:
        print(f"ERRO ao criar o banco {rotulo}: {type(e).__name__}: {e}")
        return 1
    print("Tabelas e views prontas: " + ", ".join(sorted(objetos)))
    print("OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
