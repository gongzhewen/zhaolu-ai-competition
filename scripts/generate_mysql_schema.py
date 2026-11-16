from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "mysql" / "postgres_offline.sql"
TARGET = ROOT / "scripts" / "mysql" / "schema.sql"
DOCKER_TARGET = ROOT / "scripts" / "mysql" / "docker-init" / "01-schema.sql"

SCHEMA_MAP = {
    "sys": "zhaolu_sys",
    "dim": "zhaolu_dim",
    "fact": "zhaolu_fact",
    "gov": "zhaolu_gov",
    "ai": "zhaolu_ai",
    "analytics": "zhaolu_analytics",
}


def split_statements(sql: str) -> list[str]:
    return [part.strip() for part in re.split(r";\s*(?:\r?\n|$)", sql) if part.strip()]


def map_schema_names(sql: str) -> str:
    for source, target in SCHEMA_MAP.items():
        sql = re.sub(rf"(?<![A-Za-z0-9_]){source}\.", f"{target}.", sql)
    return sql


def convert_ddl(statement: str) -> str | None:
    sql = "\n".join(line for line in statement.splitlines() if not line.strip().startswith("--")).strip()
    if not sql or sql.startswith("INFO"):
        return None
    upper = sql.upper()
    if upper.startswith("CREATE EXTENSION"):
        return None
    if upper.startswith("CREATE SCHEMA"):
        name = sql.split()[-1].strip(";")
        mapped = SCHEMA_MAP.get(name, name)
        return (
            f"CREATE DATABASE IF NOT EXISTS `{mapped}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
        )
    if upper.startswith("CREATE MATERIALIZED VIEW"):
        return None
    if upper.startswith("CREATE INDEX") or upper.startswith("CREATE UNIQUE INDEX"):
        return None
    if upper.startswith("ALTER TABLE") and ("FOREIGN KEY" in upper or "REFERENCES" in upper):
        return None
    if not any(
        upper.startswith(prefix)
        for prefix in (
            "CREATE TABLE",
            "CREATE INDEX",
            "CREATE UNIQUE INDEX",
            "ALTER TABLE",
        )
    ):
        return None

    sql = map_schema_names(sql)
    sql = sql.replace("BIGSERIAL", "BIGINT AUTO_INCREMENT")
    sql = sql.replace("JSONB", "JSON")
    sql = re.sub(r"VECTOR\(\d+\)", "JSON", sql, flags=re.IGNORECASE)
    sql = sql.replace("TIMESTAMPTZ", "TIMESTAMP")
    sql = sql.replace("TIMESTAMP WITH TIME ZONE", "TIMESTAMP")
    sql = re.sub(r"\bnow\(\)", "CURRENT_TIMESTAMP", sql, flags=re.IGNORECASE)
    sql = re.sub(r"::(?:bigint|integer|text|jsonb|date|numeric)", "", sql, flags=re.IGNORECASE)
    sql = re.sub(
        r",?\s*FOREIGN KEY\s*\([^)]*\)\s*(?:REFERENCES\s+[A-Za-z0-9_.`]+\s*\([^)]*\))?\s*(?:ON DELETE CASCADE)?",
        "",
        sql,
        flags=re.IGNORECASE,
    )
    sql = re.sub(
        r"\s+REFERENCES\s+[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)?\s*\([^)]*\)",
        "",
        sql,
    )
    sql = re.sub(r"\s+INCLUDE\s*\([^)]*\)", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s+USING\s+GIN", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"(?:\s*ON\s+DELETE\s+(?:CASCADE|SET\s+NULL|RESTRICT|NO\s+ACTION))+", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"(?:\s*ON\s+UPDATE\s+(?:CASCADE|SET\s+NULL|RESTRICT|NO\s+ACTION))+", "", sql, flags=re.IGNORECASE)
    sql = sql.replace("JSON NOT NULL DEFAULT '{}'", "JSON NOT NULL")
    sql = sql.replace("JSON DEFAULT '{}'", "JSON")
    sql = sql.replace("JSON NOT NULL DEFAULT '[]'", "JSON NOT NULL")
    sql = sql.replace("JSON DEFAULT '[]'", "JSON")
    sql = re.sub(r"CREATE\s+(UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS", r"CREATE \1INDEX", sql, flags=re.IGNORECASE)
    return sql


def main() -> None:
    sql = SOURCE.read_text(encoding="utf-8")
    statements = [f"{converted};" for item in split_statements(sql) if (converted := convert_ddl(item))]
    header = [
        "-- Generated MySQL Lite schema for zhaolu-ai-v2.",
        "SET NAMES utf8mb4;",
        "SET FOREIGN_KEY_CHECKS = 0;",
        *[
            f"CREATE DATABASE IF NOT EXISTS `{target}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
            for target in SCHEMA_MAP.values()
        ],
    ]
    footer = [
        """
CREATE TABLE IF NOT EXISTS zhaolu_analytics.mv_admissions_rollup (
    year_no INT NOT NULL,
    school_id BIGINT NOT NULL,
    school_name VARCHAR(255) NOT NULL,
    province_id BIGINT NOT NULL,
    province_name VARCHAR(64) NOT NULL,
    source_major_id BIGINT NOT NULL,
    source_major_name VARCHAR(255) NOT NULL,
    canonical_major_id BIGINT NOT NULL,
    canonical_major_name VARCHAR(255) NOT NULL,
    subject_id BIGINT NOT NULL,
    subject_name VARCHAR(64),
    plan_type_id BIGINT,
    plan_type_key BIGINT NOT NULL,
    plan_type_code VARCHAR(64) NOT NULL,
    batch_id BIGINT,
    plan_count BIGINT NOT NULL DEFAULT 0,
    admitted_count BIGINT NOT NULL DEFAULT 0,
    min_score DECIMAL(6,2),
    max_score DECIMAL(6,2),
    min_rank_no INT,
    data_version VARCHAR(64),
    PRIMARY KEY (
        year_no, school_id, province_id, source_major_id, canonical_major_id,
        subject_id, plan_type_key, batch_id
    ),
    KEY idx_mv_admissions_year_school_province_major (
        year_no, school_id, province_id, canonical_major_id
    ),
    KEY idx_mv_admissions_year_school_major (
        year_no, school_id, canonical_major_id
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
""".strip(),
        "SET FOREIGN_KEY_CHECKS = 1;",
    ]
    schema_sql = "\n\n".join([*header, *statements, *footer]) + "\n"
    TARGET.write_text(schema_sql, encoding="utf-8")
    DOCKER_TARGET.parent.mkdir(parents=True, exist_ok=True)
    DOCKER_TARGET.write_text(schema_sql, encoding="utf-8")
    print(f"generated={TARGET} statements={len(statements)}")


if __name__ == "__main__":
    main()


