-- CosmosProof lab: fictional data covering the situations CosmosProof must judge.
-- ${LAKE} is replaced by deploy.py with an abfss:// URL under a Unity Catalog external location.
-- All names, CPFs and emails are generated and fictional.

CREATE CATALOG IF NOT EXISTS cosmosproof_lab MANAGED LOCATION '${LAKE}/managed'
  COMMENT 'CosmosProof lab with fictional data, safe to delete';
CREATE SCHEMA IF NOT EXISTS cosmosproof_lab.raw;
CREATE SCHEMA IF NOT EXISTS cosmosproof_lab.bronze;
CREATE SCHEMA IF NOT EXISTS cosmosproof_lab.silver;
CREATE SCHEMA IF NOT EXISTS cosmosproof_lab.gold;
CREATE SCHEMA IF NOT EXISTS cosmosproof_lab.archive;

-- S1 used every day: the consumer job reads it.
CREATE TABLE IF NOT EXISTS cosmosproof_lab.silver.contas_ativas
  LOCATION '${LAKE}/silver/contas_ativas'
  AS SELECT id AS id_conta, id % 5000 AS id_cliente, CAST(rand(1) * 10000 AS DECIMAL(18, 2)) AS saldo
     FROM range(0, 200000);

-- S2 dead table with personal data: never read.
CREATE TABLE IF NOT EXISTS cosmosproof_lab.raw.clientes_legado_2019
  LOCATION '${LAKE}/raw/clientes_legado_2019'
  AS SELECT id AS id_cliente,
            lpad(CAST(id AS STRING), 11, '0') AS cpf,
            concat('cliente', id, '@example.com') AS email,
            concat('+55 11 9', lpad(CAST(id AS STRING), 8, '0')) AS telefone,
            concat('Cliente Ficticio ', id) AS nome_completo,
            date_add(DATE '2019-01-01', CAST(id % 365 AS INT)) AS data_cadastro
     FROM range(0, 100000);

-- S3 still fed, never read: the producer job appends to it every day.
CREATE TABLE IF NOT EXISTS cosmosproof_lab.bronze.eventos_cdc
  LOCATION '${LAKE}/bronze/eventos_cdc'
  AS SELECT id AS id_evento, 'INSERT' AS operacao, current_timestamp() AS capturado_em
     FROM range(0, 50000);

-- S4 intermediate table of a used pipeline: the producer reads it to build gold, which is used.
CREATE TABLE IF NOT EXISTS cosmosproof_lab.bronze.transacoes_raw
  LOCATION '${LAKE}/bronze/transacoes_raw'
  AS SELECT id AS id_transacao, date_add(DATE '2026-01-01', CAST(id % 330 AS INT)) AS dia,
            CAST(rand(2) * 500 AS DECIMAL(18, 2)) AS valor
     FROM range(0, 300000);
CREATE TABLE IF NOT EXISTS cosmosproof_lab.gold.receita_diaria
  LOCATION '${LAKE}/gold/receita_diaria'
  AS SELECT dia, SUM(valor) AS receita FROM cosmosproof_lab.bronze.transacoes_raw GROUP BY dia;

-- S5 orphan storage nobody reads: external table dropped, files left behind.
CREATE TABLE IF NOT EXISTS cosmosproof_lab.raw.tmp_campanha
  LOCATION '${LAKE}/exports/campanha_2024'
  AS SELECT id, concat('lead-', id) AS lead FROM range(0, 80000);
DROP TABLE IF EXISTS cosmosproof_lab.raw.tmp_campanha;

-- S6 orphan storage read by path every day.
CREATE TABLE IF NOT EXISTS cosmosproof_lab.raw.tmp_parceiro
  LOCATION '${LAKE}/exports/parceiro_x'
  AS SELECT id, CAST(rand(3) * 100 AS DECIMAL(18, 2)) AS valor FROM range(0, 40000);
DROP TABLE IF EXISTS cosmosproof_lab.raw.tmp_parceiro;

-- S7 cold history never read; deploy.py prints the command that moves it to Cool.
CREATE TABLE IF NOT EXISTS cosmosproof_lab.archive.historico_2020
  LOCATION '${LAKE}/archive/historico_2020'
  AS SELECT id, date_add(DATE '2020-01-01', CAST(id % 366 AS INT)) AS dia,
            CAST(rand(4) * 1000 AS DECIMAL(18, 2)) AS valor
     FROM range(0, 250000);

-- S8 managed table nobody reads.
CREATE TABLE IF NOT EXISTS cosmosproof_lab.gold.relatorio_antigo
  AS SELECT id, CAST(rand(5) * 100 AS DECIMAL(18, 2)) AS indicador FROM range(0, 20000);

-- S9 duplicate copy of S2 (for future duplicate detection).
CREATE TABLE IF NOT EXISTS cosmosproof_lab.raw.clientes_copia
  LOCATION '${LAKE}/raw/clientes_copia'
  AS SELECT * FROM cosmosproof_lab.raw.clientes_legado_2019;

-- S10 only COUNT(*) every day: answered from Delta statistics, so storage sees no data read.
CREATE TABLE IF NOT EXISTS cosmosproof_lab.silver.saldos
  LOCATION '${LAKE}/silver/saldos'
  AS SELECT id, CAST(rand(6) * 100 AS DECIMAL(18, 2)) AS saldo FROM range(0, 60000);
