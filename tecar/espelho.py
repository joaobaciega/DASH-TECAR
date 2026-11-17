"""BASE GRUPO TECAR.xlsx: espelho do banco, reescrito a cada importação.

Mantém as abas e os cabeçalhos do template (Consultores, Gerentes, Preço por
Unidade) e acrescenta no fim Cargo, Verba (R$/venda) e A Receber (R$). Os
valores vêm do banco local; não é planilha de cálculo, é a fotografia do banco.
"""

from pathlib import Path

import pandas as pd
from openpyxl.styles import Font

from tecar.config import Loja
from tecar.excel import (FMT_DATA, FMT_INT, FMT_MES, FMT_MOEDA, FMT_PCT, cabecalho,
                         larguras, linha_dados)

COLUNAS = ["Loja", "Marca", "Mês (data)", "Mês", "Passagens", "Refil Diant. (qtd)",
           "Refil Tras. (qtd)", "Aproveitamento", "Total Diant. (R$)", "Total Tras. (R$)",
           "Total Geral (R$)", "Preço Diant. (R$)", "Preço Tras. (R$)", "Cargo",
           "Verba (R$/venda)", "A Receber (R$)"]
FORMATOS = [None, None, None, FMT_DATA, FMT_MES, FMT_INT, FMT_INT, FMT_INT, FMT_PCT,
            FMT_MOEDA, FMT_MOEDA, FMT_MOEDA, FMT_MOEDA, FMT_MOEDA, None, FMT_MOEDA, FMT_MOEDA]
LARGURAS = [34, 22, 14, 12, 10, 10, 12, 12, 13, 15, 14, 15, 14, 14, 18, 14, 15]


def _v(x):
    """NaN -> célula vazia; float inteiro -> int (fica limpo no Excel)."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return x


def _aba(ws, df, primeira):
    cabecalho(ws, [primeira] + COLUNAS)
    for i, (_, r) in enumerate(df.iterrows(), 2):
        mes = pd.Timestamp(r["mes"]).to_pydatetime()
        valores = [r["pessoa"], r["loja"], r["marca"], mes, mes, _v(r["passagens"]),
                   _v(r["refil_diant"]), _v(r["refil_tras"]), _v(r["aproveitamento"]),
                   _v(r["total_diant"]), _v(r["total_tras"]), _v(r["total_geral"]),
                   _v(r["preco_diant"]), _v(r["preco_tras"]), r["cargo"], _v(r["verba"]),
                   _v(r["a_receber"])]
        linha_dados(ws, i, valores, FORMATOS, zebra=(i % 2 == 1))
    larguras(ws, LARGURAS)
    ws.freeze_panes = "B2"
    if len(df):
        ws.auto_filter.ref = ws.dimensions


def escrever_espelho(base: pd.DataFrame, lojas: list[Loja], caminho: Path) -> None:
    from openpyxl import Workbook

    base = base.sort_values(["mes", "loja", "pessoa"]) if len(base) else base
    wb = Workbook()
    ws = wb.active
    ws.title = "Consultores"
    vazio = base.iloc[0:0]
    _aba(ws, base[base["grupo"] == "colaborador"] if len(base) else vazio, "Consultor")
    _aba(wb.create_sheet("Gerentes"), base[base["grupo"] == "gerente"] if len(base) else vazio,
         "Gerente")

    wp = wb.create_sheet("Preço por Unidade")
    cabecalho(wp, ["Loja", "Marca", "Preço Diant. (R$)", "Preço Tras. (R$)"])
    for i, l in enumerate(lojas, 2):
        linha_dados(wp, i, [l.nome, l.marca, _v(float(l.preco_diant)) if l.preco_diant is not None
                            else None, _v(float(l.preco_tras)) if l.preco_tras is not None else None],
                    [None, None, FMT_MOEDA, FMT_MOEDA])
    larguras(wp, [24, 16, 16, 16])
    nota = wp.cell(1, 6, "Preços de config/lojas.toml. Vazio = sem preço "
                         "(faturamento aparece como —).")
    nota.font = Font(name="Arial", italic=True, size=9)
    wb.save(caminho)
