# pg-query-agent — Design Document

**Date:** 2026-05-27  
**Author:** Vinay Kumar  
**Status:** Approved  

---

## 1. Overview

A portable CLI-based AI agent that lets you query any PostgreSQL database using plain English.  
You tell it the table name → it shows you the schema → you describe what you want → it builds and runs the SQL → you get results.

No SQL knowledge required at query time. Zero risk of accidental writes.

---

## 2. Goals

- Natural language → SQL SELECT, executed against a real PostgreSQL database
- Show table schema before accepting queries (user knows what they're working with)
- Enforce strict read-only guardrails at multiple layers
- Work as a standalone portable folder — drop anywhere, set `.env`, run
- Interactive CLI loop — ask multiple queries in one session

---

## 3. Non-Goals

- No INSERT / UPDATE / DELETE / DDL — ever
- No DynamoDB, MySQL, MongoDB support (out of scope for v1)
- No web UI or REST API (CLI only for v1)
- No multi-table JOIN discovery (user specifies table explicitly)
- No authentication layer (local/private use assumed)

---

## 4. Architecture

```
┌──────────────────────────────────────────────────┐
│                    main.py (CLI)                  │
│                                                   │
│  1. Load .env → PG connection string              │
│  2. Prompt → table name(s)                        │
│  3. SchemaInspector.run() → fetch + display schema│
│  4. Loop:                                         │
│     a. Prompt → natural language query            │
│     b. QueryCrew.kickoff(nl_query, schema)        │
│     c. Display results as table                   │
└──────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────┐
│                  crew.py (QueryCrew)              │
│                                                   │
│  Agent 1: query_builder                           │
│    - Input: NL command + schema context           │
│    - Output: valid SQL SELECT string              │
│                                                   │
│  Agent 2: query_executor                          │
│    - Input: SQL string from query_builder         │
│    - Runs guardrail validator                     │
│    - Executes on PG in READ ONLY transaction      │
│    - Output: query results (rows + columns)       │
└──────────────────────────────────────────────────┘
                        │
              ┌─────────┴──────────┐
              ▼                    ▼
┌─────────────────────┐  ┌──────────────────────────┐
│   schema_tool.py    │  │      query_tool.py        │
│                     │  │                           │
│ PostgresSchemaInspector  │  PostgresReadOnlyQueryTool│
│ - information_schema│  │ - 3-layer guardrail check │
│ - column names      │  │ - BEGIN READ ONLY tx      │
│ - data types        │  │ - execute SELECT          │
│ - constraints       │  │ - ROLLBACK always         │
│ - indexes           │  └──────────────────────────┘
└─────────────────────┘
```

---

## 5. Project Structure

```
pg-query-agent/
├── .env.example              ← template for secrets
├── .gitignore
├── pyproject.toml            ← all dependencies
├── README.md                 ← setup + usage guide
├── main.py                   ← CLI entry point
│
├── config/
│   ├── agents.yaml           ← query_builder, query_executor agent definitions
│   └── tasks.yaml            ← build_query_task, execute_query_task definitions
│
├── crew.py                   ← @CrewBase QueryCrew
│
├── tools/
│   ├── __init__.py
│   ├── schema_tool.py        ← PostgresSchemaInspectorTool
│   └── query_tool.py         ← PostgresReadOnlyQueryTool + GuardrailValidator
│
└── docs/
    └── design.md             ← this file
```

---

## 6. Agents

### 6.1 `query_builder`

| Field | Value |
|---|---|
| Role | PostgreSQL Query Builder |
| Goal | Convert natural language commands into valid, safe SQL SELECT queries |
| Backstory | Expert SQL engineer who only writes SELECT queries. Always uses the provided schema to build accurate queries. Never guesses column names. |
| Tools | None (pure LLM reasoning with schema context) |
| LLM | `gemini/gemini-2.0-flash` |

**Input context passed via task:**
- `nl_query` — user's natural language command
- `schema` — table schema string (columns, types, constraints, indexes)
- `table_name` — explicit table name to query

**Output:** Raw SQL SELECT string, nothing else.

---

### 6.2 `query_executor`

| Field | Value |
|---|---|
| Role | PostgreSQL Query Executor |
| Goal | Validate and safely execute SQL SELECT queries, return formatted results |
| Backstory | A strict database operator who only runs read-only queries. Refuses any query that is not a SELECT. |
| Tools | `PostgresReadOnlyQueryTool` |
| LLM | `gemini/gemini-2.0-flash` |

**Input:** SQL SELECT from `query_builder` task output  
**Output:** Query results as formatted rows

---

## 7. Tasks

### 7.1 `build_query_task`

```
Description:
  Given the natural language command: {nl_query}
  And the table schema: {schema}
  For table: {table_name}

  Build a valid PostgreSQL SELECT query that answers the command.
  Use only column names that exist in the schema.
  Always add LIMIT 50 by default unless the user explicitly requests more rows or a specific count.
  Do not include any explanation — output ONLY the SQL query.

Expected Output:
  A single valid PostgreSQL SELECT query string. No markdown. No explanation.
```

### 7.2 `execute_query_task`

```
Description:
  Execute the SQL query produced by the query builder.
  Use the PostgresReadOnlyQueryTool to run it.
  Return the results clearly.

Expected Output:
  Query results as a formatted table with column headers and row values.
  Always show row count at the bottom (e.g. "Showing 50 rows. Ask for more if needed.").
  If no rows returned, say "No results found."
  If query fails guardrail check, explain why it was blocked.
```

---

## 8. Tools

### 8.1 `PostgresSchemaInspectorTool`

**File:** `tools/schema_tool.py`  
**Purpose:** Fetch and format full table schema from PostgreSQL.

**Queries run:**
```sql
-- Column info
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = '{table_name}'
ORDER BY ordinal_position;

-- Index info
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = '{table_name}';

-- Constraints
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_name = '{table_name}';
```

**Output format:**
```
Table: orders
Columns:
  - id           : integer        NOT NULL  (PK)
  - user_id      : integer        NOT NULL
  - amount       : numeric(10,2)  NOT NULL
  - status       : varchar(50)    NOT NULL
  - created_at   : timestamp      NOT NULL

Indexes:
  - orders_pkey on (id)
  - idx_orders_user_id on (user_id)
```

---

### 8.2 `PostgresReadOnlyQueryTool`

**File:** `tools/query_tool.py`  
**Purpose:** Validate SQL safety + execute in read-only transaction.

**Guardrail — 3 layers:**

```
Layer 1: sqlparse type check
  parsed = sqlparse.parse(sql)[0]
  parsed.get_type() must equal 'SELECT'
  → blocks any non-SELECT statement type

Layer 2: forbidden keyword scan
  Scans uppercased SQL for:
  INSERT, UPDATE, DELETE, DROP, CREATE, ALTER,
  TRUNCATE, GRANT, REVOKE, EXEC, EXECUTE,
  INTO, SET (as standalone keyword)
  → blocks even if embedded in a subquery

Layer 3: database-level read-only transaction
  BEGIN TRANSACTION READ ONLY;
  [execute query]
  ROLLBACK;   ← always rollback, even on success
  → PostgreSQL engine itself rejects any write attempt
```

**Connection:**
- Uses `psycopg2` with connection string from `PG_CONNECTION_STRING` env var
- Connection opened per tool call, closed after (simple and portable)
- Future: connection pooling via `psycopg2.pool`

---

## 9. Guardrail Decision Table

| SQL Attempted | Layer 1 | Layer 2 | Layer 3 | Result |
|---|---|---|---|---|
| `SELECT * FROM orders` | ✅ | ✅ | ✅ | Executed |
| `SELECT * FROM orders; DROP TABLE orders` | ✅ | ❌ DROP blocked | — | Rejected |
| `UPDATE orders SET status='x'` | ❌ not SELECT | — | — | Rejected |
| `DELETE FROM orders` | ❌ not SELECT | — | — | Rejected |
| `INSERT INTO orders VALUES (...)` | ❌ not SELECT | — | — | Rejected |
| SELECT with subquery `(SELECT ... INTO ...)` | ✅ | ❌ INTO blocked | — | Rejected |

---

## 10. Configuration

### `.env.example`

```
# PostgreSQL connection params
DATABASE_HOST=10.40.134.71
DATABASE_PORT=5432
DATABASE_NAME=your_db_name
DATABASE_USER=postgres
DATABASE_PASSWORD=your_password_here

# Gemini API key
GEMINI_API_KEY=your_gemini_api_key_here
```

Connection string built at runtime:
```python
conn_str = (
    f"host={os.getenv('DATABASE_HOST')} "
    f"port={os.getenv('DATABASE_PORT')} "
    f"dbname={os.getenv('DATABASE_NAME')} "
    f"user={os.getenv('DATABASE_USER')} "
    f"password={os.getenv('DATABASE_PASSWORD')}"
)
```

### `config/agents.yaml`

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

---

## 11. CLI User Experience

```bash
$ python main.py

╔══════════════════════════════════╗
║     pg-query-agent  v1.0        ║
╚══════════════════════════════════╝

Enter table name: orders

Fetching schema for table: orders...

┌─────────────┬──────────────┬──────────┐
│ Column      │ Type         │ Nullable │
├─────────────┼──────────────┼──────────┤
│ id          │ integer      │ NO       │
│ user_id     │ integer      │ NO       │
│ amount      │ numeric      │ NO       │
│ status      │ varchar(50)  │ NO       │
│ created_at  │ timestamp    │ NO       │
└─────────────┴──────────────┴──────────┘

You: show me top 10 orders above 5000 placed last week

🔧 Building query...
📋 SQL: SELECT * FROM orders WHERE amount > 5000
        AND created_at >= NOW() - INTERVAL '7 days'
        ORDER BY amount DESC LIMIT 10;

✅ Guardrail passed
⚡ Executing...

┌────┬─────────┬──────────┬────────────┬─────────────────────┐
│ id │ user_id │ amount   │ status     │ created_at          │
├────┼─────────┼──────────┼────────────┼─────────────────────┤
│ 42 │ 101     │ 9500.00  │ completed  │ 2026-05-22 14:32:10 │
│ 38 │ 205     │ 7200.00  │ completed  │ 2026-05-21 09:15:44 │
└────┴─────────┴──────────┴────────────┴─────────────────────┘
2 rows returned.

You: exit
Bye!
```

---

## 12. Error Handling

| Scenario | Behavior |
|---|---|
| PG connection fails | Clear error message + exit. Check `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`. |
| Table not found | Schema tool returns "Table not found". Prompt user to re-enter. |
| Guardrail blocks query | Show which layer blocked it and why. Re-prompt. |
| Query returns 0 rows | Show "No results found." — not an error. |
| LLM builds invalid SQL | psycopg2 raises `ProgrammingError`. Show error, re-prompt. |
| LLM hallucinates column | PG returns column-not-found error. Show error, re-prompt. |
| GEMINI_API_KEY missing | Fail fast at startup with clear message. |

---

## 13. Dependencies

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
]
```

---

## 14. Deployment

Since this is a self-contained folder:

```bash
# Clone / copy folder anywhere
cd pg-query-agent

# Install dependencies
uv sync        # if using uv
# OR
pip install -e .

# Configure
cp .env.example .env
# Fill in PG_CONNECTION_STRING and GEMINI_API_KEY

# Run
python main.py
```

No Docker required. No server. Works on any machine with Python 3.10+.

---

## 15. Future Extensions (v2)

| Feature | Description |
|---|---|
| Multi-table support | Inspect and query across joined tables |
| Query history | Save past queries + results to local SQLite |
| Export results | Save results as CSV / JSON |
| DynamoDB support | Add DynamoDB schema + query tools |
| REST API mode | Wrap in FastAPI for service deployment |
| Connection pooling | `psycopg2.pool` for better performance |
