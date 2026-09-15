# langflowai/langflow:latest already ships psycopg3 and langchain-community (needed for
# LANGFLOW_DATABASE_URL, its own app-metadata Postgres backend), but not the `pgvector` python
# package that its Knowledge Bases "Postgres" DB provider (PostgresBackend, configured via
# PGVECTOR_CONNECTION_STRING) imports from `pgvector.sqlalchemy`. Upstream only bundles it behind
# the opt-in `langflow[pgvector]` extra, which isn't part of any published image tag. Layer it on
# top rather than switching images, matching the version pin in langflow's own pyproject.toml
# pgvector extra (pgvector>=0.4.2).
FROM langflowai/langflow:latest

RUN pip install --no-cache-dir "pgvector>=0.4.2"
