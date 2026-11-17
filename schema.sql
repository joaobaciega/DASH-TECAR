-- =============================================================================
--  Dashboard Grupo TECAR — esquema do banco (MySQL 8)
--
--  NÃO rode este arquivo à mão: use  python criar_banco.py  (local) ou
--  python criar_banco.py --online  (Aiven). O script cria o banco com o nome
--  que está no .streamlit/secrets.toml e aplica os comandos abaixo.
--
--  Tudo é "IF NOT EXISTS": rodar de novo não apaga dados.
--  Para recriar do zero (APAGA tudo): python criar_banco.py --recriar
-- =============================================================================

-- -----------------------------------------------------------------------------
-- lojas: espelho de config/lojas.toml (o atualizar.py sincroniza a cada rodada).
--   chave        nome da loja como aparece no arquivo (sem acento, maiúsculo)
--   preco_*      R$ por refil; NULL = sem preço (faturamento aparece como —)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lojas (
  id           INT           NOT NULL AUTO_INCREMENT,
  chave        VARCHAR(80)   NOT NULL,
  nome         VARCHAR(120)  NOT NULL,
  marca        VARCHAR(60)   NOT NULL,
  cidade       VARCHAR(80)   NOT NULL,
  preco_diant  DECIMAL(10,2) NULL,
  preco_tras   DECIMAL(10,2) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_loja_chave (chave)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- cargos: espelho de config/cargos.toml.
--   grupo   'colaborador' (vendas somam na loja) | 'gerente' (vendas = equipe)
--   equipe  cargos da equipe do gerente, separados por ';'
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cargos (
  nome    VARCHAR(60)  NOT NULL,
  grupo   ENUM('colaborador','gerente') NOT NULL,
  equipe  VARCHAR(255) NULL,
  PRIMARY KEY (nome)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- pessoas: uma por nome DENTRO de cada loja (chave = nome sem acento/maiúsculo).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pessoas (
  id       INT          NOT NULL AUTO_INCREMENT,
  loja_id  INT          NOT NULL,
  nome     VARCHAR(150) NOT NULL,
  chave    VARCHAR(150) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_pessoa (loja_id, chave),
  CONSTRAINT fk_pessoa_loja FOREIGN KEY (loja_id) REFERENCES lojas (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- lancamentos: uma linha por pessoa / loja / mês (o que veio da planilha).
--   refil_diant  = VENDAS da planilha (para gerente: vendas da equipe)
--   refil_tras   = 0 (a TECAR não envia traseiro)
--   passagens    = NULL (a TECAR não envia)
--   verba        = R$ por venda; a_receber = verba × vendas
--   origem       'importacao' (atualizar.py) | 'correcao' (página Lançamento)
-- Reimportar a loja/mês APAGA e regrava as linhas daquela loja/mês.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lancamentos (
  id            INT           NOT NULL AUTO_INCREMENT,
  pessoa_id     INT           NOT NULL,
  loja_id       INT           NOT NULL,
  mes           DATE          NOT NULL,
  cargo         VARCHAR(60)   NOT NULL,
  grupo         ENUM('colaborador','gerente') NOT NULL,
  passagens     INT           NULL,
  refil_diant   INT           NOT NULL DEFAULT 0,
  refil_tras    INT           NOT NULL DEFAULT 0,
  verba         DECIMAL(10,2) NOT NULL DEFAULT 0,
  a_receber     DECIMAL(12,2) NOT NULL DEFAULT 0,
  origem        ENUM('importacao','correcao') NOT NULL DEFAULT 'importacao',
  atualizado_em TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_lancamento (pessoa_id, loja_id, mes),
  KEY idx_lanc_loja_mes (loja_id, mes),
  CONSTRAINT fk_lanc_pessoa FOREIGN KEY (pessoa_id) REFERENCES pessoas (id),
  CONSTRAINT fk_lanc_loja FOREIGN KEY (loja_id) REFERENCES lojas (id),
  CONSTRAINT chk_lanc_nao_negativo CHECK (refil_diant >= 0 AND refil_tras >= 0
                                          AND (passagens IS NULL OR passagens >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- historico: cada importação (uma linha por loja/mês) e cada correção manual
-- (uma linha por pessoa alterada). Só recebe INSERT: o app nunca apaga.
-- Guarda NOMES (não ids) para continuar legível se o cadastro mudar.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historico (
  id                BIGINT        NOT NULL AUTO_INCREMENT,
  registrado_em     TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  tipo              ENUM('importacao','correcao') NOT NULL,
  loja              VARCHAR(120)  NOT NULL,
  mes               DATE          NOT NULL,
  pessoa            VARCHAR(150)  NULL,
  cargo             VARCHAR(60)   NULL,
  vendas_antes      INT           NULL,
  vendas_depois     INT           NULL,
  a_receber_antes   DECIMAL(12,2) NULL,
  a_receber_depois  DECIMAL(12,2) NULL,
  arquivo           VARCHAR(255)  NULL,
  detalhe           VARCHAR(500)  NULL,
  PRIMARY KEY (id),
  KEY idx_hist_mes (mes)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- vw_base: o que o dashboard lê. Faturamento calculado na leitura:
--   total_diant = refil_diant × preco_diant  (NULL se a loja está sem preço)
--   total_tras  = 0 quando não há traseiro; senão refil_tras × preco_tras
--   aproveitamento = refil_diant / passagens (NULL sem passagens)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_base AS
SELECT
  p.id                                   AS pessoa_id,
  p.nome                                 AS pessoa,
  l.cargo                                AS cargo,
  l.grupo                                AS grupo,
  lo.id                                  AS loja_id,
  lo.chave                               AS loja_chave,
  lo.nome                                AS loja,
  lo.marca                               AS marca,
  lo.cidade                              AS cidade,
  l.mes                                  AS mes,
  DATE_FORMAT(l.mes, '%m/%Y')            AS mes_label,
  l.passagens                            AS passagens,
  l.refil_diant                          AS refil_diant,
  l.refil_tras                           AS refil_tras,
  CASE WHEN l.passagens > 0 THEN ROUND(l.refil_diant / l.passagens, 4) END AS aproveitamento,
  l.verba                                AS verba,
  l.a_receber                            AS a_receber,
  l.origem                               AS origem,
  lo.preco_diant                         AS preco_diant,
  lo.preco_tras                          AS preco_tras,
  ROUND(l.refil_diant * lo.preco_diant, 2) AS total_diant,
  CASE WHEN l.refil_tras = 0 THEN 0
       ELSE ROUND(l.refil_tras * lo.preco_tras, 2) END AS total_tras,
  ROUND(l.refil_diant * lo.preco_diant
        + CASE WHEN l.refil_tras = 0 THEN 0 ELSE l.refil_tras * lo.preco_tras END, 2)
                                         AS total_geral
FROM lancamentos l
JOIN pessoas p  ON p.id  = l.pessoa_id
JOIN lojas   lo ON lo.id = l.loja_id;
