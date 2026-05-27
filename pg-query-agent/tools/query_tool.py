"""PostgreSQL read-only query tool with 3-layer guardrail validation."""

from __future__ import annotations

import re
from dataclasses import dataclass

import sqlparse


FORBIDDEN_KEYWORDS = frozenset({
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "GRANT", "REVOKE", "EXEC", "EXECUTE", "INTO",
})


@dataclass(frozen=True)
class GuardrailResult:
    ok: bool
    message: str = "OK"


class GuardrailValidator:
    """3-layer SQL guardrail: sqlparse type check, keyword scan, db read-only."""

    def validate(self, sql: str) -> GuardrailResult:
        if not sql or not sql.strip():
            return GuardrailResult(ok=False, message="Layer 1: empty SQL")

        # Layer 1: sqlparse statement type check
        parsed = sqlparse.parse(sql.strip())
        if not parsed or parsed[0].get_type() != "SELECT":
            stmt_type = parsed[0].get_type() if parsed else "UNKNOWN"
            return GuardrailResult(
                ok=False,
                message=f"Layer 1: statement type is '{stmt_type}', expected SELECT",
            )

        # Layer 2: forbidden keyword word-boundary scan
        upper_sql = sql.upper()
        for keyword in FORBIDDEN_KEYWORDS:
            if re.search(rf"\b{keyword}\b", upper_sql):
                return GuardrailResult(
                    ok=False,
                    message=f"Layer 2: forbidden keyword '{keyword}' detected",
                )

        return GuardrailResult(ok=True)


import psycopg2
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type


class QueryToolInput(BaseModel):
    sql: str = Field(description="The SQL SELECT query to execute")


class PostgresReadOnlyQueryTool(BaseTool):
    name: str = "PostgreSQL Read-Only Query Tool"
    description: str = (
        "Executes a validated SQL SELECT query against PostgreSQL in a read-only "
        "transaction. Returns formatted results. Blocks any non-SELECT SQL."
    )
    args_schema: Type[BaseModel] = QueryToolInput
    connection_string: str

    def _run(self, sql: str) -> str:
        check = GuardrailValidator().validate(sql)
        if not check.ok:
            return f"Query blocked — {check.message}"

        try:
            conn = psycopg2.connect(self.connection_string)
            try:
                with conn.cursor() as cur:
                    cur.execute("BEGIN TRANSACTION READ ONLY")
                    try:
                        cur.execute(sql)
                        rows = cur.fetchall()
                        columns = (
                            [desc.name for desc in cur.description]
                            if cur.description
                            else []
                        )
                        return self._format_results(columns, rows)
                    finally:
                        try:
                            cur.execute("ROLLBACK")
                        except Exception:
                            pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass  # Best-effort close; ROLLBACK already executed
        except psycopg2.Error as exc:
            return f"Database error: {exc}"

    def _format_results(self, columns: list[str], rows: list[tuple]) -> str:
        if not rows:
            return "No results found."
        header = " | ".join(columns)
        separator = "-" * len(header)
        row_lines = [" | ".join(str(v) for v in row) for row in rows]
        count_line = f"\n{len(rows)} row(s) returned."
        return "\n".join([header, separator, *row_lines]) + count_line
