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
