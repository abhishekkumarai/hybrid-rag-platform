from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOST = "localhost"
DEFAULT_PORT = "5432"
DEFAULT_DATABASE = "postgres"
DEFAULT_USER = "postgres"


def get_connection_info() -> dict[str, str]:
    """Load the project .env and build psycopg connection keywords."""
    load_dotenv(PROJECT_ROOT / ".env")

    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        raise RuntimeError(
            f"POSTGRES_PASSWORD is not set. Add it to {PROJECT_ROOT / '.env'}"
        )

    return {
        "host": os.getenv("POSTGRES_HOST", DEFAULT_HOST),
        "port": os.getenv("POSTGRES_PORT", DEFAULT_PORT),
        "dbname": os.getenv("POSTGRES_DB", DEFAULT_DATABASE),
        "user": os.getenv("POSTGRES_USER", DEFAULT_USER),
        "password": password,
    }


def connect() -> psycopg.Connection:
    """Open a connection to the configured Postgres database."""
    return psycopg.connect(**get_connection_info())


def get_server_version() -> str:
    """Return the Postgres server version string."""
    with connect() as conn:
        return conn.execute("SELECT version()").fetchone()[0]


def has_pgvector() -> bool:
    """Report whether the server can offer the pgvector extension."""
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"
        ).fetchone()
    return row is not None
