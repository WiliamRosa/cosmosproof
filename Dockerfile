# CosmosProof scanner image, for scheduled runs (Azure Container Apps Job, ADR 0007).
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
RUN pip install --no-cache-dir ".[databricks,azure]" && useradd --create-home scanner
USER scanner
ENTRYPOINT ["cosmosproof"]
CMD ["scan"]
