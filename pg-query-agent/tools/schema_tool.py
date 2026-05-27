"""PostgreSQL schema inspector tool for CrewAI agents."""

from __future__ import annotations

from typing import Type

import psycopg2
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class SchemaInspectorInput(BaseModel):
    table_name: str = Field(description="The PostgreSQL table name to inspect")


class PostgresSchemaInspectorTool(BaseTool):
    name: str = "PostgreSQL Schema Inspector"
    description: str = (
        "Fetches the full schema for a PostgreSQL table: columns, types, nullability, "
        "indexes, and constraints. Use before building queries to know exact column names."
    )
    args_schema: Type[BaseModel] = SchemaInspectorInput
    connection_string: str

    def _run(self, table_name: str) -> str:
        try:
            conn = psycopg2.connect(self.connection_string)
            try:
                with conn.cursor() as cur:
                    columns = self._fetch_columns(cur, table_name)
                    indexes = self._fetch_indexes(cur, table_name)
                    constraints = self._fetch_constraints(cur, table_name)
                return self._format_schema(table_name, columns, indexes, constraints)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except psycopg2.Error as exc:
            return f"❌ Database error: {exc}"

    def _fetch_columns(self, cur, table_name: str) -> list[tuple]:
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
            """,
            (table_name,),
        )
        return cur.fetchall()

    def _fetch_indexes(self, cur, table_name: str) -> list[tuple]:
        cur.execute(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = %s
            """,
            (table_name,),
        )
        return cur.fetchall()

    def _fetch_constraints(self, cur, table_name: str) -> list[tuple]:
        cur.execute(
            """
            SELECT constraint_name, constraint_type
            FROM information_schema.table_constraints
            WHERE table_name = %s
            """,
            (table_name,),
        )
        return cur.fetchall()

    def _format_schema(
        self,
        table_name: str,
        columns: list[tuple],
        indexes: list[tuple],
        constraints: list[tuple],
    ) -> str:
        if not columns:
            return f"Table '{table_name}' not found or has no columns."

        lines = [f"Table: {table_name}", "Columns:"]
        for col_name, data_type, is_nullable, col_default in columns:
            nullable = "NOT NULL" if is_nullable == "NO" else "YES"
            lines.append(f"  - {col_name:<22} {data_type:<35} {nullable}")

        if indexes:
            lines.append("\nIndexes:")
            for idx_name, idx_def in indexes:
                lines.append(f"  - {idx_name}")

        if constraints:
            lines.append("\nConstraints:")
            for con_name, con_type in constraints:
                lines.append(f"  - {con_name}: {con_type}")

        return "\n".join(lines)
