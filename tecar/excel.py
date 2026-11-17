"""Estilo comum dos Excel gerados (preto e branco, fonte Arial)."""

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

PRETO, BRANCO, ZEBRA = "FF000000", "FFFFFFFF", "FFF2F2F2"
FMT_INT, FMT_MOEDA, FMT_PCT = "#,##0", "R$ #,##0.00", "0.0%"
FMT_DATA, FMT_MES = "dd/mm/yyyy", "mmm/yyyy"
_FINA = Side(style="thin", color="FFD9D9D9")
BORDA = Border(left=_FINA, right=_FINA, top=_FINA, bottom=_FINA)
FONTE = Font(name="Arial", size=10)
FONTE_NEGRITO = Font(name="Arial", size=10, bold=True)


def cabecalho(ws, titulos, linha=1):
    for j, t in enumerate(titulos, 1):
        c = ws.cell(linha, j, t)
        c.font = Font(name="Arial", size=10, bold=True, color=BRANCO)
        c.fill = PatternFill("solid", fgColor=PRETO)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BORDA


def linha_dados(ws, linha, valores, formatos, zebra=False, negrito=False):
    """Escreve uma linha; `formatos[j]` é o number_format (ou None) da coluna j."""
    for j, (v, fmt) in enumerate(zip(valores, formatos), 1):
        c = ws.cell(linha, j, v)
        c.font = FONTE_NEGRITO if negrito else FONTE
        c.border = BORDA
        if fmt:
            c.number_format = fmt
        if fmt in (FMT_INT, FMT_PCT, FMT_DATA, FMT_MES):
            c.alignment = Alignment(horizontal="center")
        if zebra:
            c.fill = PatternFill("solid", fgColor=ZEBRA)


def larguras(ws, valores):
    for j, w in enumerate(valores, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
