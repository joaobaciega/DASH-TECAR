"""Leitura de config/lojas.toml e config/cargos.toml.

Os dois arquivos são editados à mão pelo usuário; por isso toda inconsistência
vira `ConfigInvalida` com uma mensagem que diz o que corrigir, em vez de um
erro do Python no meio da importação.
"""

import re
import tomllib
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
GRUPOS = ("colaborador", "gerente")


class ConfigInvalida(Exception):
    """Erro de preenchimento em config/lojas.toml ou config/cargos.toml."""


@dataclass(frozen=True)
class Loja:
    chave: str
    nome: str
    marca: str
    cidade: str
    preco_diant: Decimal | None
    preco_tras: Decimal | None


@dataclass(frozen=True)
class Cargo:
    nome: str
    grupo: str
    equipe: tuple[str, ...] = ()


def chave(texto) -> str:
    """Texto comparável: sem acento, maiúsculo, espaços colapsados.

    "Técnico ", "TECNICO" e "tecnico" viram todos "TECNICO".
    """
    if texto is None:
        return ""
    s = unicodedata.normalize("NFKD", str(texto).replace("\xa0", " "))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().upper()


def _ler_toml(caminho: Path) -> dict:
    try:
        with open(caminho, "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        raise ConfigInvalida(f"Arquivo de configuração não encontrado: {caminho}")
    except tomllib.TOMLDecodeError as e:
        raise ConfigInvalida(f"{caminho.name} tem um erro de digitação: {e}")


def _preco(valor, onde: str) -> Decimal | None:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    texto = str(valor).strip().replace("R$", "").strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        preco = Decimal(texto)
    except InvalidOperation:
        raise ConfigInvalida(f"{onde}: preço '{valor}' não é um número (use 199 ou \"199,90\").")
    if preco < 0:
        raise ConfigInvalida(f"{onde}: preço '{valor}' negativo.")
    return preco


def carregar_lojas(caminho: Path = RAIZ / "config" / "lojas.toml") -> list[Loja]:
    caminho = Path(caminho)
    dados = _ler_toml(caminho).get("loja", [])
    if not dados:
        raise ConfigInvalida(f"{caminho.name} não tem nenhuma seção [[loja]].")
    lojas, vistas = [], set()
    for i, d in enumerate(dados, 1):
        onde = f"{caminho.name}, loja nº {i}"
        faltando = [c for c in ("arquivo", "nome", "marca", "cidade") if not str(d.get(c, "")).strip()]
        if faltando:
            raise ConfigInvalida(f"{onde}: preencha {', '.join(faltando)}.")
        k = chave(d["arquivo"])
        if k in vistas:
            raise ConfigInvalida(f"{onde}: arquivo '{d['arquivo']}' repetido.")
        vistas.add(k)
        lojas.append(Loja(chave=k, nome=str(d["nome"]).strip(), marca=str(d["marca"]).strip(),
                          cidade=str(d["cidade"]).strip(),
                          preco_diant=_preco(d.get("preco_diant"), f"{onde} ({d['nome']})"),
                          preco_tras=_preco(d.get("preco_tras"), f"{onde} ({d['nome']})")))
    return lojas


def carregar_cargos(caminho: Path = RAIZ / "config" / "cargos.toml") -> dict[str, Cargo]:
    caminho = Path(caminho)
    dados = _ler_toml(caminho).get("cargo", [])
    if not dados:
        raise ConfigInvalida(f"{caminho.name} não tem nenhuma seção [[cargo]].")
    cargos: dict[str, Cargo] = {}
    for i, d in enumerate(dados, 1):
        nome = re.sub(r"\s+", " ", str(d.get("nome", ""))).strip()
        grupo = str(d.get("grupo", "")).strip().lower()
        onde = f"{caminho.name}, cargo '{nome or i}'"
        if not nome:
            raise ConfigInvalida(f"{caminho.name}, cargo nº {i}: preencha o nome.")
        if grupo not in GRUPOS:
            raise ConfigInvalida(f"{onde}: grupo '{d.get('grupo')}' inválido; use "
                                 "\"colaborador\" ou \"gerente\".")
        if chave(nome) in cargos:
            raise ConfigInvalida(f"{onde}: cargo repetido.")
        cargos[chave(nome)] = Cargo(nome=nome, grupo=grupo, equipe=tuple(d.get("equipe", [])))
    for c in cargos.values():
        if c.grupo == "gerente" and not c.equipe:
            raise ConfigInvalida(f"{caminho.name}, cargo '{c.nome}': gerente precisa de equipe = [...].")
        if c.grupo == "colaborador" and c.equipe:
            raise ConfigInvalida(f"{caminho.name}, cargo '{c.nome}': só gerente tem equipe.")
        canonicos = []
        for membro in c.equipe:
            alvo = cargos.get(chave(membro))
            if alvo is None or alvo.grupo != "colaborador":
                raise ConfigInvalida(f"{caminho.name}, cargo '{c.nome}': a equipe cita "
                                     f"'{membro}', que não é um cargo de colaborador da lista.")
            canonicos.append(alvo.nome)
        if c.equipe:
            cargos[chave(c.nome)] = Cargo(c.nome, c.grupo, tuple(canonicos))
    return cargos
