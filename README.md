# Dashboard Grupo TECAR — Refis para Palhetas

Dashboard em Streamlit + MySQL para acompanhar a venda de refis de palheta nas
concessionárias do Grupo TECAR (Jeep Goiânia, Mercedes Brasília, Mercedes Goiânia
e Mercedes Uberlândia). Ele segue a estrutura do dashboard Dahruj.

- **Dashboard**: trimestre móvel por colaborador, loja e marca.
- **Relatório por Gerente**: gerentes do mês, com as vendas da equipe e a verba de cada um.
- **Relatório por Colaborador**: ranking do mês (Consultores, Vendedores de Peças e
  Técnicos juntos, cada um com o seu cargo), com filtro por cargo.
- **Verbas**: quanto cada pessoa tem a receber (VERBA × VENDAS), por loja e por mês.
- **📝 Lançamento** (com senha): corrige as vendas de uma pessoa num mês.
- **🗂️ Histórico** (com senha): cada importação e cada correção manual.

Todas as páginas exportam Excel. Os dados entram todo mês com **um comando**:
`python atualizar.py`. Você não precisa escrever SQL em nenhum momento.

> Nos comandos abaixo, abra o terminal **dentro da pasta `DASH TECAR`**
> (no Explorador de Arquivos: clique na barra de endereço, digite `powershell` e aperte Enter).

---

## 1. Instalar (uma vez)

1. Instale o **Python 3.12 ou mais novo** (python.org). Na instalação, marque *Add python.exe to PATH*.
2. Instale as bibliotecas:
   ```
   pip install -r requirements.txt
   ```
3. O **MySQL** local é o mesmo do Dahruj (servidor `127.0.0.1`, porta 3306). Ele precisa estar ligado.

## 2. Criar o banco local (uma vez)

```
python criar_banco.py
```

Esse comando cria o banco `dashboard_tecar` e as tabelas. Se você rodar de novo,
nada é apagado: ele só cria o que estiver faltando.
Para **apagar tudo e recomeçar**, use `python criar_banco.py --recriar`. O script pede para
você digitar `APAGAR`.

## 3. Preencher o secrets

O arquivo `.streamlit/secrets.toml` guarda as senhas. Ele **não vai para o GitHub**
(está no `.gitignore`). O modelo sem senhas é o `.streamlit/secrets.example.toml`.

| Seção | Para que serve | Campos |
|---|---|---|
| `[mysql]` | banco que o **app** lê. Nesta máquina, o MySQL local (já preenchido). | host, port, user, password, database |
| `[mysql_online]` | banco da **Aiven**. Usado pelo `atualizar.py` (grava no local e na Aiven), pelo `criar_banco.py --online` e pelas correções feitas nesta máquina. Enquanto estiver vazio, tudo grava só no local. | host, port, user, password, database, ssl_ca |
| `[acesso]` | senha do cadeado (Lançamento e Histórico). A senha inicial está só no seu `secrets.toml` local: **troque por uma senha forte** e use outra senha forte nos Secrets do Streamlit Cloud. | senha_lancamento |

## 4. Criar o banco na Aiven (uma vez)

1. Em [console.aiven.io](https://console.aiven.io), crie um serviço **MySQL** (o plano gratuito serve).
2. Quando o serviço estiver *Running*, abra **Overview → Connection information** e copie
   **Host**, **Port**, **User** e **Password** para a seção `[mysql_online]` do
   `.streamlit/secrets.toml`. Mantenha `database = "dashboard_tecar"`.
3. Na mesma tela, clique em **CA certificate → Download** e salve o arquivo como
   `certs\aiven-ca.pem`, dentro desta pasta. O secrets já aponta para esse caminho
   (`ssl_ca = "certs/aiven-ca.pem"`).
4. Crie as tabelas na Aiven:
   ```
   python criar_banco.py --online
   ```
   Se aparecer `OK.`, o banco online está pronto.
5. Rode a atualização mensal (seção 5). A partir daí, cada rodada grava nos dois bancos.

## 5. Atualização mensal (todo mês)

1. Copie os arquivos do mês para a pasta **`entrada\`**. Cada arquivo precisa ter o nome no
   padrão `VERBAS <MÊS> TECAR <LOJA>.xlsx`, por exemplo
   `VERBAS NOVEMBRO TECAR JEEP GOIANIA.xlsx`. Maiúsculas e acentos não importam.
2. Rode:
   ```
   python atualizar.py
   ```
   - O **mês** e a **loja** saem do nome do arquivo. O **ano** é o ano atual. Para outro
     ano, use `python atualizar.py --ano 2026` (por exemplo, ao importar dezembro em janeiro).
   - Para gravar sem a pergunta de confirmação: `python atualizar.py --sim`.
3. Leia a **prévia**. Para cada loja aparecem as pessoas, o cargo, as vendas, o A RECEBER,
   os gerentes (marcados `[G]`) e os avisos.
4. **Gravação bloqueada?** O script diz o arquivo, a linha e o motivo, e nada é gravado.
   Os motivos possíveis são:
   - cargo que não está em `config/cargos.toml`;
   - nome repetido na mesma loja;
   - loja que não está em `config/lojas.toml`;
   - mês ilegível no nome do arquivo;
   - A RECEBER diferente de VERBA × VENDAS;
   - valor que não é número;
   - dois arquivos da mesma loja e mês.

   Corrija a planilha (ou a configuração) e rode de novo.
5. **Avisos** não bloqueiam. São eles:
   - vendas do gerente diferentes da soma da equipe (é gravado o valor da planilha);
   - loja sem preço;
   - correção manual que será substituída.
6. Confirme com `s`. O script então:
   - grava no banco local e, se a Aiven estiver configurada, na Aiven. Se a Aiven falhar,
     ele grava só no local e diz isso claramente;
   - **lê de volta** de cada banco e confere vendas e A RECEBER por loja contra os arquivos.
     Se algo não bater, mostra em qual banco e em qual loja;
   - registra a importação no **Histórico**;
   - reescreve o **`BASE GRUPO TECAR.xlsx`**, o espelho do banco com todos os meses;
   - gera **`conferencias\conferencia_AAAA-MM.xlsx`**, com os totais por loja do arquivo,
     do banco local e da Aiven, mais a lista de avisos.

**Rodar o mesmo mês de novo substitui o mês daquela loja**, sem duplicar. Isso também
desfaz as correções manuais desse mês (a prévia avisa antes).
Se o `BASE GRUPO TECAR.xlsx` ou a conferência estiverem abertos no Excel, o script pede
para fechar o arquivo. Os dados no banco já ficam gravados mesmo assim.

## 6. Ajustar preços

Abra `config/lojas.toml` no Bloco de Notas. O preço de venda de cada loja está em
`preco_diant` (hoje R$ 199). Depois de salvar, rode:
```
python atualizar.py
```
Com a pasta `entrada` vazia, o script só atualiza lojas, preços e cargos nos bancos.
O preço vale para **todos os meses** da loja. Se ficar vazio (`""`), o faturamento aparece
como **—**.

## 7. Ajustar cargos

Abra `config/cargos.toml`. Cada `[[cargo]]` tem um `nome`, um `grupo` e, no caso de
gerente, uma `equipe`:
- `grupo = "colaborador"`: as vendas entram no total da loja e nos rankings;
- `grupo = "gerente"`: as vendas são a soma da equipe e **não entram** no total da loja,
  mas a verba (A RECEBER) entra no total de verbas.

Quando aparecer um cargo novo na planilha, copie um bloco, ajuste os campos e rode
`python atualizar.py` de novo. Não precisa mexer no código. Maiúsculas, acentos e espaços
não importam ("Tecnico" = "Técnico").

Para **incluir uma loja nova**, copie um bloco `[[loja]]` em `config/lojas.toml`.

## 8. Área restrita

As páginas **Lançamento** e **Histórico** só aparecem depois de clicar no **cadeado 🔒**,
no fim da barra lateral, e digitar a senha (`[acesso] senha_lancamento`). O acesso trava
de novo quando você clica no 🔓, depois de 30 minutos sem uso ou ao recarregar a página.
Depois de 3 senhas erradas, o app espera 1 minuto.

- **Lançamento**: escolha a loja, o mês e o colaborador e digite as vendas corrigidas.
  A prévia mostra o novo A RECEBER e os gerentes recalculados (os gerentes da equipe
  daquele cargo). A correção grava no banco do app e, nesta máquina, também na Aiven.
  Ela não reescreve o `BASE GRUPO TECAR.xlsx`: isso acontece na próxima vez que você
  rodar o `atualizar.py`.
- **Histórico**: lista cada importação (uma linha por loja e mês) e cada correção
  (uma linha por pessoa), com o valor antes e depois e a opção de exportar para Excel.

## 9. Abrir o dashboard nesta máquina

```
streamlit run app.py
```
O dashboard abre em `http://localhost:8501`.

## 10. Publicar no Streamlit Cloud

1. Crie um repositório **privado** no GitHub e envie esta pasta (pelo GitHub Desktop:
   *File → Add local repository*, escolha `DASH TECAR` e depois *Publish repository*,
   deixando marcado *Keep this code private*). O `.gitignore` deixa de fora o
   `secrets.toml` e os dados reais: `entrada\`, `conferencias\`, `BASE GRUPO TECAR.xlsx`
   e `tests\dados\`. O `certs\aiven-ca.pem` vai junto, porque é um certificado público
   e a nuvem precisa dele.
2. Em [share.streamlit.io](https://share.streamlit.io), clique em **Create app**, escolha o
   repositório e o arquivo `app.py`.
3. Em **Advanced settings → Secrets**, cole:
   ```toml
   [mysql]
   host = "<host da Aiven>"
   port = <porta da Aiven>
   user = "avnadmin"
   password = "<senha da Aiven>"
   database = "dashboard_tecar"
   ssl_ca = "certs/aiven-ca.pem"

   [acesso]
   senha_lancamento = "<a senha do cadeado>"
   ```
   Na nuvem, a seção `[mysql]` recebe os dados da **Aiven**. Não coloque `[mysql_online]`.
4. Clique em **Deploy**. Todo mês, o `python atualizar.py` rodado nesta máquina atualiza
   a Aiven, e o dashboard publicado mostra os dados novos em até 60 segundos.

## 11. Incluir uma página nova (ex.: Estoque)

1. Crie `paginas/estoque.py` com uma função `pagina()`.
2. Em `app.py`, importe o módulo e acrescente **uma linha** na lista `PAGINAS`:
   ```python
   Pagina("📦 Estoque", estoque.pagina, True),   # True = só com senha
   ```
O menu e a navegação são montados só a partir dessa lista.

## 12. Arquivos

| Arquivo | Função |
|---|---|
| `app.py` | Navegação (lista `PAGINAS`), tema preto/branco, logo e cadeado. |
| `paginas/` | Uma página por arquivo, mais `comum.py` (formatos, agregações e Excel). |
| `db.py` | Leitura do banco pelo app (cache de 60 s) e gravação das correções. |
| `atualizar.py` | Atualização mensal (prévia → bloqueios → gravação → conferência → Excel). |
| `criar_banco.py` | Cria o banco e as tabelas (local, ou `--online` para a Aiven). |
| `schema.sql` | Tabelas `lojas`, `cargos`, `pessoas`, `lancamentos`, `historico` e view `vw_base`. |
| `tecar/` | Regras sem tela: configuração, leitura das planilhas, banco, espelho e conferência. |
| `config/lojas.toml`, `config/cargos.toml` | Lojas, preços, cargos e equipes (editáveis). |
| `entrada/` | Onde você coloca as planilhas do mês. |
| `conferencias/` | Um Excel de conferência por mês importado. |
| `BASE GRUPO TECAR.xlsx` | Espelho do banco (abas Consultores, Gerentes e Preço por Unidade). |
| `tests/` | Testes automáticos: `python -m unittest discover -s tests -v`. |

Os testes usam um banco separado, o `dashboard_tecar_teste`, no MySQL local, e **nunca**
gravam na Aiven.

## 13. Como os números são calculados

- **Vendas** = coluna VENDAS da planilha, gravada como *Refil Dianteiro*. O *Refil
  Traseiro* é sempre 0 e as **Passagens** ficam vazias, porque a TECAR não envia esses
  dados. Por isso o **aproveitamento** aparece como "—".
- **Vendas da loja / do grupo** = só os colaboradores. As vendas de um gerente são a soma
  da equipe dele (Gerente Peças e Gerente Pós Vendas: Consultores e Vendedores de Peças;
  Chefe de oficina: Técnicos) e nunca entram no total.
- **A RECEBER** = VERBA (R$ por venda) × VENDAS, igual à planilha. O total de verbas soma
  colaboradores e gerentes.
- **Faturamento** = vendas × preço da loja (R$ 199). Se alguma loja do recorte estiver
  sem preço, o total aparece como "—" em vez de um valor parcial.
- Lojas sem gerente na planilha (hoje Brasília e Uberlândia) aparecem como "(sem gerente)"
  no Relatório por Gerente.

Conferência de outubro/2026:

| Loja | Vendas | A receber colaboradores | A receber gerentes |
|---|---|---|---|
| Jeep Goiânia | 20 | R$ 200 | R$ 200 |
| Mercedes Brasília | 24 | R$ 360 | sem gerente |
| Mercedes Goiânia | 38 | R$ 475 | R$ 95 |
| Mercedes Uberlândia | 22 | R$ 275 | sem gerente |
| **Grupo** | **104** | | **R$ 1.605 no total** |

O faturamento do grupo nesse mês foi de R$ 20.696,00.

## 14. Decisões tomadas na construção

1. **Logo**: o anexo veio sem transparência (fundo preto). `assets/logo.png` foi
   regravada com transparência calculada pelo brilho. Se você tiver o PNG original
   transparente, basta substituir o arquivo.
2. **Preço**: vale para todos os meses da loja. Mudar o preço recalcula o histórico inteiro.
3. **Faturamento com loja sem preço**: o total do recorte aparece como "—", nunca como
   soma parcial.
4. **Vendas do gerente**: a importação grava o valor da planilha e avisa se for diferente
   da soma da equipe. A correção manual de um colaborador recalcula os gerentes da equipe
   dele. Gerente não se corrige direto.
5. **Correção × reimportação**: reimportar a loja e o mês substitui a correção manual.
   A prévia avisa antes.
6. **Correções** gravam no banco do app e, nesta máquina, também na Aiven.
7. **`BASE GRUPO TECAR.xlsx`** guarda valores, não fórmulas, porque é a fotografia do banco.
   Ele mantém as abas e os cabeçalhos do template e acrescenta no fim `Cargo`,
   `Verba (R$/venda)` e `A Receber (R$)`. Os dados fictícios do template foram apagados.
8. **Senha** só no secrets. Sem ela, o cadeado avisa que a senha não está configurada.
9. **Dados reais fora do Git** (`entrada`, `conferencias`, `BASE GRUPO TECAR.xlsx` e
   `tests/dados`). Os testes que usam as planilhas de outubro são pulados quando
   `tests/dados/outubro` não existe.
10. **`--ano`**: o padrão é o ano atual.
11. **Marca** das lojas Mercedes = "Mercedes-Benz" (dá para mudar em `config/lojas.toml`).
12. **Part %** nos relatórios = participação nas **vendas** (o faturamento pode estar "—").
13. **Aiven falhou?** O `atualizar.py` termina com código 0, porque o local foi gravado e
    conferido, e escreve em destaque "Aiven FALHOU … gravado SÓ no banco local". Código 2
    = divergência na conferência; código 1 = bloqueado, cancelado ou erro no banco local.
14. A linha GRUPO do Excel de conferência usa fórmulas `=SUM`, que o Excel calcula ao abrir.
15. **Fundo do conteúdo** em cinza-claro neutro (`#E9E9E6`), e não em branco puro, que
    cansava a vista. A cor fica em `.streamlit/config.toml` (`backgroundColor`).

## 15. O que ficou de fora do Dahruj, e por quê

| Função do Dahruj | Por que ficou de fora |
|---|---|
| Unidades encerradas / Nissan Braz Leme | Regra específica da Dahruj. |
| BYD | Regra específica da Dahruj. |
| Lançamento por fotos (skill `lancar-fotos-dahruj`) | Fora do escopo; a TECAR envia planilha. |
| Verbas de marketing e pagamentos (`verbas_pagamentos`, `verbas_marketing_pagos`) | A TECAR não envia esses dados. |
| Sell In, estoque e reposição (página Estoque, `estoque_pagina.py`) | Página adiada; pode ser incluída depois (seção 11). |
| Passagens e aproveitamento | A TECAR não envia passagens: aparecem como "—". |
| Lançamentos semanais (nº do lançamento, aba "Semanal" do histórico) | A TECAR é mensal; o Histórico registra importações e correções. |
| Vigência consultor ↔ unidade (`consultor_unidade`) | A pessoa é identificada pelo nome dentro da loja. |
| `seed.py`, `carregar_base.py`, `importar_verbas.py` | Substituídos pelo `atualizar.py`. |
| `conferir_verbas.py` | Substituído pela conferência automática do `atualizar.py`. |
| Skill de PDF por loja (`analise-lojas-dahruj`) | Fora do escopo. |
| Pisos fixos do eixo Y dos gráficos | Valores da Dahruj; aqui os eixos começam do zero. |
