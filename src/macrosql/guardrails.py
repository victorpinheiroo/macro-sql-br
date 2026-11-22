"""AST-based SQL guardrails. Every rule has its own test proving it blocks on its own."""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

ALLOWED_TABLES = frozenset({"obs", "series", "calendar"})
MAX_LIMIT = 10_000

_FORBIDDEN_FUNCS = {
    # DuckDB table functions that read files or reach the network.
    "read_csv",
    "read_csv_auto",
    "read_parquet",
    "read_json",
    "read_json_auto",
    "read_text",
    "read_blob",
    "glob",
    "sniff_csv",
    "parquet_scan",
    "query_table",
}

# Functions that expose the host or engine rather than the data: environment variables (may hold
# credentials), engine settings. Found by red-teaming: getenv() passed every other rule.
_INTROSPECTION_FUNCS = {"getenv", "current_setting"}
_INTROSPECTION_PREFIXES = ("duckdb_", "pragma_")


class GuardrailError(ValueError):
    def __init__(self, rule: str, detail: str):
        super().__init__(f"[{rule}] {detail}")
        self.rule = rule


@dataclass(frozen=True)
class CheckedSQL:
    sql: str
    tables: frozenset[str]


def check(sql: str, dialect: str = "duckdb") -> CheckedSQL:
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except sqlglot.errors.ParseError as e:
        raise GuardrailError("parse", str(e)) from e

    if len(statements) != 1:
        raise GuardrailError("single_statement", f"expected 1 statement, got {len(statements)}")
    tree = statements[0]

    if not isinstance(tree, exp.Query):
        raise GuardrailError("select_only", f"statement type {type(tree).__name__} not allowed")

    for node in tree.walk():
        if isinstance(
            node,
            (
                exp.Insert,
                exp.Update,
                exp.Delete,
                exp.Create,
                exp.Drop,
                exp.Alter,
                exp.Copy,
                exp.Attach,
                exp.Command,
                exp.Pragma,
            ),
        ):
            raise GuardrailError("select_only", f"{type(node).__name__} found inside query")

    for func in tree.find_all(exp.Func):
        name = (func.sql_name() if not isinstance(func, exp.Anonymous) else func.name).lower()
        if name in _FORBIDDEN_FUNCS:
            raise GuardrailError("no_file_access", f"function {name}() not allowed")
        if name in _INTROSPECTION_FUNCS or name.startswith(_INTROSPECTION_PREFIXES):
            raise GuardrailError("no_introspection", f"function {name}() not allowed")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    tables = set()
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise GuardrailError("no_file_access", f"non-identifier table source: {table.sql()}")
        name = table.name.lower()
        # DuckDB reads FROM 'path/file.csv' as a file scan; sqlglot sees a quoted identifier.
        if any(ch in name for ch in "/\\.:") or name.endswith(("csv", "parquet", "json")):
            raise GuardrailError("no_file_access", f"path-like table source: {table.sql()}")
        if name in cte_names:
            continue
        if table.args.get("db") or table.args.get("catalog"):
            raise GuardrailError("table_allowlist", f"qualified table {table.sql()} not allowed")
        if name not in ALLOWED_TABLES:
            raise GuardrailError("table_allowlist", f"table '{name}' not in allowlist")
        tables.add(name)

    limit = tree.args.get("limit")
    if limit is None:
        tree = tree.limit(MAX_LIMIT)
    else:
        value = limit.expression
        if not isinstance(value, exp.Literal) or int(value.this) > MAX_LIMIT:
            tree = tree.limit(MAX_LIMIT)

    return CheckedSQL(sql=tree.sql(dialect=dialect), tables=frozenset(tables))
