# Dashboard Grupo TECAR — Plano de Implementação

> **Para quem executa:** SUB-SKILL OBRIGATÓRIA: superpowers:executing-plans (escolhida pelo usuário). Importador, regras de cargo e conferência com superpowers:test-driven-development. Passos em checkbox (`- [ ]`).

**Objetivo:** dashboard Streamlit + MySQL do Grupo TECAR (refis de palheta), réplica da estrutura do Dahruj, alimentado todo mês por `python atualizar.py`, que lê as planilhas de verbas de `entrada\`, valida, grava no MySQL local e no Aiven, confere e gera os Excel de espelho e de conferência.

**Arquitetura:** um pacote `tecar/` sem Streamlit concentra as regras (config, leitura das planilhas, banco, espelho e conferência) e é usado pelo `atualizar.py`, pelo `criar_banco.py` e pela camada do app (`db.py`). O app (`app.py`) monta a navegação a partir de **uma lista única `PAGINAS`**, e cada página fica em `paginas/`. O banco guarda lojas, cargos, pessoas, lançamentos mensais e histórico. A view `vw_base` calcula o faturamento na leitura (NULL quando a loja está sem preço).

**Stack:** Python 3.14, Streamlit 1.58, pandas 3, SQLAlchemy 2 + PyMySQL, openpyxl, plotly, MySQL 8 (local 127.0.0.1:3306) e Aiven MySQL.

**Spec:** o pedido do usuário nesta conversa (seções contexto, escopo, dados, banco, atualizacao_mensal, design, pronto_quando). Referência só de leitura: `..\DASH DAHRUJ\MySQL Dahurj\`.

## Restrições globais

- Tudo o que for criado fica em `DASH TECAR\`. Nada é alterado em `DASH DAHRUJ\`.
- Lojas: Jeep Goiânia, Mercedes Brasília, Mercedes Goiânia, Mercedes Uberlândia.
- Colunas das planilhas: `NOME | CARGO | VERBA | VENDAS | A RECEBER`. VENDAS vai para Refil Dianteiro, Refil Traseiro = 0, Passagens = NULL e o aproveitamento aparece como "—".
- Colaboradores: Consultor, Vendedor de Peças, Técnico. Gerentes: Gerente Peças e Gerente Pós Vendas (equipe = Consultor + Vendedor de Peças) e Chefe de oficina (equipe = Técnico). Cada cargo segue separado. As vendas de gerente nunca entram no total da loja, mas o A RECEBER do gerente entra no total de verbas.
- Cargos são normalizados por espaços, maiúsculas e acentos ("Tecnico" = "Técnico", "Consultor " = "Consultor").
- Preço do refil por loja em `config/lojas.toml`. Valor inicial: **R$ 199,00 por refil dianteiro (= por venda) nas 4 lojas**, informado pelo usuário depois do pedido. O preço traseiro fica vazio (a TECAR não vende traseiro). Se um preço dianteiro ficar vazio, o faturamento aparece como "—" e o script avisa. Linha com 0 refil traseiro tem `total_tras = 0`, mesmo sem preço traseiro.
- Banco local `dashboard_tecar` com host, usuário e senha da seção `[mysql]` do secrets do Dahruj. Nenhuma credencial Aiven do Dahruj é copiada.
- Os testes **nunca** gravam no Aiven: usam o banco local `dashboard_tecar_teste`, e o helper de teste recusa host que não seja `127.0.0.1`/`localhost`.
- O cliente `mysql` não está no PATH. Todo SQL roda via PyMySQL/SQLAlchemy.
- Visual: preto como primária e branco como secundária. Barra lateral e cabeçalho pretos com a logo, conteúdo branco com texto preto, botões e cartões em destaque pretos, gráficos em preto e cinzas.
- Totais de outubro/2026 (aceite): Jeep Goiânia 20 / R$ 200 / gerentes R$ 200; Mercedes Brasília 24 / R$ 360 / sem gerente; Mercedes Goiânia 38 / R$ 475 / gerente R$ 95; Mercedes Uberlândia 22 / R$ 275 / sem gerente; Grupo 104 vendas e R$ 1.605. Faturamento a R$ 199: Jeep Goiânia R$ 3.980,00, Mercedes Brasília R$ 4.776,00, Mercedes Goiânia R$ 7.562,00, Mercedes Uberlândia R$ 4.378,00, Grupo R$ 20.696,00.
- O console do Windows precisa mostrar os acentos: `atualizar.py` e `criar_banco.py` chamam `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`.

## Decisões de rotina (vão para o README)

1. **Logo:** o anexo chegou em RGB (fundo preto, sem alfa). `assets/logo.png` é regravada em RGBA com alfa = brilho do pixel e cor branca. Se houver o PNG original transparente, basta substituir o arquivo.
2. **Preço:** vale para todos os meses da loja (como o `precos_marca` do Dahruj). Mudar o preço recalcula o faturamento do histórico inteiro. Para ajustar, edite `config/lojas.toml` e rode `python atualizar.py`: com a pasta `entrada` vazia ele só sincroniza lojas, preços e cargos.
3. **Faturamento agregado:** se alguma loja do recorte estiver sem preço, o total do recorte aparece como "—" (não soma parcial), com uma legenda listando as lojas sem preço.
4. **Vendas do gerente:** a importação grava o valor da planilha (avisa se for diferente da soma da equipe). A correção manual de um colaborador recalcula os gerentes cuja equipe inclui o cargo dele (vendas = soma da equipe, A RECEBER = verba × vendas). Gerente não é corrigido diretamente.
5. **Correção × reimportação:** reimportar a loja/mês substitui a correção manual. A prévia avisa quando isso vai acontecer.
6. **Correção grava onde o app lê (`[mysql]`)** e também no `[mysql_online]`, se ele existir e estiver preenchido (na sua máquina). No Streamlit Cloud só existe `[mysql]` (= Aiven).
7. **Espelho `BASE GRUPO TECAR.xlsx`:** valores vindos do banco local (é espelho, não planilha de cálculo). Mantém as abas e os cabeçalhos do template e acrescenta no fim `Cargo`, `Verba (R$/venda)`, `A Receber (R$)`. Aproveitamento e totais em R$ ficam em branco quando não há passagens ou preço.
8. **Senha da área restrita** em `[acesso] senha_lancamento` do secrets. Sem ela, o cadeado avisa "senha não configurada" e não libera nada. A senha inicial fica só no secrets.toml local; trocar por uma senha forte antes de publicar.
9. **Git:** `git init` em `DASH TECAR`. O `.gitignore` exclui o secrets e os dados reais (`entrada/*.xlsx`, `conferencias/`, `BASE GRUPO TECAR.xlsx`, `tests/dados/`). Os testes que dependem de `tests/dados/outubro` são pulados (skip) com mensagem quando a pasta não existe.
10. **Ano:** `--ano` (padrão = ano atual). O README avisa para passar `--ano 2026` ao importar dezembro em janeiro.

## Review Focus

1. **Excel aberto:** `BASE GRUPO TECAR.xlsx` ou a conferência abertos no Excel dão `PermissionError`. Os dados já foram gravados, então o script diz "feche o arquivo e rode de novo" sem traceback (teste na Task 6).
2. **Linhas vazias no fim da planilha** (Brasília vai até E12 e Uberlândia até E11, com dados só até 10 e 4): são ignoradas, sem bloqueio (teste na Task 2).
3. **A RECEBER sem valor em cache** (arquivo salvo por ferramenta que não calcula): bloqueia com "abra no Excel e salve" quando VERBA × VENDAS ≠ 0 (teste na Task 2).
4. **Soma com loja sem preço:** `sum()` do pandas transforma NaN em 0 e mostraria R$ 0,00. Os agregados usam `min_count` e a regra 3 acima (teste na Task 8).
5. **Dois arquivos da mesma loja e mês em `entrada`** (ex.: cópia "(1)"): bloqueia em vez de gravar o último (teste na Task 2).

---

## Estrutura de arquivos

```
DASH TECAR/
  app.py                  navegação (lista PAGINAS), tema/CSS, logo, cadeado
  db.py                   camada do app: engine via st.secrets, leituras com cache, correção
  paginas/__init__.py
  paginas/comum.py        formatação BR, agg_por, paleta, helpers de Excel, avisos de preço
  paginas/dashboard.py | relatorio_gerente.py | relatorio_colaborador.py | verbas.py
  paginas/lancamento.py | historico.py
  tecar/__init__.py
  tecar/config.py         Loja, Cargo, chave(), carregar_lojas(), carregar_cargos()
  tecar/leitura.py        Linha, Lote, identificar_arquivo(), ler_arquivo(), ler_pasta()
  tecar/banco.py          secrets/destinos, engine, schema, gravar, totais, correção, leituras
  tecar/espelho.py        escrever_espelho()
  tecar/conferencia.py    comparar(), escrever_conferencia()
  atualizar.py            CLI mensal
  criar_banco.py          aplica schema.sql (local; --online = Aiven)
  schema.sql
  config/lojas.toml  config/cargos.toml
  .streamlit/config.toml  secrets.toml  secrets.example.toml
  assets/logo.png  entrada/.gitkeep  conferencias/.gitkeep
  requirements.txt  .gitignore  README.md  BASE GRUPO TECAR.xlsx
  tests/fabrica.py  tests/dados/outubro/*.xlsx  tests/test_*.py
```

---

### Task 1: Esqueleto, configuração e logo

**Arquivos:** criar `.gitignore`, `requirements.txt` (streamlit, pandas, SQLAlchemy, PyMySQL, openpyxl, plotly, cryptography), `config/lojas.toml`, `config/cargos.toml`, `tecar/__init__.py`, `tecar/config.py`, `.streamlit/config.toml`, `.streamlit/secrets.toml`, `.streamlit/secrets.example.toml`, `entrada/.gitkeep`, `conferencias/.gitkeep`, `tests/dados/outubro/` (cópias dos 4 arquivos de outubro), `tests/test_config.py`. Modificar: `assets/logo.png`.

**Interfaces (produz):**
- `chave(texto: str | None) -> str`: tira espaços nas pontas, colapsa espaços internos, maiúsculas, sem acento.
- `@dataclass(frozen=True) Loja(chave: str, nome: str, marca: str, cidade: str, preco_diant: Decimal | None, preco_tras: Decimal | None)`. `chave` = `chave(arquivo)`.
- `@dataclass(frozen=True) Cargo(nome: str, grupo: str, equipe: tuple[str, ...])`, com grupo ∈ {"colaborador", "gerente"}.
- `class ConfigInvalida(Exception)`
- `carregar_lojas(caminho: Path = RAIZ/"config/lojas.toml") -> list[Loja]`
- `carregar_cargos(caminho: Path = RAIZ/"config/cargos.toml") -> dict[str, Cargo]` (indexado por `chave(nome)`)
- `RAIZ: Path` = pasta `DASH TECAR`.

Formato de `lojas.toml`: `[[loja]]` com `arquivo`, `nome`, `marca`, `cidade`, `preco_diant = 199`, `preco_tras = ""`. O preço aceita número, `""` ou texto `"12,50"`. Formato de `cargos.toml`: `[[cargo]]` com `nome`, `grupo` e `equipe = [...]` (só para gerente). Os dois arquivos levam comentários explicando como editar.

`secrets.toml`: `[mysql]` local (127.0.0.1, 3306, root, senha do Dahruj, `dashboard_tecar`), `[mysql_online]` com `host = ""`, `port = 0`, `user = ""`, `password = ""`, `database = "dashboard_tecar"`, `ssl_ca = ""` e comentários, e `[acesso] senha_lancamento`. O `secrets.example.toml` é igual, sem senhas.

`.streamlit/config.toml`: `base="light"`, `primaryColor="#000000"`, `backgroundColor="#FFFFFF"`, `secondaryBackgroundColor="#F2F2F2"`, `textColor="#000000"`, `runOnSave=false`.

- [ ] **Passo 1:** `git init` em `DASH TECAR`. Criar `.gitignore`, as pastas e os arquivos de config, e copiar os 4 arquivos de outubro para `tests/dados/outubro/`.
- [ ] **Passo 2: teste que falha**: `tests/test_config.py`
  - `test_chave_normaliza`: `chave(" Técnico ") == chave("TECNICO") == "TECNICO"`; `chave("Gerente  Peças") == "GERENTE PECAS"`.
  - `test_lojas_padrao`: 4 lojas; nomes == ["Jeep Goiânia", "Mercedes Brasília", "Mercedes Goiânia", "Mercedes Uberlândia"]; todas com `preco_diant == Decimal("199")` e `preco_tras is None`; a chave da primeira é `"JEEP GOIANIA"`.
  - `test_cargos_padrao`: grupos dos 6 cargos; `cargos["GERENTE PECAS"].equipe == ("Consultor", "Vendedor de Peças")`; `cargos["CHEFE DE OFICINA"].equipe == ("Técnico",)`.
  - `test_preco_texto_virgula`: um toml temporário com `preco_diant = "12,50"` dá `Decimal("12.50")`.
  - `test_config_invalida`: um gerente cuja equipe cita um cargo inexistente levanta `ConfigInvalida`, com o nome do cargo na mensagem; o mesmo para grupo desconhecido.
- [ ] **Passo 3:** rodar `python -m unittest tests.test_config -v` → FAIL (módulo inexistente).
- [ ] **Passo 4:** implementar `tecar/config.py` (tomllib).
- [ ] **Passo 5:** rodar de novo → PASS.
- [ ] **Passo 6:** regravar `assets/logo.png` em RGBA (Pillow: L = convert("L"); RGBA = (255, 255, 255, L)). Conferir com `Image.open(...).mode == "RGBA"` e o canto (0,0) com alfa 0.
- [ ] **Passo 7:** commit `chore: esqueleto, configuração de lojas/cargos e logo`.

### Task 2: Leitura das planilhas e regras de bloqueio (TDD)

**Arquivos:** criar `tecar/leitura.py`, `tests/fabrica.py`, `tests/test_leitura.py`, `tests/test_outubro.py`.

**Interfaces:**
- Consome: `Loja`, `Cargo`, `chave`, `carregar_lojas`, `carregar_cargos`.
- Produz:
  - `MESES: dict[str, int]` (chaves normalizadas JANEIRO…DEZEMBRO, com MARCO).
  - `@dataclass Linha(linha: int, nome: str, cargo: str, grupo: str, verba: Decimal, vendas: int, a_receber: Decimal)`. `cargo` = nome canônico do config; `linha` = número da linha no Excel.
  - `@dataclass Lote(arquivo: Path, loja: Loja | None, mes: date | None, linhas: list[Linha], erros: list[str], avisos: list[str])` com `colaboradores`, `gerentes` (listas), `totais() -> dict` = `{"vendas": int, "a_receber_colaboradores": Decimal, "a_receber_gerentes": Decimal}`.
  - `identificar_arquivo(nome: str, lojas: list[Loja], ano: int) -> tuple[date | None, Loja | None, list[str]]`: padrão `VERBAS <MÊS> TECAR <LOJA>.xlsx`, sem diferenciar maiúsculas e acentos.
  - `ler_arquivo(caminho: Path, lojas, cargos, ano: int) -> Lote`
  - `ler_pasta(pasta: Path, lojas, cargos, ano: int) -> list[Lote]`: só `*.xlsx`, ignora `~$*` (lock do Excel); dois lotes da mesma loja+mês recebem erro nos dois.
  - `fabrica.criar_planilha(caminho: Path, linhas: list[tuple], linha_cabecalho: int = 1) -> Path` grava valores (não fórmulas) com o cabeçalho padrão.

**Regras:** cabeçalho procurado nas 10 primeiras linhas da primeira aba que contenha NOME e CARGO (normalizados); leitura com `data_only=True`; linha com NOME e CARGO vazios = ignorada; nome comparado por `chave()` e gravado com `strip` e espaços colapsados.

Bloqueios (vão para `erros`, cada um com o arquivo e "linha N"):
- cargo fora do mapa;
- nome repetido na loja ("linhas 3 e 7");
- loja fora de `config/lojas.toml`;
- mês ilegível no nome do arquivo;
- `|A RECEBER − VERBA×VENDAS| > 0,005`;
- VERBA ou VENDAS não numérico;
- VENDAS negativa ou fracionada;
- A RECEBER vazio com VERBA×VENDAS ≠ 0 ("abra no Excel e salve");
- cabeçalho não encontrado.

Avisos: vendas do gerente ≠ soma da equipe ("planilha 20, equipe 18"); loja sem preço ("Jeep Goiânia sem preço em config/lojas.toml: faturamento aparece como —"); VENDAS vazio tratado como 0.

- [ ] **Passo 1: testes que falham**: `tests/test_leitura.py` (planilhas sintéticas em `tempfile.TemporaryDirectory`)
  - `test_identificar_outubro`: `"VERBAS OUTUBRO TECAR JEEP GOIANIA.xlsx"`, ano 2026 → `date(2026,10,1)`, loja "Jeep Goiânia", sem erros. `"verbas março tecar mercedes brasília.xlsx"` → mês 3.
  - `test_mes_ilegivel` (`"VERBAS OUTUBR TECAR JEEP GOIANIA.xlsx"`) → erro contém "mês"; `test_loja_fora_config` (`"VERBAS OUTUBRO TECAR VW ANAPOLIS.xlsx"`) e `"VERBAS SETEMBRO.xlsx"` → erro contém "loja".
  - `test_cargo_normalizado`: as linhas "Consultor ", "Tecnico" e "TÉCNICO" viram "Consultor", "Técnico" e "Técnico".
  - `test_cargo_desconhecido_bloqueia`: "Estagiário" na linha 3 → erro contém "linha 3" e "Estagiário".
  - `test_nome_repetido_bloqueia`: "Ana Silva" e "ana silva " → erro contém "linhas 2 e 3".
  - `test_a_receber_divergente_bloqueia`: verba 10, vendas 3, a receber 31 na linha 2 → erro contém "linha 2".
  - `test_a_receber_vazio_bloqueia` (verba 10, vendas 2, None) e `test_a_receber_vazio_zero_ok` (vendas 0, None → 0, sem erro).
  - `test_linhas_vazias_ignoradas`: 2 linhas de dados + 3 linhas vazias → `len(linhas) == 2`, sem erros.
  - `test_gerente_diferente_da_equipe_avisa`: consultores 5+3 e Gerente Peças com 9 → aviso contém "9" e "8", e `erros == []`.
  - `test_sem_preco_avisa`: aviso contém "sem preço".
  - `test_duplicado_na_pasta_bloqueia`: dois arquivos de Jeep outubro (um com " (1)") → os dois lotes têm erro.
  - `test_totais_excluem_vendas_de_gerente`: consultores 8+4 a R$ 10 e gerente 12 a R$ 5 → `{"vendas": 12, "a_receber_colaboradores": 120, "a_receber_gerentes": 60}`.
- [ ] **Passo 2:** rodar `python -m unittest tests.test_leitura -v` → FAIL.
- [ ] **Passo 3:** implementar `tests/fabrica.py` e `tecar/leitura.py`.
- [ ] **Passo 4:** rodar → PASS.
- [ ] **Passo 5: teste das cópias reais**: `tests/test_outubro.py` (skip se `tests/dados/outubro` não existir)
  - `test_totais_por_loja`: `ler_pasta(dados/outubro, ..., 2026)` → todos sem erro; totais por loja: Jeep (20, 200, 200), Brasília (24, 360, 0), Mercedes Goiânia (38, 475, 95), Uberlândia (22, 275, 0).
  - `test_totais_grupo`: soma de vendas 104; soma de A RECEBER (colaboradores + gerentes) == `Decimal("1605")`.
  - `test_gerentes`: Jeep tem 2 gerentes (Gerente Peças e Gerente Pós Vendas), Mercedes Goiânia tem 1 (Chefe de oficina), Brasília e Uberlândia têm 0; nenhum aviso de "equipe" nos 4 arquivos.
- [ ] **Passo 6:** rodar `python -m unittest tests.test_outubro -v` → PASS (se falhar sem causa óbvia, usar superpowers:systematic-debugging).
- [ ] **Passo 7:** commit `feat: leitura e validação das planilhas de verbas`.

### Task 3: Schema, conexões e `criar_banco.py`

**Arquivos:** criar `schema.sql`, `tecar/banco.py` (parte de conexão), `criar_banco.py`, `tests/apoio_banco.py`, `tests/test_banco_schema.py`.

**Schema** (sem `CREATE DATABASE`/`USE`, porque o banco é criado pelo script com o nome do secrets; tudo com `IF NOT EXISTS` e as views com `CREATE OR REPLACE`):
- `lojas(id PK AI, chave VARCHAR(80) UNIQUE, nome, marca, cidade, preco_diant DECIMAL(10,2) NULL, preco_tras DECIMAL(10,2) NULL)`
- `cargos(nome VARCHAR(60) PK, grupo ENUM('colaborador','gerente'), equipe VARCHAR(255) NULL)`, com equipe separada por `;`.
- `pessoas(id PK AI, loja_id FK, nome VARCHAR(150), chave VARCHAR(150), UNIQUE(loja_id, chave))`
- `lancamentos(id PK AI, pessoa_id FK, loja_id FK, mes DATE, cargo VARCHAR(60), grupo ENUM, passagens INT NULL, refil_diant INT NOT NULL, refil_tras INT NOT NULL DEFAULT 0, verba DECIMAL(10,2), a_receber DECIMAL(12,2), origem ENUM('importacao','correcao'), atualizado_em TIMESTAMP, UNIQUE(pessoa_id, loja_id, mes))`
- `historico(id BIGINT PK AI, registrado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP, tipo ENUM('importacao','correcao'), loja VARCHAR(120), mes DATE, pessoa VARCHAR(150) NULL, cargo VARCHAR(60) NULL, vendas_antes INT NULL, vendas_depois INT NULL, a_receber_antes DECIMAL(12,2) NULL, a_receber_depois DECIMAL(12,2) NULL, arquivo VARCHAR(255) NULL, detalhe VARCHAR(500) NULL)`, só com inserções (o app nunca apaga).
- `vw_base`: lançamentos + pessoas + lojas → `pessoa_id, pessoa, cargo, grupo, loja_id, loja_chave, loja, marca, cidade, mes, mes_label('%m/%Y'), passagens, refil_diant, refil_tras, aproveitamento (refil/passagens se passagens>0, senão NULL), verba, a_receber, origem, preco_diant, preco_tras, total_diant (NULL se preço NULL), total_tras (0 quando refil_tras = 0; NULL se houver refil traseiro sem preço), total_geral`.

**Interfaces (produz, em `tecar/banco.py`):**
- `ler_secrets(caminho: Path = RAIZ/".streamlit/secrets.toml") -> dict`
- `online_preenchido(cfg: dict | None) -> bool`: host, user, password e database não vazios e port > 0.
- `destinos(secrets: dict) -> list[tuple[str, dict]]`: `[("local", secrets["mysql"])]` + `("aiven", ...)` se preenchido.
- `criar_engine(cfg: dict, com_banco: bool = True) -> Engine`: `ssl_ca` relativo a `RAIZ` vai para `connect_args={"ssl": {"ca": caminho}}`.
- `aplicar_schema(cfg: dict, schema: Path = RAIZ/"schema.sql", recriar: bool = False) -> list[str]`: cria o banco se não existir, separa os comandos por `;` em fim de linha, ignora comentários `--` e devolve os nomes das tabelas e views existentes. `recriar=True` apaga as tabelas antes.
- `tests/apoio_banco.py`: `cfg_teste() -> dict` (o `[mysql]` do secrets com `database="dashboard_tecar_teste"`; `assert host in {"127.0.0.1","localhost"}`); `banco_limpo() -> Engine` (aplica o schema com `recriar=True`); `skip` se o MySQL local não responder.

`criar_banco.py`: `python criar_banco.py` (local), `--online` (Aiven, erro claro se `[mysql_online]` não estiver preenchido) e `--recriar` (pede para digitar `APAGAR`). Mostra o servidor, o banco e a lista de tabelas/views criadas.

- [ ] **Passo 1: testes que falham**: `tests/test_banco_schema.py`
  - `test_online_preenchido`: o template vazio dá False; preenchido dá True; port 0 dá False.
  - `test_destinos_sem_online`: `destinos({"mysql": {...}, "mysql_online": {"host": ""}})` == só local.
  - `test_aplicar_schema_cria_objetos`: retorno ⊇ {"lojas","cargos","pessoas","lancamentos","historico","vw_base"}.
  - `test_aplicar_schema_idempotente`: aplicar duas vezes sem `recriar` não dá erro e não apaga uma linha inserida em `lojas`.
- [ ] **Passo 2:** rodar `python -m unittest tests.test_banco_schema -v` → FAIL.
- [ ] **Passo 3:** implementar `schema.sql`, a parte de conexão de `tecar/banco.py`, `tests/apoio_banco.py` e `criar_banco.py`.
- [ ] **Passo 4:** rodar → PASS.
- [ ] **Passo 5:** commit `feat: schema MySQL e criar_banco.py`.

### Task 4: Gravação, totais, correção e leituras (TDD)

**Arquivos:** modificar `tecar/banco.py`; criar `tests/test_banco.py`.

**Interfaces (produz):**
- `gravar(engine, lotes: list[Lote], lojas: list[Loja], cargos: dict[str, Cargo]) -> None`: uma transação; sincroniza `lojas` (upsert por chave, inclusive preço) e `cargos`; para cada lote, faz upsert das pessoas, `DELETE` dos lançamentos daquela loja+mês, `INSERT` das linhas (`origem='importacao'`) e 1 linha em `historico` (`tipo='importacao'`, pessoa NULL, `vendas_antes` = total de colaboradores antes, ou NULL, `vendas_depois`, `a_receber_antes/depois` = colaboradores + gerentes, `arquivo` = nome do arquivo, `detalhe` = "N pessoas, G gerentes").
- `totais_por_loja(engine, mes: date) -> dict[str, dict]`: indexado pela chave da loja, no mesmo formato de `Lote.totais()`.
- `correcoes_existentes(engine, loja_chave: str, mes: date) -> list[str]`: nomes com `origem='correcao'`.
- `salvar_correcao(engine, loja_id: int, mes: date, pessoa_id: int, vendas: int) -> list[dict]`: uma transação; recusa gerente (`ValueError`); atualiza vendas e `a_receber = verba × vendas`, `origem='correcao'`; recalcula os gerentes da loja+mês cuja equipe contém o cargo dele; grava 1 linha de `historico` por pessoa alterada. Retorna `[{pessoa, cargo, vendas_antes, vendas_depois, a_receber_antes, a_receber_depois}]`.
- `ler_base(engine) -> pd.DataFrame` (colunas da `vw_base`, `mes` como datetime, DECIMAL → float, `passagens` float com NaN) e `ler_historico(engine) -> pd.DataFrame`.

- [ ] **Passo 1: testes que falham**: `tests/test_banco.py` (usa `banco_limpo()` e as cópias de outubro; skip se faltar MySQL ou dados)
  - `test_gravar_e_totais_outubro`: `totais_por_loja(eng, date(2026,10,1))` == totais dos lotes, nas 4 lojas.
  - `test_gravar_duas_vezes_nao_duplica`: depois de 2 gravações, `COUNT(*)` de lançamentos == 27 (24 colaboradores + 3 gerentes) e os totais continuam iguais; `historico` tem 8 linhas de importação.
  - `test_faturamento_padrao_199`: com o config padrão, `total_geral` de o consultor da linha 2 da Jeep = 1592.0 e a soma de `total_geral` dos colaboradores = 20696.0.
  - `test_sincroniza_preco`: com a loja Jeep a `Decimal("30")`, `ler_base` traz `total_geral` de o consultor da linha 2 da Jeep = 240.0 e a Brasília (sem preço) tem `total_geral` NaN.
  - `test_correcao_recalcula_gerentes`: o consultor da linha 2 da Jeep 8→10 → o retorno tem 3 mudanças; os 2 gerentes da Jeep com vendas 22 e A RECEBER 110; Jeep com vendas 22; `historico` +3 linhas `correcao`; `correcoes_existentes` == [consultor da linha 2 da Jeep].
  - `test_correcao_consultor_nao_mexe_chefe_oficina`: o consultor da linha 5 da Mercedes Goiânia 4→6 → retorno com 1 mudança; Chefe continua com 19.
  - `test_correcao_de_gerente_recusada`: `ValueError`.
  - `test_reimportar_substitui_correcao`: após a correção e uma nova gravação, Jeep volta a 20.
- [ ] **Passo 2:** rodar → FAIL.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** rodar → PASS.
- [ ] **Passo 5:** commit `feat: gravação idempotente, totais, correção e histórico`.

### Task 5: Espelho e Excel de conferência (TDD)

**Arquivos:** criar `tecar/espelho.py`, `tecar/conferencia.py`, `tests/test_planilhas_saida.py`.

**Interfaces:**
- `espelho.escrever_espelho(base: pd.DataFrame, lojas: list[Loja], caminho: Path) -> None`: abas `Consultores` (colaboradores), `Gerentes` e `Preço por Unidade`, com cabeçalhos do template + `Cargo`, `Verba (R$/venda)`, `A Receber (R$)`. Todos os meses, ordenados por mês, loja e nome. Cabeçalho preto com fonte branca Arial em negrito, `Mês` no formato `mmm/aaaa`, R$ `R$ #,##0.00`, painel congelado. Apaga os dados fictícios (reescreve o arquivo inteiro).
- `conferencia.comparar(lotes: list[Lote], local: dict, aiven: dict | None) -> list[dict]`: uma linha por loja do mês com `loja, arquivo_vendas, local_vendas, aiven_vendas, arquivo_colab, local_colab, aiven_colab, arquivo_ger, local_ger, aiven_ger, status` (`"OK"`, `"DIVERGE: local"`, `"DIVERGE: aiven"`, `"Aiven não gravado"`).
- `conferencia.escrever_conferencia(caminho: Path, mes: date, linhas: list[dict], avisos: list[str]) -> None`: aba `Conferência` (+ linha GRUPO com fórmulas `SUM` nas colunas numéricas) e aba `Avisos`.

- [ ] **Passo 1: testes que falham**
  - `test_espelho_outubro`: com uma base montada a partir dos lotes de outubro (`fabrica.base_de_lotes(lotes, lojas)`), o arquivo tem as abas `["Consultores","Gerentes","Preço por Unidade"]`; `Consultores` tem 24 linhas de dados; `Gerentes` tem 3; nenhuma célula contém "Volkswagen" ou "Loja 1"; os últimos cabeçalhos são `["Cargo","Verba (R$/venda)","A Receber (R$)"]`; o total da coluna A Receber de Consultores é 1310 e o de Gerentes é 295.
  - `test_comparar_ok_e_divergencia`: local igual ao arquivo e aiven None → status `"Aiven não gravado"` em todas; local com Jeep vendas 19 → `"DIVERGE: local"` só na Jeep.
  - `test_escrever_conferencia`: abas `["Conferência","Avisos"]` e 5 linhas de dados (4 lojas + GRUPO).
- [ ] **Passo 2:** rodar → FAIL. **Passo 3:** implementar (inclui `fabrica.base_de_lotes`). **Passo 4:** rodar → PASS.
- [ ] **Passo 5:** commit `feat: espelho BASE GRUPO TECAR e Excel de conferência`.

### Task 6: `atualizar.py` (fluxo mensal)

**Arquivos:** criar `atualizar.py` e `tests/test_atualizar.py`.

**Interfaces:**
- `main(argv: list[str] | None = None, entrada=input) -> int`, com os argumentos `--ano` (padrão: ano atual), `--sim`, `--pasta` (padrão `RAIZ/"entrada"`), `--secrets` (padrão do projeto; usado nos testes), `--espelho` (padrão `RAIZ/"BASE GRUPO TECAR.xlsx"`) e `--conferencias` (padrão `RAIZ/"conferencias"`).
- Códigos de saída: 0 = gravou e conferiu; 1 = bloqueado, cancelado ou falha no local; 2 = conferência divergente.

**Fluxo:**
1. Carrega o config. `ConfigInvalida` → mensagem e saída 1.
2. Roda `ler_pasta`.
3. Imprime a prévia por loja/mês: tabela Nome | Cargo | Vendas | A Receber, gerentes marcados com `[G]`, totais (vendas sem gerente, A RECEBER de colaboradores, de gerentes e total), "sem gerente" quando não houver gerente, avisos e, consultando o local, as correções manuais que serão substituídas.
4. Se houver erro, lista "GRAVAÇÃO BLOQUEADA" com cada motivo e sai com 1.
5. Pergunta "Gravar? [s/N]" (a menos que haja `--sim`).
6. Grava no local (falha → mensagem e saída 1). Depois no Aiven: se não estiver configurado, imprime "Aiven não configurado ([mysql_online] vazio): gravado SÓ no banco local."; se falhar, imprime "Aiven FALHOU (<erro>): gravado SÓ no banco local."
7. Lê de volta cada banco gravado e imprime OK ou "DIVERGÊNCIA no banco <x>, loja <y>: arquivo … × banco …".
8. Escreve o espelho e `conferencia_AAAA-MM.xlsx` para cada mês. `PermissionError` → "feche o arquivo X no Excel e rode de novo" (sem traceback).
9. Imprime o resumo do grupo. Pasta vazia → sincroniza só o cadastro (com confirmação) e diz isso.

- [ ] **Passo 1: testes que falham** (secrets temporário: `[mysql]` = `cfg_teste()`; `[mysql_online]` vazio ou apontando para `127.0.0.1` porta `1`, que é inalcançável e nunca o Aiven)
  - `test_bloqueio_nao_grava`: pasta com um arquivo de cargo inválido → retorno 1; saída contém "BLOQUEADA" e "linha"; `lancamentos` vazia.
  - `test_cancelar_na_confirmacao`: `entrada=lambda _: "n"` → retorno 1 e nada gravado.
  - `test_outubro_sim_grava_e_confere`: cópias de outubro em pasta temporária e `--sim --ano 2026` → retorno 0; saída contém "Aiven não configurado" e "OK"; o arquivo de conferência `conferencia_2026-10.xlsx` existe; o espelho existe.
  - `test_duas_execucoes_mesmos_totais`: rodar duas vezes deixa `totais_por_loja` igual.
  - `test_aiven_falha_grava_so_local`: online na porta 1 → retorno 0; saída contém "Aiven FALHOU" e "SÓ no banco local".
  - `test_espelho_aberto`: `patch` de `escrever_espelho` levantando `PermissionError` → saída contém "feche o arquivo"; retorno 0; dados gravados.
- [ ] **Passo 2:** rodar → FAIL. **Passo 3:** implementar. **Passo 4:** rodar → PASS.
- [ ] **Passo 5:** commit `feat: atualizar.py com prévia, bloqueios, gravação local+Aiven e conferência`.

### Task 7: Base do app: tema, navegação, cadeado e `db.py`

**Arquivos:** criar `app.py`, `db.py`, `paginas/__init__.py`, `paginas/comum.py`, `tests/test_app.py` (driver no estilo do Dahruj: grava em `tests/__pycache__` um script que substitui as funções de `db` por dados de outubro montados com `fabrica.base_de_lotes` e executa o `app.py`).

**Interfaces:**
- `db.get_engine()` (`st.cache_resource`, `banco.criar_engine(st.secrets["mysql"])`); `db.ler_base()` e `db.ler_historico()` (`st.cache_data(ttl=60)`); `db.salvar_correcao(loja_id, mes, pessoa_id, vendas) -> dict[str, list|str]` (grava em `[mysql]` e, se `online_preenchido(st.secrets.get("mysql_online"))`, também no online; devolve o resultado ou o erro por banco; limpa o cache).
- `paginas/comum.py`: `fmt_money`, `fmt_int`, `fmt_pct` ("—" para None/NaN), `mlabel`, `label_mes`, `PALETA = ["#000000","#404040","#707070","#9E9E9E","#C8C8C8"]`, `agg_por(df, grupo) -> DataFrame` (passagens/refis/a_receber com `min_count=1`; `total_*` NaN se alguma linha do grupo não tiver preço; aproveitamento = refil/passagens se > 0), `lojas_sem_preco(df) -> list[str]`, `aviso_preco(df)` (legenda), `excel_tabela(titulo, subtitulo, cabecalho, linhas, formatos) -> bytes` (cabeçalho preto `FF000000` com fonte branca Arial, zebra `FFF2F2F2`, linha TOTAL em negrito), `layout_grafico(fig)` (plotly_white, fundo transparente, texto preto).
- `app.py`: `Pagina = namedtuple("Pagina", "titulo funcao restrita")`; `PAGINAS = [Pagina("Dashboard", dashboard.pagina, False), Pagina("Relatório por Gerente", ...), Pagina("Relatório por Colaborador", ...), Pagina("Verbas", ...), Pagina("📝 Lançamento", ..., True), Pagina("🗂️ Histórico", ..., True)]`. O menu e o roteamento derivam só dessa lista. O cadeado, a sessão de 30 min, as 3 tentativas e o 1 min de espera seguem o Dahruj (mesmas chaves de `session_state`: `menu_pagina`, `lanc_ok`, `lanc_visto`, `btn_cadeado`, `pedir_senha_restrita`); a senha vem de `st.secrets["acesso"]["senha_lancamento"]`. CSS: `stSidebar` e `stHeader` com fundo `#000`, textos da barra lateral brancos, `stMetric` com fundo `#000`, texto branco e borda arredondada, botões primários pretos, radio selecionado em negrito branco. Logo: `st.sidebar.image(assets/logo.png)` no topo e `st.logo(...)` para o cabeçalho quando a barra recolhe; `page_title="Grupo TECAR — Refis para Palhetas"`.

- [ ] **Passo 1: testes que falham**: `tests/test_app.py`
  - `test_menu_publico`: opções do radio == as 4 públicas; sem exceção.
  - `test_restritas_com_acesso`: com `lanc_ok=True` → 6 opções.
  - `test_cadeado_senha_errada_e_certa`: replica `test_cadeado_exige_senha_e_libera_estoque` do Dahruj, com "📝 Lançamento".
  - `test_sessao_expirada`: com `lanc_visto` de 1801 s atrás, as restritas somem e a página volta para "Dashboard".
  - `test_lista_unica`: incluir uma `Pagina("Teste", f, False)` em `PAGINAS` (via driver) faz ela aparecer no menu.
  - `test_agg_sem_preco_nao_soma_zero` (unitário em `comum`): uma loja com preço e outra sem → `total_geral` do grupo NaN; `fmt_money(NaN) == "—"`.
- [ ] **Passo 2:** FAIL. **Passo 3:** implementar (as páginas podem ser stubs até a Task 8). **Passo 4:** PASS.
- [ ] **Passo 5:** commit `feat: app base com tema preto/branco, navegação por lista e área restrita`.

### Task 8: Páginas públicas

**Arquivos:** criar `paginas/dashboard.py`, `paginas/relatorio_gerente.py`, `paginas/relatorio_colaborador.py` e `paginas/verbas.py`; ampliar `tests/test_app.py`. Cada uma expõe `pagina() -> None` e uma função pura de Excel.

Todas usam só `grupo == "colaborador"` nas vendas e no faturamento. Disposição do Dahruj:

- **Dashboard:** mês de referência (mais recente primeiro) e trimestre móvel; filtros na barra lateral: Marca, Loja, **Cargo**, Colaborador; botão "📥 Exportar relatório (Excel)" (`gerar_excel_ranking` com coluna Cargo). KPIs em 2×3: Passagens, Nº Refil Diant., Aproveitamento Diant., Faturamento total, Nº Refil Tras., Aproveitamento Tras., com variação contra o mês anterior. Evolução em 4 gráficos de linha (série vazia → legenda "Sem dados de passagens no período" no lugar do gráfico). "Por loja" com o radio [Refis vendidos, Faturamento, Aproveitamento]. Ranking (ordenar por Nº Refil Dianteiro (padrão), Faturamento, Aproveitamento, Passagens), com rótulo "Nome (Cargo)". Expander com a tabela detalhada, incluindo Cargo.
- **Relatório por Gerente:** filtro de mês; ordenar por [Vendas da equipe, A Receber]. Uma linha por gerente: Seq, Gerente, Cargo, Loja, Marca, Equipe, Passagens, Vendas equipe (Refil Diant.), % Aprov, Total Diant., Refil Tras., Total Geral, Part %, Verba (R$/venda), A Receber. Mais uma linha "(sem gerente)" por loja sem gerente, com as vendas dos colaboradores da loja e Verba/A Receber "—". A linha TOTAL soma as vendas dos colaboradores do grupo (sem dupla contagem: 104 em outubro) e o A Receber dos gerentes (R$ 295). A legenda explica as duas coisas. Excel com as mesmas colunas.
- **Relatório por Colaborador:** Mês, Loja, Cargo (multiselect) e ordenar por [Vendas, A Receber, Faturamento]. Colunas: Seq, Colaborador, Cargo, Loja, Passagens, Refil Diant., % Aprov (D), Total Diant., Refil Tras., % Aprov (T), Total Tras., Total Geral, Part %, Verba (R$/venda), A Receber, mais TOTAL. Excel.
- **Verbas:** Ano, Mês ("Ano todo" + meses) e Loja. Cartões: "A receber — Colaboradores", "A receber — Gerentes", "Total a receber" e "Vendas (refis)". Tabela por loja (Vendas, A receber colaboradores, gerentes, total). Tabela mês a mês do ano com TOTAL. Tabela por pessoa (Nome, Cargo, Grupo, Loja, Verba R$/venda, Vendas, A Receber). Gráfico de barras agrupadas colaboradores × gerentes por mês, em preto e cinza. Excel com abas `Por loja`, `Mês a mês` e `Por pessoa`.

- [ ] **Passo 1: testes que falham** (driver com a base de outubro e o preço padrão de R$ 199)
  - `test_dashboard_outubro`: sem exceção; métrica "Nº Refil Diant. (Out/2026)" == "104"; "Faturamento total (Out/2026)" == "R$ 20.696,00"; "Passagens (Out/2026)" == "—"; existe 1 `download_button`; filtro Cargo com ["Consultor","Técnico","Vendedor de Peças"].
  - `test_relatorio_gerente_outubro`: a tabela tem os gerentes dos 3 gerentes (2 da Jeep, 1 da Mercedes Goiânia) + 2 linhas "(sem gerente)"; TOTAL Vendas "104"; TOTAL A Receber "R$ 295,00".
  - `test_relatorio_colaborador_filtro_cargo`: filtrar "Técnico" → 12 linhas + TOTAL com Refil Diant. "42" (Brasília 12 + Mercedes Goiânia 19 + Uberlândia 11); download presente.
  - `test_verbas_outubro`: cartões == ["R$ 1.310,00", "R$ 295,00", "R$ 1.605,00", "104"]; download presente; o Excel tem as abas `["Por loja","Mês a mês","Por pessoa"]`.
  - `test_faturamento_sem_preco`: driver com a Mercedes Brasília sem preço → "Faturamento total (Out/2026)" == "—" e uma legenda citando "Mercedes Brasília"; com o filtro só na Jeep Goiânia → "R$ 3.980,00".
- [ ] **Passo 2:** FAIL. **Passo 3:** implementar. **Passo 4:** PASS.
- [ ] **Passo 5:** commit `feat: páginas Dashboard, relatórios e Verbas`.

### Task 9: Páginas restritas (Lançamento e Histórico)

**Arquivos:** criar `paginas/lancamento.py` e `paginas/historico.py`; ampliar `tests/test_app.py`.

- **Lançamento:** trava redundante sem `lanc_ok`. Selects Loja → Mês (meses existentes da loja, mais recente primeiro) → Colaborador ("Nome — Cargo", só colaboradores). Mostra Verba, Vendas atuais e A Receber. `number_input` "Vendas corrigidas". Prévia: novo A Receber e os gerentes afetados (vendas e A Receber antes → depois, calculados em memória com a mesma regra do banco). Aviso de que a reimportação da loja/mês substitui a correção. Botão "Salvar correção" → `db.salvar_correcao`, com mensagem por banco (✅ local/online ou ❌ com o erro).
- **Histórico:** filtros Mês, Loja e Tipo (Importação/Correção); métricas Importações, Correções e Pessoas corrigidas; tabela (Registrado em, Tipo, Loja, Mês, Pessoa, Cargo, Vendas antes → depois, A Receber antes → depois, Arquivo, Detalhe); "📥 Exportar histórico (Excel)".

- [ ] **Passo 1: testes que falham**
  - `test_lancamento_bloqueado_sem_acesso`: chamar `lancamento.pagina()` com `session_state` vazio → `st.error` e nenhuma chamada a `db.ler_base`.
  - `test_lancamento_previa_gerentes`: loja Jeep, o consultor da linha 2 da Jeep, vendas 10 → a prévia mostra os 2 gerentes da Jeep com 22; clicar em "Salvar correção" chama `db.salvar_correcao` com (id da Jeep, 2026-10-01, id dele, 10).
  - `test_historico_exporta`: o driver com 4 importações + 3 correções dá as métricas "4" e "3", e há 1 download.
- [ ] **Passo 2:** FAIL. **Passo 3:** implementar. **Passo 4:** PASS.
- [ ] **Passo 5:** commit `feat: Lançamento (correção manual) e Histórico`.

### Task 10: README e verificação final

**Arquivos:** criar `README.md` e `.claude/launch.json` (na pasta de trabalho, se faltar, para o preview).

README, em passos para quem não programa:
1. Instalar (Python, `pip install -r requirements.txt`).
2. Criar o banco local (`python criar_banco.py`).
3. Criar o banco na Aiven: criar o serviço MySQL, baixar o `ca.pem` para `certs/aiven-ca.pem`, preencher `[mysql_online]` e rodar `python criar_banco.py --online`.
4. Preencher o secrets (o que é cada campo).
5. Atualização mensal (copiar para `entrada\`, rodar `python atualizar.py`, ler a prévia e os bloqueios, confirmar, ler a conferência em `conferencias\`, `--ano`, `--sim`).
6. Ajustar preços (`config/lojas.toml` + `python atualizar.py`).
7. Ajustar cargos (`config/cargos.toml`: cargo novo, grupo, equipe).
8. Área restrita (senha, Lançamento, Histórico).
9. Publicar no Streamlit Cloud (repositório privado no GitHub, o que o `.gitignore` deixa de fora, colar `[mysql]` = dados da Aiven com `ssl_ca` e `[acesso]` nos Secrets).
10. Incluir uma página nova (um item em `PAGINAS`).
11. Decisões de rotina (a lista acima).
12. O que ficou de fora do Dahruj e por quê:
    - unidades encerradas e Nissan Braz Leme (regra da Dahruj);
    - BYD;
    - lançamento por fotos (skill `lancar-fotos-dahruj`);
    - verbas de marketing e pagamentos (sem dados TECAR);
    - Sell In, estoque e reposição (página Estoque adiada);
    - passagens e aproveitamento (a TECAR não envia: aparecem como "—");
    - lançamentos semanais com nº e aba Semanal do histórico (a TECAR é mensal);
    - vigência consultor↔unidade (a pessoa é identificada por loja);
    - `seed.py`, `carregar_base.py` e `importar_verbas.py` (substituídos por `atualizar.py`);
    - `conferir_verbas.py` (substituído pela conferência automática);
    - skill de PDF por loja;
    - pisos fixos do eixo Y.

- [ ] **Passo 1:** escrever o README.
- [ ] **Passo 2 (superpowers:verification-before-completion):** mostrar a saída de cada comando:
  1. `python -m unittest discover -s tests -v` → `OK`, 0 falhas.
  2. `python criar_banco.py` com o `dashboard_tecar` inexistente (conferir antes com `SHOW DATABASES`) → lista de tabelas/views.
  3. Copiar os 4 arquivos de outubro para `entrada\` e rodar `python atualizar.py --ano 2026 --sim` → conferência OK com Jeep 20/200/200, Brasília 24/360/—, Mercedes Goiânia 38/475/95, Uberlândia 22/275/— e Grupo 104 / R$ 1.605; faturamento do grupo R$ 20.696,00 lido do banco. Mostrar também a planilha `conferencias\conferencia_2026-10.xlsx` lida com openpyxl.
  4. Rodar o mesmo comando de novo → os mesmos totais e `COUNT(*)` de lançamentos igual.
  5. `streamlit run app.py` no preview: navegar pelas 4 páginas públicas e, com a senha, pelas 2 restritas. Conferir que não há erro no console nem nos logs, que outubro/2026 aparece com as 4 lojas e que o download de cada página gera um .xlsx válido (gerar os bytes das funções de Excel com a base real e abrir com openpyxl). Fazer screenshots.
  6. O README cobre os itens 1–12 acima.
- [ ] **Passo 3:** commit `docs: README` e o resumo para o usuário.

> Nota (revisão final): os testes citam as pessoas pela posição na planilha (`tests/fabrica.py`, `POSICOES`); os nomes reais ficam só em `tests/dados`, fora do Git.
