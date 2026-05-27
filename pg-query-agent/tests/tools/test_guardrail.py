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
