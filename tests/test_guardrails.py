"""One test per rule: each attack must be stopped by the rule named in the assertion."""

import pytest

from macrosql.guardrails import MAX_LIMIT, GuardrailError, check

BLOCKED = [
    ("SELECT 1; SELECT 2", "single_statement"),
    ("SELECT * FROM obs; DROP TABLE obs", "single_statement"),
    ("DROP TABLE obs", "select_only"),
    ("DELETE FROM obs", "select_only"),
    ("INSERT INTO obs VALUES (1, DATE '2024-01-01', 1)", "select_only"),
    ("COPY obs TO 'out.csv'", "select_only"),
    ("ATTACH 'other.db'", "select_only"),
    ("INSTALL httpfs", "select_only"),
    ("SELECT * FROM read_csv('/etc/passwd')", "no_file_access"),
    ("SELECT * FROM read_parquet('s3://bucket/x.parquet')", "no_file_access"),
    ("SELECT * FROM '/etc/passwd'", "no_file_access"),
    ("SELECT * FROM users", "table_allowlist"),
    ("SELECT * FROM information_schema.tables", "table_allowlist"),
    ("SELECT * FROM other_db.main.obs", "table_allowlist"),
    ("SELECT getenv('DATABRICKS_TOKEN')", "no_introspection"),
    ("SELECT current_setting('enable_external_access')", "no_introspection"),
    ("SELECT duckdb_version_x()", "no_introspection"),
]


@pytest.mark.parametrize("sql,rule", BLOCKED)
def test_blocked(sql, rule):
    with pytest.raises(GuardrailError) as e:
        check(sql)
    assert e.value.rule == rule


def test_cte_names_are_not_mistaken_for_tables():
    check("WITH x AS (SELECT * FROM obs) SELECT * FROM x")


def test_limit_is_added_when_missing():
    assert f"LIMIT {MAX_LIMIT}" in check("SELECT * FROM obs").sql


def test_oversized_limit_is_capped():
    assert f"LIMIT {MAX_LIMIT}" in check("SELECT * FROM obs LIMIT 999999999").sql


def test_small_limit_is_kept():
    assert "LIMIT 5" in check("SELECT * FROM obs LIMIT 5").sql
