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
    """Sequential two-agent crew: query_builder -> query_executor."""

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
            description=self._tasks_cfg["build_query_task"]["description"],
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

        result = crew.kickoff(inputs={
            "nl_query": nl_query,
            "schema": schema,
            "table_name": table_name,
        })
        return result.raw if hasattr(result, "raw") else str(result)
