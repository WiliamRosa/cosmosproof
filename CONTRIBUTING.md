# Contributing

Thank you for your interest. Issues, questions and ideas are welcome in GitHub Issues.

**Code contributions are not accepted yet.** CosmosProof is licensed under the Business Source License 1.1 and is sold commercially; accepting outside code first needs a Contributor License Agreement, which does not exist yet. See [ADR 0002](docs/decisions/0002-repository-license-and-cosmos-dependency.md).

If you need a change in the shared foundation (connectors, LGPD detection), contribute it to [Cosmos Semantic](https://github.com/WiliamRosa/cosmos-semantic-platform), which is Apache 2.0 and accepts contributions under the DCO.

## Development

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Live tests against a Databricks SQL warehouse are opt-in:

```bash
COSMOSPROOF_DATABRICKS_PROFILE=<profile> COSMOSPROOF_DATABRICKS_HTTP_PATH=<http path> uv run pytest -m databricks
```
