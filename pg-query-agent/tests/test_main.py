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
    @patch("builtins.input", side_effect=["nonexistent_table"])
    def test_schema_not_found_exits(
        self, mock_input, mock_schema_cls, mock_crew_cls, monkeypatch
    ):
        _set_env(monkeypatch)
        mock_tool = MagicMock()
        mock_schema_cls.return_value = mock_tool
        mock_tool._run.return_value = "Table 'nonexistent_table' not found or has no columns."
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

        assert exc_info.value.code == 1
