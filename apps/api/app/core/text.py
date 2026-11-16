from __future__ import annotations

import re

from sqlalchemy import text as sqlalchemy_text

from app.core.config import settings

SCHEMA_MAP = {
    "sys": "zhaolu_sys",
    "dim": "zhaolu_dim",
    "fact": "zhaolu_fact",
    "gov": "zhaolu_gov",
    "ai": "zhaolu_ai",
    "analytics": "zhaolu_analytics",
}


def _translate_on_conflict(statement: str) -> str:
    if not re.search(r"\bON\s+CONFLICT\b", statement, flags=re.IGNORECASE):
        return statement

    if re.search(
        r"\bON\s+CONFLICT(?:\s*\([^)]*\))?\s+DO\s+NOTHING\b",
        statement,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        statement = re.sub(
            r"\s+ON\s+CONFLICT(?:\s*\([^)]*\))?\s+DO\s+NOTHING\b",
            "",
            statement,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return re.sub(
            r"^\s*INSERT\s+INTO\b",
            "INSERT IGNORE INTO",
            statement,
            count=1,
            flags=re.IGNORECASE,
        )

    statement = re.sub(
        r"\s+ON\s+CONFLICT(?:\s*\([^)]*\))?\s+DO\s+UPDATE\s+SET\b",
        "\nON DUPLICATE KEY UPDATE",
        statement,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    statement = re.sub(
        r"\bEXCLUDED\.([A-Za-z_][A-Za-z0-9_]*)",
        r"VALUES(\1)",
        statement,
        flags=re.IGNORECASE,
    )
    statement = re.sub(
        r"\b(?:zhaolu_)?(?:sys|dim|fact|gov|ai)\.[A-Za-z_][A-Za-z0-9_]*\.([A-Za-z_][A-Za-z0-9_]*)",
        r"\1",
        statement,
        flags=re.IGNORECASE,
    )
    return statement


def _translate_mysql_sql(text_value: str) -> str:
    rewritten = text_value

    rewritten = re.sub(
        r"([A-Za-z_][A-Za-z0-9_.]*)\s*->>\s*'([^']+)'",
        r"JSON_UNQUOTE(JSON_EXTRACT(\1, '$.\2'))",
        rewritten,
    )
    rewritten = re.sub(
        r"([A-Za-z_][A-Za-z0-9_.]*)\s*->\s*'([^']+)'",
        r"JSON_EXTRACT(\1, '$.\2')",
        rewritten,
    )
    rewritten = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)::(?:text|varchar|char)\b",
        r"CAST(\1 AS CHAR)",
        rewritten,
        flags=re.IGNORECASE,
    )
    rewritten = re.sub(r"\bnow\(\)", "CURRENT_TIMESTAMP", rewritten, flags=re.IGNORECASE)
    rewritten = re.sub(r"\bILIKE\b", "LIKE", rewritten, flags=re.IGNORECASE)
    rewritten = rewritten.replace("!~", "NOT REGEXP")
    rewritten = rewritten.replace(", '[[:space:]]+', '', 'g')", ", '[[:space:]]+', '')")
    rewritten = re.sub(
        r"CAST\((\s*:[A-Za-z0-9_]+\s*) AS\s+(?:integer|text|jsonb|bigint|numeric|date)\s*\)",
        r"\1",
        rewritten,
        flags=re.IGNORECASE,
    )
    rewritten = rewritten.replace("'[]'::jsonb", "'[]'")
    rewritten = rewritten.replace("'{}'::jsonb", "'{}'")
    rewritten = _translate_on_conflict(rewritten)

    rewritten = re.sub(
        r"BOOL_OR\(([^)]+)\)",
        r"MAX(CASE WHEN \1 THEN 1 ELSE 0 END)",
        rewritten,
        flags=re.IGNORECASE,
    )
    rewritten = re.sub(
        r"BOOL_AND\(([^)]+)\)",
        r"MIN(CASE WHEN \1 THEN 1 ELSE 0 END)",
        rewritten,
        flags=re.IGNORECASE,
    )
    rewritten = re.sub(
        r"COUNT\(DISTINCT\s+([^)]+)\)\s+FILTER\s*\(WHERE\s+([^)]+)\)",
        r"COUNT(DISTINCT CASE WHEN \2 THEN \1 END)",
        rewritten,
        flags=re.IGNORECASE,
    )
    rewritten = re.sub(
        r"COUNT\(\*\)\s+FILTER\s*\(WHERE\s+([^)]+)\)",
        r"SUM(CASE WHEN \1 THEN 1 ELSE 0 END)",
        rewritten,
        flags=re.IGNORECASE,
    )
    rewritten = re.sub(
        r"SUM\(([^)]+)\)\s+FILTER\s*\(WHERE\s+([^)]+)\)",
        r"SUM(CASE WHEN \2 THEN \1 END)",
        rewritten,
        flags=re.IGNORECASE,
    )

    for source, target in SCHEMA_MAP.items():
        rewritten = re.sub(
            rf"(?<![A-Za-z0-9_]){source}\.",
            f"{target}.",
            rewritten,
        )
    return rewritten


def rewrite_sql(text_value: str) -> str:
    if not settings.database_url.startswith("mysql"):
        return text_value
    return _translate_mysql_sql(text_value)


def text(text_value: str):
    return sqlalchemy_text(rewrite_sql(text_value))
