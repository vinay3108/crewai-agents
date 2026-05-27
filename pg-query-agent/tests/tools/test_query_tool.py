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

    @patch("tools.query_tool.psycopg2.connect")
    def test_rollback_called_even_on_query_error(self, mock_connect):
        """ROLLBACK must run even when the query itself raises an error."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.execute.side_effect = [
            None,  # BEGIN succeeds
            psycopg2.ProgrammingError("column not found"),  # query fails
            None,  # ROLLBACK (best-effort, in finally)
        ]
        result = self._tool()._run(sql="SELECT nonexistent FROM orders")
        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        assert any("ROLLBACK" in c for c in calls)
        assert "error" in result.lower()

    @patch("tools.query_tool.psycopg2.connect")
    def test_connection_always_closed(self, mock_connect):
        """conn.close() must be called even when query succeeds."""
        mock_conn, mock_cursor = _setup_mock_conn(
            mock_connect,
            description=[ColInfo("id")],
            rows=[(1,)],
        )
        self._tool()._run(sql="SELECT id FROM orders")
        mock_conn.close.assert_called_once()
