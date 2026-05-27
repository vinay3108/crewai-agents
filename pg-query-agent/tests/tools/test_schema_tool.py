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
