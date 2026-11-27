-- Daily consumer. The result cache would answer repeated queries without reading storage,
-- which storage-only mode cannot see; the lab turns it off so reads reach the lake.
SET use_cached_result = false;

SELECT SUM(saldo) FROM cosmosproof_lab.silver.contas_ativas;

SELECT dia, receita FROM cosmosproof_lab.gold.receita_diaria ORDER BY dia DESC LIMIT 10;

SELECT SUM(valor) FROM delta.`${LAKE}/exports/parceiro_x`;

SELECT COUNT(*) FROM cosmosproof_lab.silver.saldos;
