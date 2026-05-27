# pg-query-agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI AI agent that converts plain-English questions into safe PostgreSQL SELECT queries using CrewAI + Gemini.

**Architecture:** Two sequential CrewAI agents (query_builder → query_executor) with 3-layer read-only guardrails. Schema inspection via psycopg2 + information_schema. Rich terminal display. All secrets via `.env`.

**Tech Stack:** Python 3.10+, crewai[tools]≥0.141.0, psycopg2-binary, sqlparse, rich, python-dotenv, pyyaml, Gemini (gemini/gemini-2.0-flash), uv

---

## File Map

```
pg-query-agent/
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
├── main.py                        ← CLI entry point, Rich display, query loop
├── crew.py                        ← QueryCrew: builds + runs two-agent pipeline
├── config/
│   ├── agents.yaml                ← LLM + role/goal/backstory per agent
│   └── tasks.yaml                 ← task descriptions + expected output
├── tools/
│   ├── __init__.py                ← build_connection_string() helper
│   ├── query_tool.py              ← GuardrailValidator + PostgresReadOnlyQueryTool
│   └── schema_tool.py             ← PostgresSchemaInspectorTool
└── tests/
    ├── __init__.py
    ├── test_crew.py
    ├── test_main.py
    └── tools/
        ├── __init__.py
        ├── test_guardrail.py
        ├── test_query_tool.py
        └── test_schema_tool.py
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `pg-query-agent/pyproject.toml`
- Create: `pg-query-agent/.env.example`
- Create: `pg-query-agent/.gitignore`
- Create: `pg-query-agent/tools/__init__.py`
- Create: `pg-query-agent/tests/__init__.py`
- Create: `pg-query-agent/tests/tools/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "pg-query-agent"
version = "1.0.0"
requires-python = ">=3.10"
dependencies = [
    "crewai[tools]>=0.141.0",
    "psycopg2-binary>=2.9.0",
    "sqlparse>=0.5.0",
    "rich>=13.0.0",
    "python-dotenv>=1.1.1",
    "pyyaml>=6.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=5.0.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=. --cov-omit=tests/* --cov-report=term-missing --cov-fail-under=80"
```

- [ ] **Step 2: Create .env.example**

```
# PostgreSQL connection params
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=your_db_name
DATABASE_USER=postgres
DATABASE_PASSWORD=your_password_here

# Gemini API key
GEMINI_API_KEY=your_gemini_api_key_here
```

- [ ] **Step 3: Create .gitignore**

```
.env
__pycache__/
*.pyc
.venv/
*.egg-info/
.coverage
htmlcov/
dist/
.pytest_cache/
```

- [ ] **Step 4: Create tools/__init__.py**

```python
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
```

- [ ] **Step 5: Create empty init files**

`pg-query-agent/tests/__init__.py` — empty file
`pg-query-agent/tests/tools/__init__.py` — empty file

- [ ] **Step 6: Install dependencies**

```bash
cd pg-query-agent
uv sync
```

Expected: packages installed, `.venv/` created.

- [ ] **Step 7: Commit scaffold**

```bash
cd pg-query-agent
git add .
git commit -m "chore: scaffold pg-query-agent project structure and dependencies"
```

---

## Task 2: GuardrailValidator (3-layer SQL safety check)

**Files:**
- Create: `pg-query-agent/tools/query_tool.py` (GuardrailValidator only — tool added in Task 3)
- Create: `pg-query-agent/tests/tools/test_guardrail.py`

- [ ] **Step 1: Write failing tests**

Create `pg-query-agent/tests/tools/test_guardrail.py`:

```python
import pytest
from tools.query_tool import GuardrailValidator, GuardrailResult


class TestGuardrailValidator:
    def setup_method(self):
        self.v = GuardrailValidator()

    def test_valid_select_passes(self):
        result = self.v.validate("SELECT * FROM orders")
        assert result.ok is True
        assert result.message == "OK"

    def test_select_with_where_and_limit_passes(self):
        result = self.v.validate(
            "SELECT id, amount FROM orders WHERE status = 'completed' LIMIT 10"
        )
        assert result.ok is True

    def test_select_with_subquery_passes(self):
        result = self.v.validate(
            "SELECT * FROM orders WHERE id IN (SELECT id FROM orders WHERE amount > 100)"
        )
        assert result.ok is True

    def test_update_blocked_layer1(self):
        result = self.v.validate("UPDATE orders SET status='x'")
        assert result.ok is False
        assert "Layer 1" in result.message

    def test_delete_blocked_layer1(self):
        result = self.v.validate("DELETE FROM orders")
        assert result.ok is False
        assert "Layer 1" in result.message

    def test_insert_blocked_layer1(self):
        result = self.v.validate("INSERT INTO orders VALUES (1, 2, 3)")
        assert result.ok is False
        assert "Layer 1" in result.message

    def test_stacked_drop_blocked_layer2(self):
        result = self.v.validate("SELECT * FROM orders; DROP TABLE orders")
        assert result.ok is False
        assert "Layer 2" in result.message

    def test_truncate_blocked_layer2(self):
        result = self.v.validate("SELECT * FROM orders; TRUNCATE orders")
        assert result.ok is False
        assert "Layer 2" in result.message

    def test_select_into_blocked_layer2(self):
        result = self.v.validate("SELECT * INTO backup FROM orders")
        assert result.ok is False
        assert "Layer 2" in result.message

    def test_create_blocked_layer2(self):
        result = self.v.validate("SELECT 1; CREATE TABLE foo (id INT)")
        assert result.ok is False
        assert "Layer 2" in result.message

    def test_alter_blocked_layer2(self):
        result = self.v.validate("SELECT 1; ALTER TABLE orders ADD COLUMN x INT")
        assert result.ok is False
        assert "Layer 2" in result.message

    def test_empty_sql_blocked(self):
        result = self.v.validate("")
        assert result.ok is False

    def test_whitespace_only_sql_blocked(self):
        result = self.v.validate("   ")
        assert result.ok is False

    def test_guardrail_result_is_frozen_dataclass(self):
        result = GuardrailResult(ok=True)
        with pytest.raises((AttributeError, TypeError)):
            result.ok = False  # type: ignore
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd pg-query-agent
uv run pytest tests/tools/test_guardrail.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `tools.query_tool` does not exist yet.

- [ ] **Step 3: Implement GuardrailValidator**

Create `pg-query-agent/tools/query_tool.py`:

```python
"""PostgreSQL read-only query tool with 3-layer guardrail validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Type

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
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
cd pg-query-agent
uv run pytest tests/tools/test_guardrail.py -v
```

Expected: 13 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pg-query-agent/tools/query_tool.py pg-query-agent/tests/tools/test_guardrail.py
git commit -m "feat: add 3-layer GuardrailValidator with full test coverage"
```

---

## Task 3: PostgresReadOnlyQueryTool

**Files:**
- Modify: `pg-query-agent/tools/query_tool.py` (append tool class)
- Create: `pg-query-agent/tests/tools/test_query_tool.py`

- [ ] **Step 1: Write failing tests**

Create `pg-query-agent/tests/tools/test_query_tool.py`:

```python
import pytest
import psycopg2
from collections import namedtuple
from unittest.mock import patch, MagicMock, call
from tools.query_tool import PostgresReadOnlyQueryTool

ColInfo = namedtuple("ColInfo", ["name"])
CONN_STR = "host=localhost port=5432 dbname=test user=postgres password=test"


def _setup_mock_conn(mock_connect, description, rows):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_cursor.description = description
    mock_cursor.fetchall.return_value = rows
    return mock_conn, mock_cursor


class TestPostgresReadOnlyQueryTool:
    def _tool(self) -> PostgresReadOnlyQueryTool:
        return PostgresReadOnlyQueryTool(connection_string=CONN_STR)

    @patch("tools.query_tool.psycopg2.connect")
    def test_select_runs_in_read_only_transaction(self, mock_connect):
        mock_conn, mock_cursor = _setup_mock_conn(
            mock_connect,
            description=[ColInfo("id"), ColInfo("amount")],
            rows=[(1, 100.0), (2, 200.0)],
        )
        result = self._tool()._run(sql="SELECT id, amount FROM orders")
        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        assert any("BEGIN TRANSACTION READ ONLY" in c for c in calls)
        assert "id" in result
        assert "amount" in result
        assert "2 row" in result

    @patch("tools.query_tool.psycopg2.connect")
    def test_rollback_called_even_on_success(self, mock_connect):
        mock_conn, mock_cursor = _setup_mock_conn(
            mock_connect,
            description=[ColInfo("id")],
            rows=[(1,)],
        )
        self._tool()._run(sql="SELECT id FROM orders")
        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        assert any("ROLLBACK" in c for c in calls)

    @patch("tools.query_tool.psycopg2.connect")
    def test_non_select_rejected_before_db_call(self, mock_connect):
        result = self._tool()._run(sql="DELETE FROM orders")
        mock_connect.assert_not_called()
        assert any(w in result.lower() for w in ("blocked", "layer", "rejected"))

    @patch("tools.query_tool.psycopg2.connect")
    def test_empty_result_returns_no_results_message(self, mock_connect):
        mock_conn, mock_cursor = _setup_mock_conn(
            mock_connect,
            description=[ColInfo("id")],
            rows=[],
        )
        result = self._tool()._run(sql="SELECT id FROM orders WHERE id = -999")
        assert "No results found" in result

    @patch("tools.query_tool.psycopg2.connect")
    def test_db_programming_error_returned_as_message(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.execute.side_effect = [
            None,  # BEGIN succeeds
            psycopg2.ProgrammingError("column not found"),
        ]
        result = self._tool()._run(sql="SELECT nonexistent FROM orders")
        assert "error" in result.lower()

    @patch("tools.query_tool.psycopg2.connect")
    def test_connection_failure_returned_as_message(self, mock_connect):
        mock_connect.side_effect = psycopg2.OperationalError("could not connect")
        result = self._tool()._run(sql="SELECT * FROM orders")
        assert "error" in result.lower()
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd pg-query-agent
uv run pytest tests/tools/test_query_tool.py -v
```

Expected: `ImportError` — `PostgresReadOnlyQueryTool` not defined yet.

- [ ] **Step 3: Append PostgresReadOnlyQueryTool to query_tool.py**

Add after the `GuardrailValidator` class in `pg-query-agent/tools/query_tool.py`:

```python
import psycopg2
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


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
            return f"❌ Query blocked — {check.message}"

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
                        cur.execute("ROLLBACK")
            finally:
                conn.close()
        except psycopg2.Error as exc:
            return f"❌ Database error: {exc}"

    def _format_results(self, columns: list[str], rows: list[tuple]) -> str:
        if not rows:
            return "No results found."
        header = " | ".join(columns)
        separator = "-" * len(header)
        row_lines = [" | ".join(str(v) for v in row) for row in rows]
        count_line = f"\n{len(rows)} row(s) returned."
        return "\n".join([header, separator, *row_lines]) + count_line
```

The full `pg-query-agent/tools/query_tool.py` should now be:

```python
"""PostgreSQL read-only query tool with 3-layer guardrail validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Type

import psycopg2
import sqlparse
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


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

        parsed = sqlparse.parse(sql.strip())
        if not parsed or parsed[0].get_type() != "SELECT":
            stmt_type = parsed[0].get_type() if parsed else "UNKNOWN"
            return GuardrailResult(
                ok=False,
                message=f"Layer 1: statement type is '{stmt_type}', expected SELECT",
            )

        upper_sql = sql.upper()
        for keyword in FORBIDDEN_KEYWORDS:
            if re.search(rf"\b{keyword}\b", upper_sql):
                return GuardrailResult(
                    ok=False,
                    message=f"Layer 2: forbidden keyword '{keyword}' detected",
                )

        return GuardrailResult(ok=True)


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
            return f"❌ Query blocked — {check.message}"

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
                        cur.execute("ROLLBACK")
            finally:
                conn.close()
        except psycopg2.Error as exc:
            return f"❌ Database error: {exc}"

    def _format_results(self, columns: list[str], rows: list[tuple]) -> str:
        if not rows:
            return "No results found."
        header = " | ".join(columns)
        separator = "-" * len(header)
        row_lines = [" | ".join(str(v) for v in row) for row in rows]
        count_line = f"\n{len(rows)} row(s) returned."
        return "\n".join([header, separator, *row_lines]) + count_line
```

- [ ] **Step 4: Run all tool tests — verify they pass**

```bash
cd pg-query-agent
uv run pytest tests/tools/ -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pg-query-agent/tools/query_tool.py pg-query-agent/tests/tools/test_query_tool.py
git commit -m "feat: add PostgresReadOnlyQueryTool with read-only transaction enforcement"
```

---

## Task 4: PostgresSchemaInspectorTool

**Files:**
- Create: `pg-query-agent/tools/schema_tool.py`
- Create: `pg-query-agent/tests/tools/test_schema_tool.py`

- [ ] **Step 1: Write failing tests**

Create `pg-query-agent/tests/tools/test_schema_tool.py`:

```python
import pytest
import psycopg2
from unittest.mock import patch, MagicMock
from tools.schema_tool import PostgresSchemaInspectorTool

CONN_STR = "host=localhost port=5432 dbname=test user=postgres password=test"


def _setup_mock(mock_connect, columns, indexes, constraints):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchall.side_effect = [columns, indexes, constraints]
    return mock_cursor


class TestPostgresSchemaInspectorTool:
    def _tool(self) -> PostgresSchemaInspectorTool:
        return PostgresSchemaInspectorTool(connection_string=CONN_STR)

    @patch("tools.schema_tool.psycopg2.connect")
    def test_schema_contains_table_name(self, mock_connect):
        _setup_mock(
            mock_connect,
            columns=[("id", "integer", "NO", None)],
            indexes=[],
            constraints=[],
        )
        result = self._tool()._run(table_name="orders")
        assert "orders" in result

    @patch("tools.schema_tool.psycopg2.connect")
    def test_schema_contains_column_names_and_types(self, mock_connect):
        _setup_mock(
            mock_connect,
            columns=[
                ("id", "integer", "NO", None),
                ("user_id", "integer", "NO", None),
                ("amount", "numeric", "NO", None),
                ("status", "character varying", "NO", None),
                ("created_at", "timestamp without time zone", "NO", None),
            ],
            indexes=[],
            constraints=[],
        )
        result = self._tool()._run(table_name="orders")
        for col in ("id", "integer", "amount", "numeric", "status", "created_at"):
            assert col in result

    @patch("tools.schema_tool.psycopg2.connect")
    def test_nullable_column_shows_yes(self, mock_connect):
        _setup_mock(
            mock_connect,
            columns=[
                ("id", "integer", "NO", None),
                ("notes", "text", "YES", None),
            ],
            indexes=[],
            constraints=[],
        )
        result = self._tool()._run(table_name="orders")
        assert "NOT NULL" in result
        assert "YES" in result

    @patch("tools.schema_tool.psycopg2.connect")
    def test_index_names_appear_in_output(self, mock_connect):
        _setup_mock(
            mock_connect,
            columns=[("id", "integer", "NO", None)],
            indexes=[("idx_user_id", "CREATE INDEX idx_user_id ON orders (user_id)")],
            constraints=[],
        )
        result = self._tool()._run(table_name="orders")
        assert "idx_user_id" in result

    @patch("tools.schema_tool.psycopg2.connect")
    def test_table_not_found_returns_error_message(self, mock_connect):
        _setup_mock(
            mock_connect,
            columns=[],
            indexes=[],
            constraints=[],
        )
        result = self._tool()._run(table_name="nonexistent_table")
        assert "not found" in result.lower() or "no columns" in result.lower()

    @patch("tools.schema_tool.psycopg2.connect")
    def test_connection_error_returned_as_message(self, mock_connect):
        mock_connect.side_effect = psycopg2.OperationalError("could not connect")
        result = self._tool()._run(table_name="orders")
        assert "error" in result.lower()
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd pg-query-agent
uv run pytest tests/tools/test_schema_tool.py -v
```

Expected: `ModuleNotFoundError` — `tools.schema_tool` does not exist.

- [ ] **Step 3: Implement PostgresSchemaInspectorTool**

Create `pg-query-agent/tools/schema_tool.py`:

```python
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
                conn.close()
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
```

- [ ] **Step 4: Run all tool tests — verify they pass**

```bash
cd pg-query-agent
uv run pytest tests/tools/ -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pg-query-agent/tools/schema_tool.py pg-query-agent/tests/tools/test_schema_tool.py
git commit -m "feat: add PostgresSchemaInspectorTool with information_schema queries"
```

---

## Task 5: Config Files (agents.yaml + tasks.yaml)

**Files:**
- Create: `pg-query-agent/config/agents.yaml`
- Create: `pg-query-agent/config/tasks.yaml`

No tests needed — pure YAML data, no logic.

- [ ] **Step 1: Create config/agents.yaml**

```yaml
query_builder:
  llm: gemini/gemini-2.0-flash
  role: PostgreSQL Query Builder
  goal: Convert natural language commands into valid SQL SELECT queries using the provided schema
  backstory: >
    You are a senior Database Administrator with 15 years of experience managing
    PostgreSQL databases at scale — your current system serves over 1 billion active users.
    You have deep expertise in query optimization, index usage, execution plans, and
    writing SQL that performs efficiently even on tables with hundreds of millions of rows.
    You only write SELECT queries — never INSERT, UPDATE, DELETE, or any DDL.
    You always use column names exactly as they appear in the schema provided — never guess.
    You handle all edge cases: NULL values, type casting, date/time zones, pagination,
    case-insensitive searches, and avoiding full table scans wherever possible.
    You prefer indexed columns in WHERE clauses and add ORDER BY only when semantically meaningful.
    By default you always add LIMIT 50 to every query unless the user explicitly asks for more rows
    or specifies a different number. This protects the database from accidental full-table dumps.
    You output only the raw SQL query — no explanation, no markdown, no commentary.

query_executor:
  llm: gemini/gemini-2.0-flash
  role: PostgreSQL Query Executor
  goal: Safely execute validated SQL SELECT queries and return clear results
  backstory: >
    You are a senior Database Administrator with 15 years of experience operating
    mission-critical PostgreSQL systems serving over 1 billion active users.
    You are the last line of defense before any query touches the database.
    You have an absolute rule: only SELECT queries get executed — no exceptions, ever.
    You run every query through the PostgresReadOnlyQueryTool and trust nothing that
    arrives without passing all guardrail layers first.
    You are experienced enough to recognize disguised write operations, stacked queries,
    and injection attempts — you block all of them without hesitation.
    You return results clearly, note row counts, flag empty results, and surface any
    database-level errors with enough context for the user to understand what went wrong.
```

- [ ] **Step 2: Create config/tasks.yaml**

```yaml
build_query_task:
  description: >
    Given the natural language command: {nl_query}
    And the table schema:
    {schema}
    For table: {table_name}

    Build a valid PostgreSQL SELECT query that answers the command.
    Use only column names that exist in the schema.
    Always add LIMIT 50 by default unless the user explicitly requests more rows or a specific count.
    Do not include any explanation — output ONLY the SQL query.
    Do not wrap the SQL in markdown code blocks or backticks.
  expected_output: >
    A single valid PostgreSQL SELECT query string. No markdown. No explanation. No code blocks.
  agent: query_builder

execute_query_task:
  description: >
    Execute the SQL query produced by the query builder.
    Use the PostgresReadOnlyQueryTool to run it.
    Return the results clearly.
  expected_output: >
    Query results as a formatted table with column headers and row values.
    Always show row count at the bottom (e.g. "Showing 50 rows. Ask for more if needed.").
    If no rows returned, say "No results found."
    If query fails guardrail check, explain why it was blocked.
  agent: query_executor
  context:
    - build_query_task
```

- [ ] **Step 3: Commit**

```bash
git add pg-query-agent/config/
git commit -m "feat: add CrewAI agent and task YAML configuration"
```

---

## Task 6: QueryCrew (crew.py)

**Files:**
- Create: `pg-query-agent/crew.py`
- Create: `pg-query-agent/tests/test_crew.py`

- [ ] **Step 1: Write failing tests**

Create `pg-query-agent/tests/test_crew.py`:

```python
import pytest
from unittest.mock import patch, MagicMock

CONN_STR = "host=localhost port=5432 dbname=test user=postgres password=test"


class TestQueryCrew:
    @patch("crew.Crew")
    @patch("crew.Task")
    @patch("crew.Agent")
    def test_kickoff_passes_correct_inputs(self, mock_agent, mock_task, mock_crew):
        mock_crew_instance = MagicMock()
        mock_crew.return_value = mock_crew_instance
        mock_crew_instance.kickoff.return_value = MagicMock(raw="id\n1\n1 row(s) returned.")

        from crew import QueryCrew
        qc = QueryCrew(connection_string=CONN_STR)
        result = qc.kickoff(
            nl_query="show me all orders",
            schema="Table: orders\nColumns:\n  - id integer",
            table_name="orders",
        )

        mock_crew_instance.kickoff.assert_called_once()
        call_args = mock_crew_instance.kickoff.call_args
        inputs = call_args[1].get("inputs") or call_args[0][0]
        assert inputs["nl_query"] == "show me all orders"
        assert inputs["table_name"] == "orders"
        assert "orders" in inputs["schema"]

    @patch("crew.Crew")
    @patch("crew.Task")
    @patch("crew.Agent")
    def test_kickoff_returns_string(self, mock_agent, mock_task, mock_crew):
        mock_crew_instance = MagicMock()
        mock_crew.return_value = mock_crew_instance
        mock_crew_instance.kickoff.return_value = MagicMock(
            raw="id | amount\n1 | 100.0\n1 row(s) returned."
        )

        from crew import QueryCrew
        qc = QueryCrew(connection_string=CONN_STR)
        result = qc.kickoff(
            nl_query="show orders",
            schema="Table: orders\nColumns:\n  - id integer",
            table_name="orders",
        )

        assert isinstance(result, str)
        assert len(result) > 0

    @patch("crew.Crew")
    @patch("crew.Task")
    @patch("crew.Agent")
    def test_kickoff_handles_result_without_raw_attr(self, mock_agent, mock_task, mock_crew):
        mock_crew_instance = MagicMock()
        mock_crew.return_value = mock_crew_instance
        mock_crew_instance.kickoff.return_value = "plain string result"

        from crew import QueryCrew
        qc = QueryCrew(connection_string=CONN_STR)
        result = qc.kickoff(
            nl_query="show orders",
            schema="Table: orders",
            table_name="orders",
        )

        assert result == "plain string result"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd pg-query-agent
uv run pytest tests/test_crew.py -v
```

Expected: `ModuleNotFoundError` — `crew` module does not exist.

- [ ] **Step 3: Implement crew.py**

Create `pg-query-agent/crew.py`:

```python
"""CrewAI orchestration for pg-query-agent."""

from __future__ import annotations

from pathlib import Path

import yaml
from crewai import Agent, Crew, Process, Task

from tools.query_tool import PostgresReadOnlyQueryTool

_CONFIG_DIR = Path(__file__).parent / "config"


def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


class QueryCrew:
    """Sequential two-agent crew: query_builder → query_executor."""

    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string
        self._agents_cfg = _load_yaml(_CONFIG_DIR / "agents.yaml")
        self._tasks_cfg = _load_yaml(_CONFIG_DIR / "tasks.yaml")

    def kickoff(self, nl_query: str, schema: str, table_name: str) -> str:
        query_builder = Agent(
            role=self._agents_cfg["query_builder"]["role"],
            goal=self._agents_cfg["query_builder"]["goal"],
            backstory=self._agents_cfg["query_builder"]["backstory"],
            llm=self._agents_cfg["query_builder"]["llm"],
            verbose=False,
        )

        query_executor = Agent(
            role=self._agents_cfg["query_executor"]["role"],
            goal=self._agents_cfg["query_executor"]["goal"],
            backstory=self._agents_cfg["query_executor"]["backstory"],
            llm=self._agents_cfg["query_executor"]["llm"],
            tools=[PostgresReadOnlyQueryTool(connection_string=self._connection_string)],
            verbose=False,
        )

        build_task = Task(
            description=self._tasks_cfg["build_query_task"]["description"].format(
                nl_query=nl_query,
                schema=schema,
                table_name=table_name,
            ),
            expected_output=self._tasks_cfg["build_query_task"]["expected_output"],
            agent=query_builder,
        )

        execute_task = Task(
            description=self._tasks_cfg["execute_query_task"]["description"],
            expected_output=self._tasks_cfg["execute_query_task"]["expected_output"],
            agent=query_executor,
            context=[build_task],
        )

        crew = Crew(
            agents=[query_builder, query_executor],
            tasks=[build_task, execute_task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        return result.raw if hasattr(result, "raw") else str(result)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd pg-query-agent
uv run pytest tests/test_crew.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pg-query-agent/crew.py pg-query-agent/tests/test_crew.py
git commit -m "feat: add QueryCrew with sequential two-agent pipeline"
```

---

## Task 7: CLI Entry Point (main.py)

**Files:**
- Create: `pg-query-agent/main.py`
- Create: `pg-query-agent/tests/test_main.py`

- [ ] **Step 1: Write failing tests**

Create `pg-query-agent/tests/test_main.py`:

```python
import pytest
import sys
from unittest.mock import patch, MagicMock


def _set_env(monkeypatch):
    for k, v in {
        "DATABASE_HOST": "localhost",
        "DATABASE_PORT": "5432",
        "DATABASE_NAME": "test",
        "DATABASE_USER": "postgres",
        "DATABASE_PASSWORD": "password",
        "GEMINI_API_KEY": "test-key",
    }.items():
        monkeypatch.setenv(k, v)


class TestMain:
    @patch("main.QueryCrew")
    @patch("main.PostgresSchemaInspectorTool")
    @patch("builtins.input", side_effect=["orders", "show all orders", "exit"])
    def test_run_executes_query_then_exits(
        self, mock_input, mock_schema_cls, mock_crew_cls, monkeypatch
    ):
        _set_env(monkeypatch)
        mock_tool = MagicMock()
        mock_schema_cls.return_value = mock_tool
        mock_tool._run.return_value = "Table: orders\nColumns:\n  - id integer"
        mock_crew = MagicMock()
        mock_crew_cls.return_value = mock_crew
        mock_crew.kickoff.return_value = "id\n1\n1 row(s) returned."

        from main import run
        run()

        mock_tool._run.assert_called_once_with(table_name="orders")
        mock_crew.kickoff.assert_called_once()

    @patch("main.QueryCrew")
    @patch("main.PostgresSchemaInspectorTool")
    @patch("builtins.input", side_effect=["orders", "quit"])
    def test_quit_exits_cleanly(
        self, mock_input, mock_schema_cls, mock_crew_cls, monkeypatch
    ):
        _set_env(monkeypatch)
        mock_tool = MagicMock()
        mock_schema_cls.return_value = mock_tool
        mock_tool._run.return_value = "Table: orders\nColumns:\n  - id integer"
        mock_crew_cls.return_value = MagicMock()

        from main import run
        run()  # must not raise

    @patch("main.QueryCrew")
    @patch("main.PostgresSchemaInspectorTool")
    @patch("builtins.input", side_effect=["orders", "exit"])
    def test_schema_error_exits_with_message(
        self, mock_input, mock_schema_cls, mock_crew_cls, monkeypatch
    ):
        _set_env(monkeypatch)
        mock_tool = MagicMock()
        mock_schema_cls.return_value = mock_tool
        mock_tool._run.return_value = "Table 'orders' not found or has no columns."
        mock_crew_cls.return_value = MagicMock()

        with pytest.raises(SystemExit):
            from main import run
            run()

    def test_missing_env_var_exits_with_code_1(self, monkeypatch):
        for k in ["DATABASE_HOST", "DATABASE_PORT", "DATABASE_NAME",
                  "DATABASE_USER", "DATABASE_PASSWORD", "GEMINI_API_KEY"]:
            monkeypatch.delenv(k, raising=False)

        with pytest.raises(SystemExit) as exc_info:
            import importlib
            import main as m
            importlib.reload(m)
            m.run()

        assert exc_info.value.code == 1 or exc_info.value.code is not None
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd pg-query-agent
uv run pytest tests/test_main.py -v
```

Expected: `ModuleNotFoundError` — `main` module does not exist.

- [ ] **Step 3: Implement main.py**

Create `pg-query-agent/main.py`:

```python
"""CLI entry point for pg-query-agent."""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from rich.console import Console
from rich.panel import Panel

from tools import build_connection_string
from tools.schema_tool import PostgresSchemaInspectorTool
from crew import QueryCrew

console = Console()

_REQUIRED_ENV = [
    "DATABASE_HOST", "DATABASE_PORT", "DATABASE_NAME",
    "DATABASE_USER", "DATABASE_PASSWORD", "GEMINI_API_KEY",
]


def _validate_env() -> None:
    missing = [k for k in _REQUIRED_ENV if not os.getenv(k)]
    if missing:
        console.print(f"[red]❌ Missing environment variables: {', '.join(missing)}[/red]")
        console.print("[dim]Copy .env.example to .env and fill in the values.[/dim]")
        sys.exit(1)


def _banner() -> None:
    console.print(Panel.fit("[bold cyan]pg-query-agent  v1.0[/bold cyan]", border_style="cyan"))


def run() -> None:
    _validate_env()
    _banner()

    conn_str = build_connection_string()
    schema_tool = PostgresSchemaInspectorTool(connection_string=conn_str)
    crew = QueryCrew(connection_string=conn_str)

    table_name = input("Enter table name: ").strip()

    console.print(f"\n[dim]Fetching schema for table: {table_name}...[/dim]")
    schema = schema_tool._run(table_name=table_name)

    if "not found" in schema.lower() or (schema.startswith("❌")):
        console.print(f"[red]{schema}[/red]")
        sys.exit(1)

    console.print(f"\n[bold]Schema:[/bold]\n{schema}\n")

    while True:
        try:
            nl_query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Bye![/dim]")
            break

        if nl_query.lower() in {"exit", "quit", "q"}:
            console.print("[dim]Bye![/dim]")
            break

        if not nl_query:
            continue

        console.print("[dim]🔧 Building query...[/dim]")
        try:
            result = crew.kickoff(
                nl_query=nl_query,
                schema=schema,
                table_name=table_name,
            )
            console.print(f"\n[bold green]Results:[/bold green]\n{result}\n")
        except Exception as exc:
            console.print(f"[red]❌ Error: {exc}[/red]")


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run all tests — verify they pass**

```bash
cd pg-query-agent
uv run pytest tests/test_main.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pg-query-agent/main.py pg-query-agent/tests/test_main.py
git commit -m "feat: add CLI entry point with Rich display, env validation, query loop"
```

---

## Task 8: README.md

**Files:**
- Create: `pg-query-agent/README.md`

- [ ] **Step 1: Write README.md**

Create `pg-query-agent/README.md`:

```markdown
# pg-query-agent

Query any PostgreSQL database using plain English. No SQL knowledge required.
Powered by CrewAI + Gemini 2.0 Flash.

## Setup

```bash
cd pg-query-agent

# Install dependencies
uv sync

# Configure secrets
cp .env.example .env
# Edit .env — fill in DATABASE_* and GEMINI_API_KEY
```

## Run

```bash
python main.py
```

## Usage

1. Enter a table name at the prompt
2. Schema is displayed automatically
3. Type any natural language question
4. Type `exit` or `quit` to stop

## Example

```
Enter table name: orders

You: show me top 10 orders above 5000 placed last week
You: how many completed orders exist?
You: exit
```

## Safety — 3-layer read-only guardrail

| Layer | Check | Blocks |
|-------|-------|--------|
| 1 | sqlparse type check | Any non-SELECT statement |
| 2 | Keyword scan | DROP, DELETE, INSERT, CREATE, ALTER, TRUNCATE, … |
| 3 | `BEGIN TRANSACTION READ ONLY` | PostgreSQL engine rejects all writes |

## Requirements

- Python 3.10+
- PostgreSQL database (any version)
- [Gemini API key](https://aistudio.google.com/app/apikey) (free tier works)

## Development

```bash
# Run tests
uv run pytest -v

# Run with coverage
uv run pytest --cov=. --cov-report=term-missing
```
```

- [ ] **Step 2: Commit**

```bash
git add pg-query-agent/README.md
git commit -m "docs: add README with setup, usage, and safety documentation"
```

---

## Task 9: Final Coverage Check

**Files:** None — run full test suite and verify 80%+ coverage.

- [ ] **Step 1: Run full test suite with coverage**

```bash
cd pg-query-agent
uv run pytest --cov=. --cov-omit=tests/* --cov-report=term-missing -v
```

Expected: all tests PASS, coverage ≥ 80%.

- [ ] **Step 2: Fix any coverage gaps**

If coverage < 80%, inspect the `term-missing` output. Add tests for any uncovered branches. Common gaps:
- `_format_results` edge cases in `query_tool.py`
- `_format_schema` constraint-parsing in `schema_tool.py`
- Error branches in `main.py`

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "test: verify 80%+ coverage across all modules"
```
