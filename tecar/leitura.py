"""Leitura das planilhas mensais de verbas ("VERBAS <MÊS> TECAR <LOJA>.xlsx").

Cada arquivo vira um `Lote`: as linhas lidas, os ERROS (bloqueiam a gravação
de todos os arquivos) e os AVISOS (só informam). Nada aqui grava em banco.

Colunas esperadas: NOME | CARGO | VERBA | VENDAS | A RECEBER, com o cabeçalho
em qualquer uma das 10 primeiras linhas. Os valores vêm do cache do Excel
(`data_only=True`): é o número que o usuário vê na planilha.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook

from tecar.config import Cargo, Loja, chave

MESES = {"JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6,
         "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11,
         "DEZEMBRO": 12}
COLUNAS = ("NOME", "CARGO", "VERBA", "VENDAS", "A RECEBER")
PADRAO_NOME = "VERBAS <MÊS> TECAR <LOJA>.xlsx (ex.: VERBAS OUTUBRO TECAR JEEP GOIANIA.xlsx)"
TOLERANCIA = Decimal("0.005")
CENTAVO = Decimal("0.01")


@dataclass
class Linha:
    linha: int
    nome: str
    cargo: str
    grupo: str
    verba: Decimal
    vendas: int
    a_receber: Decimal


@dataclass
class Lote:
    arquivo: Path
    loja: Loja | None
    mes: date | None
    linhas: list[Linha] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def colaboradores(self) -> list[Linha]:
        return [l for l in self.linhas if l.grupo == "colaborador"]

    @property
    def gerentes(self) -> list[Linha]:
        return [l for l in self.linhas if l.grupo == "gerente"]

    def totais(self) -> dict:
        """Vendas só dos colaboradores (as do gerente repetem as da equipe);
        A RECEBER separado em colaboradores e gerentes."""
        return {
            "vendas": sum(l.vendas for l in self.colaboradores),
            "a_receber_colaboradores": sum((l.a_receber for l in self.colaboradores), Decimal("0")),
            "a_receber_gerentes": sum((l.a_receber for l in self.gerentes), Decimal("0")),
        }


def _brl(v: Decimal) -> str:
    return ("R$ {:,.2f}".format(v)).replace(",", "X").replace(".", ",").replace("X", ".")


def _sem_marca_de_copia(texto: str) -> str:
    """'JEEP GOIANIA (1)' / 'JEEP GOIANIA - COPIA' -> 'JEEP GOIANIA'."""
    texto = re.sub(r"\s*\(\d+\)\s*$", "", texto)
    return re.sub(r"\s*-?\s*COPIA(\s*\(?\d+\)?)?\s*$", "", texto).strip()


def identificar_arquivo(nome: str, lojas: list[Loja], ano: int):
    """(mês, loja, erros) a partir do nome do arquivo."""
    erros = []
    partes = chave(Path(nome).stem).split(" ")
    if partes and partes[0] == "VERBAS":
        partes = partes[1:]
    if "TECAR" in partes:
        i = partes.index("TECAR")
        mes_txt, loja_txt = " ".join(partes[:i]), " ".join(partes[i + 1:])
    else:
        mes_txt, loja_txt = (partes[0] if partes else ""), ""
    loja_txt = _sem_marca_de_copia(loja_txt)

    mes = None
    if mes_txt in MESES:
        mes = date(ano, MESES[mes_txt], 1)
    else:
        erros.append(f"{nome}: mês ilegível no nome do arquivo ('{mes_txt}'). "
                     f"O nome precisa seguir o padrão {PADRAO_NOME}.")

    loja = next((l for l in lojas if l.chave == loja_txt), None) if loja_txt else None
    if loja is None:
        cadastradas = ", ".join(l.chave for l in lojas)
        if loja_txt:
            erros.append(f"{nome}: a loja '{loja_txt}' não está em config/lojas.toml "
                         f"(cadastradas: {cadastradas}). Corrija o nome do arquivo ou "
                         "cadastre a loja.")
        else:
            erros.append(f"{nome}: não encontrei a loja no nome do arquivo. O nome precisa "
                         f"seguir o padrão {PADRAO_NOME}.")
    return mes, loja, erros


def _numero(valor):
    """Decimal, None (célula vazia) ou False (não é número)."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, bool):
        return False
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))
    texto = str(valor).replace("R$", "").replace("\xa0", "").strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return False


def _achar_cabecalho(wb):
    """(planilha, nº da linha do cabeçalho, {coluna: índice}) ou None."""
    for ws in wb.worksheets:
        for r, linha in enumerate(ws.iter_rows(min_row=1, max_row=10, values_only=True), 1):
            nomes = [chave(v) for v in linha]
            if "NOME" in nomes and "CARGO" in nomes:
                if all(c in nomes for c in COLUNAS):
                    return ws, r, {c: nomes.index(c) for c in COLUNAS}
                return ws, r, None
    return None


def ler_arquivo(caminho: Path, lojas: list[Loja], cargos: dict[str, Cargo], ano: int) -> Lote:
    caminho = Path(caminho)
    arq = caminho.name
    mes, loja, erros = identificar_arquivo(arq, lojas, ano)
    lote = Lote(arquivo=caminho, loja=loja, mes=mes, erros=erros)

    try:
        wb = load_workbook(caminho, data_only=True)
        wb_formulas = load_workbook(caminho, data_only=False)
    except Exception as e:  # arquivo corrompido, protegido por senha etc.
        lote.erros.append(f"{arq}: não consegui abrir o arquivo ({type(e).__name__}: {e}).")
        return lote

    achado = _achar_cabecalho(wb)
    if achado is None or achado[2] is None:
        lote.erros.append(f"{arq}: cabeçalho {' | '.join(COLUNAS)} não encontrado nas 10 "
                          "primeiras linhas.")
        return lote
    ws, linha_cab, col = achado
    ws_formulas = wb_formulas[ws.title]
    numericas = ("VERBA", "VENDAS", "A RECEBER")

    vistos: dict[str, int] = {}
    for n, valores in enumerate(ws.iter_rows(min_row=linha_cab + 1, values_only=True),
                                linha_cab + 1):
        valores = tuple(valores) + (None,) * (max(col.values()) + 1 - len(valores))
        nome_raw, cargo_raw = valores[col["NOME"]], valores[col["CARGO"]]
        nome = re.sub(r"\s+", " ", str(nome_raw or "").replace("\xa0", " ")).strip()
        cargo_txt = re.sub(r"\s+", " ", str(cargo_raw or "")).strip()
        if not nome and not cargo_txt:
            if any(valores[col[c]] not in (None, "") for c in numericas):
                lote.erros.append(f"{arq}, linha {n}: há valores em VERBA/VENDAS/A RECEBER, "
                                  "mas NOME e CARGO estão vazios. Preencha ou apague a linha.")
            continue                                   # linha vazia
        onde = f"{arq}, linha {n}" + (f" ({nome})" if nome else "")
        problemas = []
        sem_calculo = [c for c in numericas if valores[col[c]] is None
                       and str(ws_formulas.cell(n, col[c] + 1).value or "").startswith("=")]
        if sem_calculo:
            lote.erros.append(f"{onde}: {', '.join(sem_calculo)} tem fórmula sem valor calculado "
                              "(o arquivo foi salvo por um programa que não calcula). Abra no "
                              "Excel, salve e copie de novo para a pasta entrada.")
            continue
        if not nome:
            problemas.append(f"{onde}: NOME vazio.")
        cargo = cargos.get(chave(cargo_txt))
        if cargo is None:
            problemas.append(f"{onde}: cargo '{cargo_txt}' não está em config/cargos.toml "
                             f"(cadastrados: {', '.join(c.nome for c in cargos.values())}). "
                             "Inclua o cargo lá e rode de novo.")

        verba = _numero(valores[col["VERBA"]])
        vendas = _numero(valores[col["VENDAS"]])
        a_receber = _numero(valores[col["A RECEBER"]])
        for rotulo, v, bruto in (("VERBA", verba, valores[col["VERBA"]]),
                                 ("VENDAS", vendas, valores[col["VENDAS"]]),
                                 ("A RECEBER", a_receber, valores[col["A RECEBER"]])):
            if v is False:
                problemas.append(f"{onde}: {rotulo} '{bruto}' não é um número.")
        if verba is None:
            verba = Decimal("0")
            lote.avisos.append(f"{onde}: VERBA vazia, considerada 0.")
        if vendas is None:
            vendas = Decimal("0")
            lote.avisos.append(f"{onde}: VENDAS vazia, considerada 0.")
        if vendas is not False and (vendas < 0 or vendas != vendas.to_integral_value()):
            problemas.append(f"{onde}: VENDAS {vendas} precisa ser um número inteiro, 0 ou maior.")
        if verba is not False and verba < 0:
            problemas.append(f"{onde}: VERBA {verba} negativa.")
        if verba is not False and abs(verba - verba.quantize(CENTAVO)) > Decimal("0.000001"):
            problemas.append(f"{onde}: VERBA {verba} tem mais de 2 casas decimais (centavos).")

        if not problemas and verba is not False and vendas is not False and a_receber is not False:
            esperado = verba * vendas
            if a_receber is None:
                if esperado != 0:
                    problemas.append(f"{onde}: A RECEBER vazio (o arquivo foi salvo sem o "
                                     "cálculo da fórmula). Abra no Excel, salve e copie de "
                                     "novo para a pasta entrada.")
                a_receber = Decimal("0")
            elif abs(a_receber - esperado) > TOLERANCIA:
                problemas.append(f"{onde}: A RECEBER {_brl(a_receber)} é diferente de VERBA "
                                 f"{_brl(verba)} × VENDAS {int(vendas)} = {_brl(esperado)}.")

        if nome:
            k = chave(nome)
            if k in vistos:
                problemas.append(f"{arq}: nome '{nome}' repetido nas linhas {vistos[k]} e {n}.")
            else:
                vistos[k] = n

        if problemas:
            lote.erros.extend(problemas)
            continue
        # Dinheiro em centavos, como no banco (DECIMAL(...,2)): 6.8999999999999995 -> 6.90.
        lote.linhas.append(Linha(linha=n, nome=nome, cargo=cargo.nome, grupo=cargo.grupo,
                                 verba=verba.quantize(CENTAVO, ROUND_HALF_UP),
                                 vendas=int(vendas),
                                 a_receber=a_receber.quantize(CENTAVO, ROUND_HALF_UP)))

    if not lote.linhas and not lote.erros:
        lote.erros.append(f"{arq}: nenhuma pessoa encontrada abaixo do cabeçalho.")

    for g in lote.gerentes:
        equipe = cargos[chave(g.cargo)].equipe
        soma = sum(l.vendas for l in lote.colaboradores if l.cargo in equipe)
        if soma != g.vendas:
            lote.avisos.append(f"{arq}, linha {g.linha}: vendas de {g.nome} ({g.cargo}) = "
                               f"{g.vendas} na planilha, mas a soma da equipe "
                               f"({', '.join(equipe)}) é {soma}. Será gravado o valor da planilha.")

    if loja is not None and loja.preco_diant is None:
        lote.avisos.append(f"{loja.nome} sem preço em config/lojas.toml: o faturamento "
                           "aparece como —.")
    return lote


def ler_pasta(pasta: Path, lojas: list[Loja], cargos: dict[str, Cargo], ano: int) -> list[Lote]:
    """Todos os .xlsx da pasta (menos os temporários '~$' do Excel), em ordem de nome."""
    arquivos = sorted(p for p in Path(pasta).glob("*.xlsx") if not p.name.startswith("~$"))
    lotes = [ler_arquivo(p, lojas, cargos, ano) for p in arquivos]
    grupos: dict[tuple, list[Lote]] = {}
    for l in lotes:
        if l.loja is not None and l.mes is not None:
            grupos.setdefault((l.loja.chave, l.mes), []).append(l)
    for (_, mes), iguais in grupos.items():
        if len(iguais) > 1:
            nomes = " e ".join(l.arquivo.name for l in iguais)
            for l in iguais:
                l.erros.append(f"{nomes} são da mesma loja e mês ({l.loja.nome}, "
                               f"{mes:%m/%Y}): deixe só um deles na pasta entrada.")
    return lotes
