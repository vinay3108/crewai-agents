"""Tools package for pg-query-agent."""

from __future__ import annotations

import os


def build_connection_string() -> str:
    """Build psycopg2 connection string from individual env vars."""
    return (
        f"host={os.environ['DATABASE_HOST']} "
        f"port={os.environ['DATABASE_PORT']} "
        f"dbname={os.environ['DATABASE_NAME']} "
        f"user={os.environ['DATABASE_USER']} "
        f"password={os.environ['DATABASE_PASSWORD']}"
    )
