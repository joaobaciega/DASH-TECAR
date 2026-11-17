"""Peças comuns às páginas: formatação BR, agregação, paleta e Excel."""

import datetime as dt
import io

import pandas as pd
import streamlit as st

from tecar.excel import (FMT_INT, FMT_MOEDA, FMT_PCT, cabecalho, larguras, linha_dados)

# Gráficos monocromáticos: preto e tons de cinza.
PALETA = ["#000000", "#404040", "#707070", "#9E9E9E", "#C8C8C8", "#262626", "#585858",
          "#888888", "#B4B4B4", "#DADADA"]
PRETO = "#000000"
MESES_PT = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
            "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TOTAIS_RS = ("total_diant", "total_tras", "total_geral")


# --------------------------------------------------------------- formatação
def _vazio(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA


def fmt_money(v) -> str:
    if _vazio(v):
        return "—"
    return ("R$ {:,.2f}".format(float(v))).replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_int(v) -> str:
    if _vazio(v):
        return "—"
    return "{:,.0f}".format(float(v)).replace(",", ".")


def fmt_pct(v) -> str:
    if _vazio(v):
        return "—"
    return ("{:.1f}%".format(float(v) * 100)).replace(".", ",")


def delta_str(v, tipo):
    if _vazio(v):
        return None
    sinal = "+" if v >= 0 else "-"
    corpo = fmt_money(abs(v)) if tipo == "money" else fmt_int(abs(v))
    return f"{sinal}{corpo}"


def mlabel(d) -> str:
    """'Out/2026'."""
    d = pd.Timestamp(d)
    return f"{MESES_PT[d.month][:3]}/{d.year}"


def label_mes(d) -> str:
    """'Outubro/2026'."""
    d = pd.Timestamp(d)
    return f"{MESES_PT[d.month]}/{d.year}"


# --------------------------------------------------------------- agregação
def agg_por(df: pd.DataFrame, grupo) -> pd.DataFrame:
    """Soma os indicadores por grupo.

    - passagens/aproveitamento: NaN quando ninguém informou passagens.
    - faturamento (total_*): NaN se ALGUMA linha do grupo não tem preço — um
      total parcial pareceria completo, então o grupo mostra "—".
    """
    g = df.groupby(grupo, dropna=False)
    out = pd.DataFrame({
        "passagens": g["passagens"].sum(min_count=1),
        "refil_diant": g["refil_diant"].sum(),
        "refil_tras": g["refil_tras"].sum(),
        "a_receber": g["a_receber"].sum(),
    })
    for c in TOTAIS_RS:
        soma = g[c].sum(min_count=1)
        faltando = g[c].apply(lambda s: s.isna().any())
        out[c] = soma.where(~faltando)
    conv = df["refil_diant"].where(df["passagens"].notna())
    conv_t = df["refil_tras"].where(df["passagens"].notna())
    out["_conv"] = conv.groupby([df[c] for c in ([grupo] if isinstance(grupo, str) else grupo)]).sum()
    out["_conv_t"] = conv_t.groupby([df[c] for c in ([grupo] if isinstance(grupo, str) else grupo)]).sum()
    out["aproveitamento"] = (out["_conv"] / out["passagens"]).where(out["passagens"] > 0)
    out["aproveitamento_tras"] = (out["_conv_t"] / out["passagens"]).where(out["passagens"] > 0)
    return out.drop(columns=["_conv", "_conv_t"]).reset_index()


def agg_total(df: pd.DataFrame) -> pd.Series:
    return agg_por(df.assign(_g=1), "_g").iloc[0]


def lojas_sem_preco(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return []
    return sorted(df.loc[df["total_geral"].isna(), "loja"].dropna().unique())


def aviso_preco(df: pd.DataFrame) -> None:
    faltam = lojas_sem_preco(df)
    if faltam:
        st.caption("Faturamento aparece como **—** porque estas lojas estão sem preço em "
                   f"config/lojas.toml: {', '.join(faltam)}.")


def colaboradores(df: pd.DataFrame) -> pd.DataFrame:
    """Só colaboradores: as vendas de gerente repetem as da equipe."""
    return df[df["grupo"] == "colaborador"].copy()


def erro_banco() -> None:
    st.error("Não foi possível conectar ao banco de dados no momento. Verifique se o MySQL "
             "está ativo e tente novamente.")


def layout_grafico(fig, altura=300, titulo=None):
    if titulo:
        fig.update_layout(title=titulo)
    fig.update_layout(template="plotly_white", height=altura,
                      margin=dict(l=10, r=40, t=50 if titulo else 20, b=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font_color=PRETO, xaxis_title=None, yaxis_title=None,
                      legend=dict(orientation="h", y=-0.2, title=None))
    return fig


def botao_excel(rotulo, dados: bytes, arquivo: str, chave: str | None = None):
    st.download_button(rotulo, data=dados, file_name=arquivo, mime=MIME_XLSX, type="primary",
                       width="stretch", key=chave)


# ------------------------------------------------------------------- Excel
def excel_abas(abas: list[dict]) -> bytes:
    """Cada aba: {nome, titulo, subtitulo, cabecalho, linhas, formatos, larguras,
    total (bool: última linha em negrito)}. Cabeçalho preto, fonte Arial."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    wb.remove(wb.active)
    for a in abas:
        ws = wb.create_sheet(a["nome"][:31])
        ws.cell(1, 1, a["titulo"]).font = Font(name="Arial", bold=True, size=13)
        ws.cell(2, 1, f"{a.get('subtitulo', '')} · Gerado em "
                      f"{dt.datetime.now():%d/%m/%Y %H:%M}").font = \
            Font(name="Arial", size=9, color="FF666666")
        h = 4
        cabecalho(ws, a["cabecalho"], h)
        linhas = a["linhas"]
        for i, lin in enumerate(linhas):
            valores = [None if _vazio(v) else v for v in lin]
            ultima = a.get("total") and i == len(linhas) - 1
            linha_dados(ws, h + 1 + i, valores, a["formatos"], zebra=(i % 2 == 1 and not ultima),
                        negrito=bool(ultima))
        larguras(ws, a.get("larguras") or [16] * len(a["cabecalho"]))
        ws.freeze_panes = ws.cell(h + 1, 1)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


F_INT, F_MOEDA, F_PCT = FMT_INT, FMT_MOEDA, FMT_PCT
