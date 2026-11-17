"""Dados sintéticos para os testes (planilhas de verbas e base do dashboard)."""

from pathlib import Path

from openpyxl import Workbook

RAIZ = Path(__file__).resolve().parent.parent
DADOS_OUTUBRO = RAIZ / "tests" / "dados" / "outubro"
CABECALHO = ("NOME", "CARGO", "VERBA", "VENDAS", "A RECEBER")


def criar_planilha(caminho, linhas, linha_cabecalho=1, cabecalho=CABECALHO):
    """Grava uma planilha de verbas com VALORES (sem fórmulas).

    `linhas` é uma lista de tuplas (nome, cargo, verba, vendas, a_receber);
    `None` vira célula vazia. Linhas vazias no meio são aceitas.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for j, h in enumerate(cabecalho, 1):
        ws.cell(linha_cabecalho, j, h)
    for i, linha in enumerate(linhas, linha_cabecalho + 1):
        for j, v in enumerate(linha, 1):
            if v is not None:
                ws.cell(i, j, v)
    caminho = Path(caminho)
    wb.save(caminho)
    return caminho


def base_de_lotes(lotes, lojas):
    """DataFrame no formato da view `vw_base`, montado a partir de lotes lidos
    (sem banco). `lojas` define os preços usados no faturamento."""
    import pandas as pd

    preco = {l.chave: l for l in lojas}
    linhas, pid = [], 0
    ordem = {l.chave: i for i, l in enumerate(lojas, 1)}
    for lote in lotes:
        loja = preco[lote.loja.chave]
        pd_ = float(loja.preco_diant) if loja.preco_diant is not None else float("nan")
        pt_ = float(loja.preco_tras) if loja.preco_tras is not None else float("nan")
        for ln in lote.linhas:
            pid += 1
            total_d = ln.vendas * pd_
            linhas.append({
                "pessoa_id": pid, "pessoa": ln.nome, "cargo": ln.cargo, "grupo": ln.grupo,
                "loja_id": ordem[loja.chave], "loja_chave": loja.chave, "loja": loja.nome,
                "marca": loja.marca, "cidade": loja.cidade, "mes": pd.Timestamp(lote.mes),
                "mes_label": lote.mes.strftime("%m/%Y"), "passagens": float("nan"),
                "refil_diant": float(ln.vendas), "refil_tras": 0.0,
                "aproveitamento": float("nan"), "verba": float(ln.verba),
                "a_receber": float(ln.a_receber), "origem": "importacao",
                "preco_diant": pd_, "preco_tras": pt_, "total_diant": total_d,
                "total_tras": 0.0, "total_geral": total_d})
    return pd.DataFrame(linhas)


# Pessoas de outubro citadas nos testes, pela POSIÇÃO na planilha (loja, linha do
# Excel). Os nomes reais ficam só nos arquivos de tests/dados, fora do Git.
POSICOES = {
    "consultor_jeep": ("JEEP GOIANIA", 2),        # Consultor, 8 vendas
    "gerente_pecas_jeep": ("JEEP GOIANIA", 5),    # Gerente Peças
    "gerente_pos_jeep": ("JEEP GOIANIA", 6),      # Gerente Pós Vendas
    "consultor_mgo": ("MERCEDES GOIANIA", 5),     # Consultor, 4 vendas
    "tecnico_zero_mgo": ("MERCEDES GOIANIA", 7),  # Técnico, 0 vendas
    "chefe_mgo": ("MERCEDES GOIANIA", 9),         # Chefe de oficina, 19 vendas
}


def pessoas_outubro() -> dict:
    """{apelido: nome real} lido das cópias de outubro ({} se não existirem)."""
    if not DADOS_OUTUBRO.exists():
        return {}
    por_pos = {(l.loja.chave, ln.linha): ln.nome for l in lotes_outubro() for ln in l.linhas}
    return {k: por_pos[pos] for k, pos in POSICOES.items()}


def historico_exemplo():
    """Histórico no formato de banco.ler_historico: 4 importações + 3 correções."""
    import pandas as pd

    lin = []
    for i, (loja, vd, rd) in enumerate((("Jeep Goiânia", 20, 400), ("Mercedes Brasília", 24, 360),
                                        ("Mercedes Goiânia", 38, 570),
                                        ("Mercedes Uberlândia", 22, 275)), 1):
        lin.append({"id": i, "registrado_em": pd.Timestamp("2026-11-16 10:00"),
                    "tipo": "importacao", "loja": loja, "mes": pd.Timestamp("2026-10-01"),
                    "pessoa": None, "cargo": None, "vendas_antes": float("nan"),
                    "vendas_depois": float(vd), "a_receber_antes": float("nan"),
                    "a_receber_depois": float(rd), "arquivo": f"VERBAS OUTUBRO TECAR {loja}.xlsx",
                    "detalhe": "importação"})
    for j, (pessoa, cargo, va, vd, ra, rd) in enumerate((
            ("Colaborador Exemplo", "Consultor", 8, 10, 80, 100),
            ("Gerente Exemplo A", "Gerente Peças", 20, 22, 100, 110),
            ("Gerente Exemplo B", "Gerente Pós Vendas", 20, 22, 100, 110)), 5):
        lin.append({"id": j, "registrado_em": pd.Timestamp("2026-11-16 11:00"),
                    "tipo": "correcao", "loja": "Jeep Goiânia", "mes": pd.Timestamp("2026-10-01"),
                    "pessoa": pessoa, "cargo": cargo, "vendas_antes": float(va),
                    "vendas_depois": float(vd), "a_receber_antes": float(ra),
                    "a_receber_depois": float(rd), "arquivo": None, "detalhe": "correção manual"})
    return pd.DataFrame(lin)


def lotes_outubro():
    from tecar.config import carregar_cargos, carregar_lojas
    from tecar.leitura import ler_pasta
    return ler_pasta(DADOS_OUTUBRO, carregar_lojas(), carregar_cargos(), 2026)
