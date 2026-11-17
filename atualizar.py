"""Atualização mensal do dashboard Grupo TECAR — um comando só.

    1. Copie os arquivos "VERBAS <MÊS> TECAR <LOJA>.xlsx" para a pasta entrada\
    2. Rode:  python atualizar.py              (ano atual)
              python atualizar.py --ano 2026   (outro ano)
              python atualizar.py --sim        (grava sem perguntar)

O script mostra a prévia de cada loja, BLOQUEIA a gravação se algo estiver
errado (dizendo o arquivo e a linha), pergunta antes de gravar, grava no banco
local e no Aiven ([mysql_online]), lê de volta e confere, registra no
Histórico, reescreve o BASE GRUPO TECAR.xlsx e gera
conferencias\\conferencia_<AAAA-MM>.xlsx.

Rodar o mesmo mês de novo SUBSTITUI aquele mês da loja (não duplica).
Com a pasta entrada vazia, só atualiza lojas, preços e cargos no banco.

Códigos de saída: 0 = ok; 1 = bloqueado/cancelado/erro no banco local;
2 = a conferência encontrou divergência.
"""

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from tecar import banco
from tecar.conferencia import comparar, escrever_conferencia
from tecar.config import RAIZ, ConfigInvalida, carregar_cargos, carregar_lojas
from tecar.espelho import escrever_espelho
from tecar.leitura import ler_pasta

MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
         "Setembro", "Outubro", "Novembro", "Dezembro"]
LINHA = "-" * 78


def brl(v) -> str:
    if v is None:
        return "—"
    return ("R$ {:,.2f}".format(v)).replace(",", "X").replace(".", ",").replace("X", ".")


def nome_mes(d: date) -> str:
    return f"{MESES[d.month]}/{d.year}"


def _faturamento(lotes) -> Decimal | None:
    total = Decimal("0")
    for l in lotes:
        if l.loja.preco_diant is None:
            return None
        total += l.loja.preco_diant * l.totais()["vendas"]
    return total


# ------------------------------------------------------------------ prévia
def imprimir_previa(lotes, correcoes: dict) -> None:
    for lote in sorted(lotes, key=lambda l: (l.mes or date.min, l.loja.nome if l.loja else "")):
        titulo = (f"{lote.loja.nome if lote.loja else '(loja ?)'} — "
                  f"{nome_mes(lote.mes) if lote.mes else '(mês ?)'}")
        print(f"\n{LINHA}\n{titulo}   [{lote.arquivo.name}]\n{LINHA}")
        if lote.linhas:
            print(f"    {'Nome':36}   {'Cargo':20} {'Vendas':>6}  {'A Receber':>12}")
            for ln in sorted(lote.linhas, key=lambda x: (x.grupo != "colaborador", x.nome)):
                marca = "[G] " if ln.grupo == "gerente" else "    "
                print(f"{marca}{ln.nome[:36]:36}   {ln.cargo[:20]:20} {ln.vendas:>6}  "
                      f"{brl(ln.a_receber):>12}")
            t = lote.totais()
            print(f"  Vendas da loja (sem gerentes): {t['vendas']}")
            print(f"  A receber: colaboradores {brl(t['a_receber_colaboradores'])} · gerentes "
                  f"{brl(t['a_receber_gerentes'])} · total "
                  f"{brl(t['a_receber_colaboradores'] + t['a_receber_gerentes'])}")
            if lote.gerentes:
                print("  Gerentes: " + "; ".join(f"{g.nome} ({g.cargo})" for g in lote.gerentes))
            else:
                print("  Sem gerente nesta planilha.")
        for a in lote.avisos:
            print(f"  AVISO: {a}")
        nomes = correcoes.get((lote.loja.chave, lote.mes)) if lote.loja and lote.mes else None
        if nomes:
            print(f"  AVISO: há correção manual (página Lançamento) neste mês que será "
                  f"SUBSTITUÍDA pela planilha: {', '.join(nomes)}.")
        for e in lote.erros:
            print(f"  ERRO: {e}")


def imprimir_resumo(lotes) -> None:
    for mes in sorted({l.mes for l in lotes}):
        do_mes = [l for l in lotes if l.mes == mes]
        t = [l.totais() for l in do_mes]
        colab = sum((x["a_receber_colaboradores"] for x in t), Decimal("0"))
        ger = sum((x["a_receber_gerentes"] for x in t), Decimal("0"))
        print(f"\nGRUPO — {nome_mes(mes)}: {len(do_mes)} loja(s) · vendas "
              f"{sum(x['vendas'] for x in t)} (sem gerentes) · A receber colaboradores "
              f"{brl(colab)} · gerentes {brl(ger)} · total {brl(colab + ger)} · faturamento "
              f"{brl(_faturamento(do_mes))}")


# --------------------------------------------------------------- gravação
def _correcoes_no_local(cfg_local, lotes) -> dict:
    """Correções manuais que a reimportação vai substituir (consulta best-effort)."""
    saida = {}
    try:
        eng = banco.criar_engine(cfg_local)
        for l in lotes:
            if l.loja and l.mes:
                nomes = banco.correcoes_existentes(eng, l.loja.chave, l.mes)
                if nomes:
                    saida[(l.loja.chave, l.mes)] = nomes
        eng.dispose()
    except Exception:
        pass
    return saida


def _dica(erro: Exception) -> str:
    msg = str(erro)
    if "doesn't exist" in msg or "Unknown database" in msg:
        return " Rode antes: python criar_banco.py"
    if "Can't connect" in msg or "Connection refused" in msg:
        return " O MySQL está ligado?"
    return ""


def _salvar_excel(func, caminho: Path, *args) -> None:
    try:
        func(*args, caminho)
        print(f"Gerado: {caminho}")
    except PermissionError:
        print(f"ATENÇÃO: não consegui escrever {caminho.name}: feche o arquivo no Excel e rode "
              "de novo (os dados já estão gravados no banco).")
    except Exception as e:  # trava do OneDrive, disco cheio, banco caiu na leitura etc.
        print(f"ATENÇÃO: não consegui escrever {caminho.name} ({type(e).__name__}: "
              f"{str(e)[:200]}). Os dados já estão gravados no banco; rode de novo para "
              "gerar o arquivo.")


def main(argv=None, entrada=input) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Atualização mensal do dashboard Grupo TECAR.")
    p.add_argument("--ano", type=int, default=date.today().year,
                   help="ano dos arquivos (padrão: ano atual)")
    p.add_argument("--sim", action="store_true", help="grava sem perguntar")
    p.add_argument("--pasta", type=Path, default=RAIZ / "entrada")
    p.add_argument("--secrets", type=Path, default=banco.SECRETS)
    p.add_argument("--espelho", type=Path, default=RAIZ / "BASE GRUPO TECAR.xlsx")
    p.add_argument("--conferencias", type=Path, default=RAIZ / "conferencias")
    args = p.parse_args(argv)

    try:
        lojas, cargos = carregar_lojas(), carregar_cargos()
    except ConfigInvalida as e:
        print(f"ERRO na configuração: {e}")
        return 1
    try:
        secrets = banco.ler_secrets(args.secrets)
    except FileNotFoundError:
        print(f"Não achei {args.secrets}. Veja o README, seção 'Preencher o secrets'.")
        return 1
    cfg_local = secrets["mysql"]
    cfg_online = secrets.get("mysql_online")
    tem_aiven = banco.online_preenchido(cfg_online)

    args.pasta.mkdir(parents=True, exist_ok=True)
    lotes = ler_pasta(args.pasta, lojas, cargos, args.ano)
    print(f"Pasta: {args.pasta}   |   ano: {args.ano}   |   {len(lotes)} arquivo(s)")

    if not lotes:
        print("Nenhum arquivo .xlsx na pasta entrada. Vou só atualizar o cadastro "
              "(lojas, preços e cargos) nos bancos.")
    else:
        imprimir_previa(lotes, _correcoes_no_local(cfg_local, lotes))
        imprimir_resumo([l for l in lotes if not l.erros and l.mes])
        erros = [e for l in lotes for e in l.erros]
        if erros:
            print(f"\n{'=' * 78}\nGRAVAÇÃO BLOQUEADA — nada foi gravado. Corrija e rode de novo:")
            for e in erros:
                print(f"  • {e}")
            return 1
        for l in lojas:
            if l.preco_diant is None:
                print(f"AVISO: {l.nome} sem preço em config/lojas.toml (faturamento aparece como —).")

    destino_txt = "no banco local e no Aiven" if tem_aiven else "no banco local"
    if not args.sim:
        resp = entrada(f"\nGravar {destino_txt}? [s/N] ")
        if resp.strip().lower() not in ("s", "sim", "y"):
            print("Cancelado. Nada foi gravado.")
            return 1

    # ---- local (obrigatório)
    eng_local = banco.criar_engine(cfg_local)
    try:
        banco.gravar(eng_local, lotes, lojas, cargos)
    except Exception as e:
        print(f"ERRO ao gravar no banco LOCAL ({banco.descrever(cfg_local)}): "
              f"{type(e).__name__}: {e}.{_dica(e)}\nNada foi gravado.")
        return 1
    print(f"\nGravado no banco local ({banco.descrever(cfg_local)}).")

    # ---- Aiven (opcional)
    eng_aiven = None
    if not tem_aiven:
        print("Aiven não configurado ([mysql_online] vazio): gravado SÓ no banco local.")
    else:
        try:
            eng_aiven = banco.criar_engine(cfg_online)
            banco.gravar(eng_aiven, lotes, lojas, cargos)
            print(f"Gravado no Aiven ({banco.descrever(cfg_online)}).")
        except Exception as e:
            print(f"Aiven FALHOU ({type(e).__name__}: {str(e)[:300]}): gravado SÓ no banco "
                  "local. O dashboard publicado NÃO foi atualizado; rode de novo quando o "
                  "Aiven estiver acessível.")
            eng_aiven = None

    # ---- conferência (lê de volta de cada banco)
    rc = 0
    avisos = [a for l in lotes for a in l.avisos]
    for mes in sorted({l.mes for l in lotes}):
        do_mes = [l for l in lotes if l.mes == mes]
        try:
            local = banco.totais_por_loja(eng_local, mes)
        except Exception as e:
            print(f"ERRO: gravado no banco local, mas não consegui ler de volta para conferir "
                  f"({type(e).__name__}: {str(e)[:200]}).")
            local = {}
        aiven = None
        if eng_aiven is not None:
            try:
                aiven = banco.totais_por_loja(eng_aiven, mes)
            except Exception as e:
                print(f"Aiven: gravado, mas não consegui ler de volta para conferir "
                      f"({type(e).__name__}: {str(e)[:200]}). Rode de novo para conferir.")
        linhas = comparar(do_mes, local, aiven)
        print(f"\nConferência {nome_mes(mes)} (arquivo × banco):")
        for lin in linhas:
            if lin["status"].startswith("DIVERGE"):
                rc = 2
                for rotulo in lin["status"].split(": ", 1)[1].split(", "):
                    print(f"  DIVERGÊNCIA no banco {rotulo}, loja {lin['loja']}: arquivo vendas "
                          f"{lin['arquivo_vendas']} / colaboradores {brl(lin['arquivo_colab'])} / "
                          f"gerentes {brl(lin['arquivo_ger'])} × banco vendas "
                          f"{lin[f'{rotulo}_vendas']} / colaboradores "
                          f"{brl(lin[f'{rotulo}_colab'])} / gerentes {brl(lin[f'{rotulo}_ger'])}")
            else:
                print(f"  {lin['loja']}: banco local OK" + ("; Aiven OK" if aiven else ""))
        args.conferencias.mkdir(parents=True, exist_ok=True)
        _salvar_excel(lambda c: escrever_conferencia(c, mes, linhas, avisos),
                      args.conferencias / f"conferencia_{mes:%Y-%m}.xlsx")

    _salvar_excel(lambda c: escrever_espelho(banco.ler_base(eng_local), lojas, c), args.espelho)
    if lotes:
        print("Importação registrada no Histórico.")
    print("\nPRONTO." if rc == 0 else "\nATENÇÃO: a conferência encontrou divergência (veja acima).")
    eng_local.dispose()
    if eng_aiven is not None:
        eng_aiven.dispose()
    return rc


if __name__ == "__main__":
    sys.exit(main())
