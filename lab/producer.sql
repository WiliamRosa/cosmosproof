-- Daily producer: appends to S3, appends to S4 and rebuilds the gold table from it.
INSERT INTO cosmosproof_lab.bronze.eventos_cdc
  SELECT id + unix_timestamp() * 1000, 'UPDATE', current_timestamp() FROM range(0, 1000);

INSERT INTO cosmosproof_lab.bronze.transacoes_raw
  SELECT id + unix_timestamp() * 1000, current_date(), CAST(rand() * 500 AS DECIMAL(18, 2))
  FROM range(0, 1000);

INSERT OVERWRITE cosmosproof_lab.gold.receita_diaria
  SELECT dia, SUM(valor) AS receita FROM cosmosproof_lab.bronze.transacoes_raw GROUP BY dia;
