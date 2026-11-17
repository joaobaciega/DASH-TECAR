"""Conferência pós-gravação: totais do arquivo × banco local × Aiven, por loja."""

from datetime import datetime
from pathlib import Path

from openpyxl.styles import Font

from tecar.excel import FMT_INT, FMT_MOEDA, cabecalho, larguras, linha_dados
from tecar.leitura import Lote

CAMPOS = (("vendas", "vendas"), ("colab", "a_receber_colaboradores"),
          ("ger", "a_receber_gerentes"))
TITULOS = ["Loja",
           "Vendas — arquivo", "Vendas — local", "Vendas — Aiven",
           "A receber colaboradores — arquivo", "A receber colaboradores — local",
           "A receber colaboradores — Aiven",
           "A receber gerentes — arquivo", "A receber gerentes — local",
           "A receber gerentes — Aiven", "Situação"]


def comparar(lotes: list[Lote], local: dict, aiven: dict | None) -> list[dict]:
    """Uma linha por lote (loja do mês). `local`/`aiven` vêm de
    banco.totais_por_loja; aiven=None quando não foi gravado."""
    linhas = []
    for lote in lotes:
        arq = lote.totais()
        lin = {"loja": lote.loja.nome}
        divergentes = []
        for rotulo, banco_ in (("local", local), ("aiven", aiven)):
            tot = None if banco_ is None else banco_.get(lote.loja.chave)
            for curto, campo in CAMPOS:
                lin[f"arquivo_{curto}"] = arq[campo]
                lin[f"{rotulo}_{curto}"] = None if tot is None else tot[campo]
            if banco_ is not None and (tot is None or any(tot[c] != arq[c] for _, c in CAMPOS)):
                divergentes.append(rotulo)
        if divergentes:
            lin["status"] = "DIVERGE: " + ", ".join(divergentes)
        elif aiven is None:
            lin["status"] = "Aiven não gravado"
        else:
            lin["status"] = "OK"
        linhas.append(lin)
    return linhas


def escrever_conferencia(caminho: Path, mes, linhas: list[dict], avisos: list[str]) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Conferência"
    cabecalho(ws, TITULOS)
    chaves = ["loja"] + [f"{o}_{c}" for c, _ in CAMPOS for o in ("arquivo", "local", "aiven")] \
        + ["status"]
    formatos = [None, FMT_INT, FMT_INT, FMT_INT] + [FMT_MOEDA] * 6 + [None]
    for i, lin in enumerate(linhas, 2):
        valores = [float(v) if hasattr(v, "is_finite") else v for v in (lin[k] for k in chaves)]
        linha_dados(ws, i, valores, formatos, zebra=(i % 2 == 1))
    fim = len(linhas) + 1
    total = ["GRUPO"]
    for j, k in enumerate(chaves[1:-1], 2):
        col = ws.cell(1, j).column_letter
        tem_valor = any(lin[k] is not None for lin in linhas)
        total.append(f"=SUM({col}2:{col}{fim})" if tem_valor and linhas else None)
    total.append("")
    linha_dados(ws, fim + 1, total, formatos, negrito=True)
    larguras(ws, [24] + [14] * 9 + [20])
    ws.row_dimensions[1].height = 45
    ws.freeze_panes = "B2"
    wb.calculation.fullCalcOnLoad = True

    wa = wb.create_sheet("Avisos")
    wa.cell(1, 1, f"Conferência de {mes:%m/%Y} — gerada em "
                  f"{datetime.now():%d/%m/%Y %H:%M}").font = Font(name="Arial", bold=True, size=12)
    wa.cell(2, 1, "Situação: OK = arquivo, banco local e Aiven iguais. 'Aiven não gravado' = "
                  "Aiven não configurado ou falhou (só o local foi conferido).")
    for i, a in enumerate(avisos or ["Nenhum aviso."], 4):
        wa.cell(i, 1, a)
    wa.column_dimensions["A"].width = 140
    wb.save(caminho)
