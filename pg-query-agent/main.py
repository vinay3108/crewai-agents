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
        console.print(f"[red]Missing environment variables: {', '.join(missing)}[/red]")
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

    if "not found" in schema.lower() or schema.startswith("❌"):
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

        console.print("[dim]Building query...[/dim]")
        try:
            result = crew.kickoff(
                nl_query=nl_query,
                schema=schema,
                table_name=table_name,
            )
            console.print(f"\n[bold green]Results:[/bold green]\n{result}\n")
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")


if __name__ == "__main__":
    run()
