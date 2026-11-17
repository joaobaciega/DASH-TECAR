"""Acesso ao MySQL (local e Aiven) sem Streamlit.

Usado pelo atualizar.py, pelo criar_banco.py e pela camada do app (db.py).
As credenciais vêm de .streamlit/secrets.toml, o mesmo arquivo do app:
    [mysql]         banco local (na nuvem, o Aiven)
    [mysql_online]  Aiven, usado só a partir desta máquina
"""

import re
import tomllib
from decimal import Decimal
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

from tecar.config import RAIZ, Cargo, Loja, chave
from tecar.leitura import Lote

SECRETS = RAIZ / ".streamlit" / "secrets.toml"
SCHEMA = RAIZ / "schema.sql"
OBJETOS = ("vw_base", "historico", "lancamentos", "pessoas", "cargos", "lojas")


# ------------------------------------------------------------------ conexão
def ler_secrets(caminho: Path = SECRETS) -> dict:
    with open(caminho, "rb") as fh:
        return tomllib.load(fh)


def online_preenchido(cfg) -> bool:
    """True quando [mysql_online] tem host, porta, usuário, senha e banco."""
    if not cfg:
        return False
    try:
        porta = int(cfg.get("port") or 0)
    except (TypeError, ValueError):
        return False
    return porta > 0 and all(str(cfg.get(c) or "").strip()
                             for c in ("host", "user", "password", "database"))


def destinos(secrets: dict) -> list[tuple[str, dict]]:
    """[('local', cfg)] + [('aiven', cfg)] se o Aiven estiver preenchido."""
    saida = [("local", secrets["mysql"])]
    if online_preenchido(secrets.get("mysql_online")):
        saida.append(("aiven", secrets["mysql_online"]))
    return saida


def criar_engine(cfg: dict, com_banco: bool = True) -> Engine:
    """Engine SQLAlchemy/PyMySQL. `ssl_ca` (caminho relativo à pasta do projeto
    ou absoluto) liga o TLS com verificação do certificado — a Aiven exige."""
    query = {"charset": "utf8mb4"}
    ca = str(cfg.get("ssl_ca") or "").strip()
    if ca:
        caminho = Path(ca)
        query["ssl_ca"] = str(caminho if caminho.is_absolute() else RAIZ / caminho)
    url = URL.create("mysql+pymysql", username=cfg["user"], password=cfg["password"],
                     host=cfg.get("host", "127.0.0.1"), port=int(cfg.get("port", 3306)),
                     database=cfg["database"] if com_banco else None, query=query)
    return create_engine(url, pool_pre_ping=True, pool_recycle=280)


def descrever(cfg: dict) -> str:
    return f"{cfg.get('host')}:{cfg.get('port')} / banco {cfg.get('database')}"


# ------------------------------------------------------------------- schema
def _comandos(sql: str) -> list[str]:
    sem_comentarios = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    return [c.strip() for c in sem_comentarios.split(";") if c.strip()]


def aplicar_schema(cfg: dict, schema: Path = SCHEMA, recriar: bool = False) -> list[str]:
    """Cria o banco (se faltar) e aplica o schema. Devolve tabelas e views."""
    nome = str(cfg["database"])
    if not re.fullmatch(r"[A-Za-z0-9_]+", nome):
        raise ValueError(f"Nome de banco inválido: {nome!r}")
    with criar_engine(cfg, com_banco=False).begin() as c:
        c.execute(text(f"CREATE DATABASE IF NOT EXISTS `{nome}` "
                       "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    eng = criar_engine(cfg)
    with eng.begin() as c:
        if recriar:
            c.execute(text("DROP VIEW IF EXISTS vw_base"))
            for t in OBJETOS[1:]:
                c.execute(text(f"DROP TABLE IF EXISTS {t}"))
        for comando in _comandos(Path(schema).read_text(encoding="utf-8")):
            c.execute(text(comando))
    with eng.connect() as c:
        objetos = [r[0] for r in c.execute(text("SHOW FULL TABLES"))]
    eng.dispose()
    return objetos


# ----------------------------------------------------------------- gravação
def _sincronizar_cadastro(c, lojas: list[Loja], cargos: dict[str, Cargo]) -> dict[str, int]:
    """Lojas (inclusive preço) e cargos do config -> banco. Devolve {chave: id}."""
    for l in lojas:
        c.execute(text(
            "INSERT INTO lojas (chave, nome, marca, cidade, preco_diant, preco_tras) "
            "VALUES (:k, :n, :m, :c, :pd, :pt) ON DUPLICATE KEY UPDATE nome = VALUES(nome), "
            "marca = VALUES(marca), cidade = VALUES(cidade), "
            "preco_diant = VALUES(preco_diant), preco_tras = VALUES(preco_tras)"),
            {"k": l.chave, "n": l.nome, "m": l.marca, "c": l.cidade,
             "pd": l.preco_diant, "pt": l.preco_tras})
    for cg in cargos.values():
        c.execute(text(
            "INSERT INTO cargos (nome, grupo, equipe) VALUES (:n, :g, :e) "
            "ON DUPLICATE KEY UPDATE grupo = VALUES(grupo), equipe = VALUES(equipe)"),
            {"n": cg.nome, "g": cg.grupo, "e": ";".join(cg.equipe) or None})
    return {r[0]: r[1] for r in c.execute(text("SELECT chave, id FROM lojas"))}


def _totais_loja_mes(c, loja_id: int, mes) -> tuple:
    """(vendas dos colaboradores, A RECEBER total) ou (None, None) se não há linhas."""
    r = c.execute(text(
        "SELECT COUNT(*), SUM(CASE WHEN grupo = 'colaborador' THEN refil_diant ELSE 0 END), "
        "SUM(a_receber) FROM lancamentos WHERE loja_id = :l AND mes = :m"),
        {"l": loja_id, "m": mes}).one()
    return (None, None) if not r[0] else (int(r[1]), Decimal(r[2]))


def gravar(engine: Engine, lotes: list[Lote], lojas: list[Loja], cargos: dict[str, Cargo]) -> None:
    """Grava os lotes numa transação só: tudo ou nada.

    Cada loja/mês é APAGADO e regravado (rodar de novo não duplica). Cada lote
    vira uma linha 'importacao' no histórico. O cadastro de lojas/cargos é
    sincronizado mesmo sem lotes (é assim que um preço novo chega ao banco).
    """
    com_erro = [l.arquivo.name for l in lotes if l.erros]
    if com_erro:
        raise ValueError(f"Lotes com erro não podem ser gravados: {', '.join(com_erro)}")
    with engine.begin() as c:
        ids = _sincronizar_cadastro(c, lojas, cargos)
        for lote in lotes:
            loja_id = ids[lote.loja.chave]
            vendas_antes, receber_antes = _totais_loja_mes(c, loja_id, lote.mes)
            c.execute(text("DELETE FROM lancamentos WHERE loja_id = :l AND mes = :m"),
                      {"l": loja_id, "m": lote.mes})
            for ln in lote.linhas:
                c.execute(text(
                    "INSERT INTO pessoas (loja_id, nome, chave) VALUES (:l, :n, :k) "
                    "ON DUPLICATE KEY UPDATE nome = VALUES(nome)"),
                    {"l": loja_id, "n": ln.nome, "k": chave(ln.nome)})
                pessoa_id = c.execute(text(
                    "SELECT id FROM pessoas WHERE loja_id = :l AND chave = :k"),
                    {"l": loja_id, "k": chave(ln.nome)}).scalar_one()
                c.execute(text(
                    "INSERT INTO lancamentos (pessoa_id, loja_id, mes, cargo, grupo, passagens, "
                    "refil_diant, refil_tras, verba, a_receber, origem) VALUES "
                    "(:p, :l, :m, :cargo, :grupo, NULL, :v, 0, :verba, :ar, 'importacao')"),
                    {"p": pessoa_id, "l": loja_id, "m": lote.mes, "cargo": ln.cargo,
                     "grupo": ln.grupo, "v": ln.vendas, "verba": ln.verba, "ar": ln.a_receber})
            t = lote.totais()
            c.execute(text(
                "INSERT INTO historico (tipo, loja, mes, vendas_antes, vendas_depois, "
                "a_receber_antes, a_receber_depois, arquivo, detalhe) VALUES "
                "('importacao', :loja, :m, :va, :vd, :ra, :rd, :arq, :det)"),
                {"loja": lote.loja.nome, "m": lote.mes, "va": vendas_antes, "vd": t["vendas"],
                 "ra": receber_antes,
                 "rd": t["a_receber_colaboradores"] + t["a_receber_gerentes"],
                 "arq": lote.arquivo.name,
                 "det": f"{len(lote.linhas)} pessoas, {len(lote.gerentes)} gerentes"})


# ------------------------------------------------------------------ leitura
def totais_por_loja(engine: Engine, mes) -> dict[str, dict]:
    """Mesmo formato de Lote.totais(), por chave de loja, lido do banco."""
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT lo.chave, "
            "  SUM(CASE WHEN l.grupo = 'colaborador' THEN l.refil_diant ELSE 0 END), "
            "  SUM(CASE WHEN l.grupo = 'colaborador' THEN l.a_receber ELSE 0 END), "
            "  SUM(CASE WHEN l.grupo = 'gerente' THEN l.a_receber ELSE 0 END) "
            "FROM lancamentos l JOIN lojas lo ON lo.id = l.loja_id "
            "WHERE l.mes = :m GROUP BY lo.chave"), {"m": mes}).all()
    return {r[0]: {"vendas": int(r[1]), "a_receber_colaboradores": Decimal(r[2]),
                   "a_receber_gerentes": Decimal(r[3])} for r in rows}


def correcoes_existentes(engine: Engine, loja_chave: str, mes) -> list[str]:
    """Colaboradores com correção manual na loja/mês (a reimportação vai desfazer)."""
    with engine.connect() as c:
        return [r[0] for r in c.execute(text(
            "SELECT p.nome FROM lancamentos l JOIN pessoas p ON p.id = l.pessoa_id "
            "JOIN lojas lo ON lo.id = l.loja_id WHERE lo.chave = :k AND l.mes = :m "
            "AND l.origem = 'correcao' AND l.grupo = 'colaborador' ORDER BY p.nome"),
            {"k": loja_chave, "m": mes})]


_NUMERICAS = ("passagens", "refil_diant", "refil_tras", "aproveitamento", "verba", "a_receber",
              "preco_diant", "preco_tras", "total_diant", "total_tras", "total_geral",
              "vendas_antes", "vendas_depois", "a_receber_antes", "a_receber_depois")


def _tipar(df: pd.DataFrame) -> pd.DataFrame:
    """DECIMAL/None chegam como object: tudo vira float (None -> NaN)."""
    for c in _NUMERICAS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    for c in ("mes", "registrado_em"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c])
    return df


def ler_base(engine: Engine) -> pd.DataFrame:
    with engine.connect() as c:
        df = pd.read_sql(text("SELECT * FROM vw_base ORDER BY mes, loja, pessoa"), c)
    return _tipar(df)


def ler_historico(engine: Engine) -> pd.DataFrame:
    with engine.connect() as c:
        df = pd.read_sql(text("SELECT * FROM historico ORDER BY registrado_em, id"), c)
    return _tipar(df)


# ----------------------------------------------------------------- correção
def salvar_correcao(engine: Engine, loja_id: int, mes, pessoa_id: int, vendas: int) -> list[dict]:
    """Corrige as VENDAS de um colaborador num mês e recalcula os gerentes cuja
    equipe inclui o cargo dele (vendas = soma da equipe; A RECEBER = verba ×
    vendas). Uma transação; cada pessoa alterada vira uma linha no histórico."""
    if isinstance(vendas, bool) or int(vendas) != vendas or vendas < 0:
        raise ValueError("Vendas precisa ser um número inteiro, 0 ou maior.")
    vendas = int(vendas)
    centavo = Decimal("0.01")
    with engine.begin() as c:
        alvo = c.execute(text(
            "SELECT l.id, l.cargo, l.grupo, l.refil_diant, l.verba, l.a_receber, p.nome, "
            "lo.nome FROM lancamentos l JOIN pessoas p ON p.id = l.pessoa_id "
            "JOIN lojas lo ON lo.id = l.loja_id "
            "WHERE l.pessoa_id = :p AND l.loja_id = :l AND l.mes = :m FOR UPDATE"),
            {"p": pessoa_id, "l": loja_id, "m": mes}).one_or_none()
        if alvo is None:
            raise ValueError("Lançamento não encontrado para essa pessoa, loja e mês.")
        lanc_id, cargo, grupo, vendas_antes, verba, receber_antes, nome, loja_nome = alvo
        if grupo != "colaborador":
            raise ValueError("Vendas de gerente não se corrigem direto: são a soma da equipe.")

        def atualizar(lid, pessoa, cg, v_antes, v_depois, verba_, r_antes, detalhe):
            r_depois = (Decimal(verba_) * v_depois).quantize(centavo)
            c.execute(text("UPDATE lancamentos SET refil_diant = :v, a_receber = :r, "
                           "origem = 'correcao' WHERE id = :id"),
                      {"v": v_depois, "r": r_depois, "id": lid})
            c.execute(text(
                "INSERT INTO historico (tipo, loja, mes, pessoa, cargo, vendas_antes, "
                "vendas_depois, a_receber_antes, a_receber_depois, detalhe) VALUES "
                "('correcao', :loja, :m, :p, :cg, :va, :vd, :ra, :rd, :det)"),
                {"loja": loja_nome, "m": mes, "p": pessoa, "cg": cg, "va": v_antes,
                 "vd": v_depois, "ra": r_antes, "rd": r_depois, "det": detalhe})
            return {"pessoa": pessoa, "cargo": cg, "vendas_antes": int(v_antes),
                    "vendas_depois": int(v_depois), "a_receber_antes": Decimal(r_antes),
                    "a_receber_depois": r_depois}

        mudancas = [atualizar(lanc_id, nome, cargo, vendas_antes, vendas, verba, receber_antes,
                              "correção manual (página Lançamento)")]

        colab = c.execute(text(
            "SELECT cargo, refil_diant FROM lancamentos WHERE loja_id = :l AND mes = :m "
            "AND grupo = 'colaborador'"), {"l": loja_id, "m": mes}).all()
        gerentes = c.execute(text(
            "SELECT l.id, p.nome, l.cargo, l.refil_diant, l.verba, l.a_receber, cg.equipe "
            "FROM lancamentos l JOIN pessoas p ON p.id = l.pessoa_id "
            "JOIN cargos cg ON cg.nome = l.cargo "
            "WHERE l.loja_id = :l AND l.mes = :m AND l.grupo = 'gerente' ORDER BY p.nome"),
            {"l": loja_id, "m": mes}).all()
        for gid, gnome, gcargo, gvendas, gverba, greceber, equipe in gerentes:
            membros = {chave(x) for x in (equipe or "").split(";") if x}
            if chave(cargo) not in membros:
                continue
            soma = sum(v for cg, v in colab if chave(cg) in membros)
            mudancas.append(atualizar(gid, gnome, gcargo, gvendas, soma, gverba, greceber,
                                      f"recalculado: soma da equipe após correção de {nome}"))
    return mudancas
