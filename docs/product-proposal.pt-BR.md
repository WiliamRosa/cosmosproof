# Proposta de produto: dado sem uso no Azure Databricks — custo, risco e PII

Status: aceita em 26/11/2026 como documento de fundação do produto. As decisões tiradas dela ficam em [docs/decisions](decisions/).

Nome: **CosmosProof** ([ADR 0001](decisions/0001-name-scope-and-promise.md)). É um produto separado e menor que o Cosmos Semantic, vendido em oferta própria, não mais uma funcionalidade dentro dele.

## 1. Promessa central

> **Mostramos, com prova, o que no seu Azure Databricks custa dinheiro, gera risco ou guarda PII sem ser usado.**

Um mapa, três leituras:

| Leitura | Pergunta que responde | Quem presta atenção |
|---|---|---|
| **Custo (FinOps)** | O que eu pago e ninguém lê? | Líder de plataforma de dados, FinOps, área financeira |
| **Risco** | Quais credenciais de produção e cargas no banco existem sem uso real? | Segurança, DBA, engenharia de plataforma |
| **Compliance** | Que dado pessoal está guardado sem finalidade em uso? | DPO, compliance, auditoria interna |

## 2. Por que um produto menor

O Cosmos Semantic faz muitas coisas bem, mas responde "o que ele faz?" com uma lista. Este produto responde com uma frase e um número. O mercado de custo de dados tem um lado lotado e um lado quase vazio:

- **Lotado: otimização de computação.** Keebo, Espresso AI, Unravel, Select e Revefi já ajustam warehouses, clusters e queries, e a Flexera comprou a Chaos Genius em janeiro de 2026. Não vale entrar.
- **Quase vazio: dado armazenado que ninguém lê, no Azure.** A Masthead marca tabelas sem uso (30 dias sem consumo), mas é focada em BigQuery e avisa sobre falsos positivos. A Revefi oferece isso para Snowflake e BigQuery. Nenhuma das duas trabalha no nível de arquivo do ADLS. Microsoft e Databricks entregam peças soltas (último acesso no ADLS, Blob Inventory, Azure Storage Discovery, tabelas de sistema do Unity Catalog), mas ninguém cruza essas peças. Um responsável da Microsoft confirmou em fórum que o Fabric não destaca storage órfão ou sem uso no OneLake.

A lacuna: ninguém cruza **arquivo no ADLS ↔ tabela do Unity Catalog ↔ histórico de consultas ↔ uso do lado do banco** para dizer "você paga por isso, ninguém lê, e aqui está a prova".

## 3. Escopo

Ponto de observação: **Azure Databricks**. Tudo o que chega nele ou é lido por ele.

| Fonte | O que é "sem uso" | Evidência disponível | Leitura principal |
|---|---|---|---|
| **ADLS Gen2** (external locations, volumes, tabelas externas) | Arquivo pago e não lido | Último acesso + Blob Inventory + lineage do Unity Catalog | Custo |
| **Lakeflow Connect** (ingestão CDC de SQL Server e PostgreSQL) | Tabela ingerida que ninguém lê depois | `system.access.table_lineage` + `system.query.history` nas tabelas de destino | Custo (caso mais forte: o gateway de CDC roda continuamente) |
| **Lakehouse Federation** (foreign catalogs em PostgreSQL Flexible Server, Azure SQL) | Conexão ou tabela federada que ninguém consulta | A Databricks documenta que o lineage de foreign tables é rastreado como o de tabelas normais do Unity Catalog | Risco |
| **Lado do banco** (PostgreSQL Flexible Server, Azure SQL / SQL Server) | Tabela que ninguém lê, não só o Databricks | `pg_stat_user_tables`, `sys.dm_db_index_usage_stats` | Custo, risco |
| **JDBC direto em notebook** (`spark.read.jdbc`) | Não mensurável | Provavelmente invisível ao lineage | Reportado como ponto cego declarado |

Maturidade dos conectores: o Lakeflow Connect para SQL Server é GA (Azure SQL Database e Managed Instance). O de PostgreSQL está em Public Preview e cita o Azure Database for PostgreSQL.

**Fora do escopo por enquanto:** Azure Data Factory, Microsoft Fabric, Power BI/DAX, Event Hubs, inferência de schema de arquivos soltos (CSV/Excel/XML/JSON).

## 4. Modelo de prova: o diferencial real

O ponto fraco declarado dos concorrentes é o falso positivo. Um banco não apaga nem muda tier de nada com base em palpite. Por isso cada achado traz:

- **Fontes de evidência** que o sustentam (ex.: "nenhuma leitura em `table_lineage` há 210 dias; nenhuma linha em `query.history`; último acesso no ADLS em 02/03/2026").
- **Nível de confiança**, calculado a partir de quantas fontes independentes concordam e das lacunas de cobertura conhecidas. O lineage só registra eventos que consegue inferir (uma minoria das queries, segundo documentação de terceiros), então a ausência de um único sinal nunca significa "sem uso".
- **Data de referência e janela de observação.**
- **Notas de cobertura** dizendo o que não pôde ser visto (ex.: "esta tabela também é acessível por JDBC direto, que não é observável").

É a mesma ideia do evidence envelope do Cosmos Semantic (fórmula, versão da regra, hash, data de referência), aplicada a custo e risco em vez de métricas.

Duas regras saem disso:
1. **"Não usado pelo Databricks" não é "não usado".** PostgreSQL e SQL Server atendem outras aplicações. As estatísticas do próprio banco separam "ninguém lê" de "só o Databricks não lê". A DMV do SQL Server zera a cada restart, e isso precisa aparecer como nota de cobertura.
2. **O produto nunca apaga nada automaticamente.** Ele recomenda, com evidência. Quem age é um humano.

## 5. As três leituras em detalhe

### 5.1 Custo (FinOps)

- **Storage morto no ADLS:** caminhos e tabelas externas sem leitura na janela, com custo mensal por tier.
- **Ingestão morta:** pipelines do Lakeflow Connect cujas tabelas de destino ninguém lê. A computação do gateway é paga todo dia.
- **Dado pago várias vezes:** a mesma tabela de origem trazida pelo Lakeflow Connect, lida por JDBC num notebook e exposta via federation. Detectado comparando host, banco e tabela de cada conexão. "Você paga três vezes para trazer a mesma tabela" é uma mensagem que ninguém está entregando.
- **Recomendações de tier** que respeitam as penalidades de retenção mínima (90 dias no cold).
- **A validar:** a otimização preditiva da Databricks só faz manutenção de tabelas *gerenciadas* do Unity Catalog. Bancos costumam ter muitas tabelas Delta *externas* no ADLS, com histórico e snapshots que ninguém limpa. Se confirmado, é storage recuperável adicional.

### 5.2 Risco

- **Conexões de federation sem uso** que ainda guardam credencial de produção. É superfície de ataque sem valor de negócio.
- **Ingerir ou federar, com base no uso real:**
  - Uma tabela federada consultada o tempo todo está martelando o banco transacional e deveria ser ingerida.
  - Uma tabela ingerida e lida uma vez por mês está pagando gateway de CDC contínuo e deveria ser federada.

  Isso otimiza custo e risco operacional ao mesmo tempo, e é específico do ecossistema Databricks.

### 5.3 Compliance (PII)

- **Dado pessoal parado, sem finalidade em uso.** Dado pessoal identificável (PII) guardado sem finalidade ativa é um passivo de privacidade, não só um custo.
- O Cosmos já detecta colunas sensíveis por regex (`cosmos bootstrap`, sinalização de PII). Cruzar "contém CPF" com "ninguém leu nos últimos 180 dias" transforma um relatório de FinOps em relatório de compliance. Num banco, compliance tem orçamento próprio, muitas vezes mais fácil de aprovar do que ferramenta de custo.

## 6. Valor recorrente: o ciclo contínuo

Sem isso, é uma auditoria única: o cliente roda uma vez, limpa e não tem motivo para continuar pagando.

1. **Alertas de desperdício novo.** Exemplo: "este pipeline do Lakeflow criado há 30 dias alimenta uma tabela que ninguém leu." O desperdício é pego quando aparece, não um ano depois.
2. **Dono do desperdício.** Usar owners e tags do Unity Catalog para atribuir achados de custo, risco e compliance a um time. Isso permite showback ou chargeback e dá um responsável para cada achado.
3. **Registro de economia realizada.** Cada ação tomada fica registrada com sua evidência e o valor economizado ou o risco removido. Prova o retorno ao longo do tempo e abre a opção de cobrar um percentual da economia.

## 7. Entrega e arquitetura (alto nível)

- **Azure Marketplace Managed Application**, o mesmo modelo que acabamos de publicar para o Cosmos Semantic. Roda na assinatura do cliente, com a managed identity dele e os papéis que ele escolher. O inventário de dados nunca sai do tenant, um argumento de confiança tão forte quanto a funcionalidade em si para um banco.
- **Reaproveitado do Cosmos:** conectores de PostgreSQL e SQL Server, detecção de PII, modelo de evidência, padrões do console, template de deploy.
- **Novo:** autenticação de saída para o Azure (managed identity), leitores das tabelas de sistema do Unity Catalog e do Blob Inventory, o motor de cruzamento, o ciclo de alertas e o registro de economia.

Permissões que o cliente concede:

| Acesso | Para quê |
|---|---|
| `USE` e `SELECT` nos schemas de sistema do Databricks | Lineage e histórico de consultas |
| Storage Blob Data Reader + uma regra de Blob Inventory | Lista de arquivos, tiers, último acesso |
| Rastreamento de último acesso habilitado na conta de storage | Gratuito; só registra a partir da ativação |
| Login SQL com permissão de estatísticas de uso em cada banco | Uso do lado do banco (precisa ficar explícito no onboarding) |

**Valor no primeiro dia:** o último acesso do ADLS só começa a contar depois de habilitado, mas as tabelas de sistema do Unity Catalog já guardam cerca de um ano de histórico. O primeiro relatório se apoia nesse passado, e a precisão cresce com o tempo.

## 8. Concorrentes

| Concorrente | O que faz | Onde fica aquém neste caso |
|---|---|---|
| Masthead | Tabelas sem uso por consumo | Focada em BigQuery; admite falsos positivos de ferramentas que não enxerga |
| Revefi | Tabelas paradas e sem uso, custo | Recurso de tabelas sem uso mostrado para Snowflake/BigQuery, não Databricks |
| Keebo, Espresso AI, Unravel, Select, Chaos Genius (Flexera) | Otimização de computação | Outro problema |
| LakeOps | Arquivos órfãos e snapshots em Iceberg | Lixo técnico, não baseado em uso; foco em Iceberg |
| Azure Storage Discovery | Insights de capacidade | Capacidade, não uso por pipeline. **Principal ameaça nativa** |
| Otimização preditiva da Databricks | Manutenção de tabelas gerenciadas | Só tabelas gerenciadas, sem veredito de uso |

## 9. Riscos

- A Microsoft pode estender o Azure Storage Discovery nessa direção. Defesa: a prova cruzada entre serviços, que um produto só de storage não faz.
- O valor completo depende de o cliente ter Databricks com Unity Catalog.
- A cobertura do lineage é parcial: o comportamento de federation e de JDBC precisa ser confirmado num workspace real antes de qualquer promessa.
- Estatísticas do lado do banco exigem credencial SQL, um obstáculo de confiança em bancos.
- As informações de concorrentes vêm em boa parte de material dos próprios fornecedores e de fontes secundárias.

## 10. Fases

1. **ADLS + Unity Catalog.** O caso de storage, com valor imediato pelo histórico das tabelas de sistema.
2. **Lakeflow Connect.** O caso de computação desperdiçada, o argumento de dinheiro mais forte.
3. **Federation + estatísticas do lado do banco.** Risco e recomendações de ingerir ou federar.
4. **Leitura de PII.** Cruzamento da detecção de sensibilidade com o uso.
5. **Ciclo contínuo** (alertas, donos, registro de economia), construído desde a fase 1 para a leitura de custo e estendido às outras conforme chegam.

O JDBC continua como ponto cego declarado em todas as fases.

## 11. Antes de construir: duas validações baratas

1. **Teste real no workspace Databricks** para confirmar como consultas federadas (PostgreSQL, SQL Server) e leituras por JDBC direto aparecem em `system.access.table_lineage` e `system.query.history`.
2. **Três ou quatro conversas com líderes de dados de bancos** (acesso natural pelo São Paulo Databricks User Group) com uma pergunta: *qual das três dores (custo, risco ou PII) você pagaria para resolver?* A resposta decide qual leitura lidera o discurso.

## 12. Depois, não agora

O outro lado do mesmo mapa, tabelas muito usadas sem dono, descrição ou certificação, é a ponte natural para o Cosmos Semantic. Fica fora do discurso deste produto e vira caminho de expansão quando o núcleo estiver provado.

## Referências

- [Azure Databricks: lineage system tables](https://learn.microsoft.com/en-us/azure/databricks/admin/system-tables/lineage)
- [Azure Databricks: foreign catalogs](https://learn.microsoft.com/en-us/azure/databricks/query-federation/foreign-catalogs)
- [Azure Databricks: data lineage](https://learn.microsoft.com/en-in/azure/databricks/data-governance/unity-catalog/data-lineage)
- [Lakeflow Connect SQL Server](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/sql-server-pipeline)
- [Lakeflow Connect PostgreSQL](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/postgresql-pipeline)
- [Databricks predictive optimization](https://docs.databricks.com/en/optimizations/predictive-optimization.html)
- [ADLS Gen2 access-time lifecycle GA](https://mc.merill.net/message/AZ-access-time-based-lifecycle-management-adls-gen2)
- [Azure Blob inventory](https://learn.microsoft.com/en-us/azure/storage/blobs/blob-inventory)
- [Azure access tiers](https://learn.microsoft.com/en-us/azure/storage/blobs/access-tiers-overview)
- [Azure Storage Discovery capacity insights](https://techcommunity.microsoft.com/blog/azurestorageblog/azure-storage-discovery-now-offers-advanced-capacity-insights/4563651)
- [Fabric community: OneLake unused storage](https://community.fabric.microsoft.com/t5/Fabric-platform/metric-details-for-onelake-storage/m-p/4902057)
- [DataHub Databricks source docs](https://docs.datahub.com/docs/generated/ingestion/sources/databricks)
- [Atlan: track lineage for Databricks jobs](https://atlan.com/know/databricks/how-to-track-lineage-databricks-jobs/)
- [Masthead storage costs](https://docs.mastheadata.com/cost-insights/storage-costs)
- [Masthead insights](https://docs.mastheadata.com/developer/api/insights)
- [Revefi solutions](https://www.revefi.com/solutions)
- [FinOps X 2026 sponsors analysis](https://finopsweekly.com/blog/what-57-finops-x-sponsors-reveal-about-the-finops-market-in-2026/)
- [Flexera (Chaos Genius acquisition)](https://en.wikipedia.org/wiki/Flexera)
- [LakeOps Iceberg FinOps 2026](https://lakeops.dev/blog/state-of-iceberg-finops-cost-reduction)
