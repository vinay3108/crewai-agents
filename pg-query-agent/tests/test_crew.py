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
