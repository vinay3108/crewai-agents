"""Tools package for pg-query-agent."""

from __future__ import annotations

import os


def build_connection_string() -> str:
    """Build psycopg2 connection string from individual env vars.

    Raises:
        EnvironmentError: If any required DATABASE_* env var is missing.
    """
    try:
        return (
            f"host={os.environ['DATABASE_HOST']} "
            f"port={os.environ['DATABASE_PORT']} "
            f"dbname={os.environ['DATABASE_NAME']} "
            f"user={os.environ['DATABASE_USER']} "
            f"password={os.environ['DATABASE_PASSWORD']}"
        )
    except KeyError as exc:
        raise EnvironmentError(
            f"Missing required environment variable: {exc}. "
            "Copy .env.example to .env and fill in all DATABASE_* values."
        ) from exc
