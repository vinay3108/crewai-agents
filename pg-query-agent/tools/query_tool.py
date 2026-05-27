"""PostgreSQL read-only query tool with 3-layer guardrail validation."""

from __future__ import annotations

import re
from dataclasses import dataclass

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
