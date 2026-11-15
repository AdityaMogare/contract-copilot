"""SQL validator: layer 2 of 4 (design 07 §4). Allowlist over the WHOLE parse tree.

Measured (design 07): `WITH d AS (DELETE …) SELECT`, `SELECT … INTO`, `… FOR UPDATE` and `pg_sleep(…)`
all parse with a Select at the root, so checking the root type alone is not enough.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

ALLOWED_TABLES = {"awards", "transactions"}
MAX_ROWS = 100

ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)
FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter, exp.TruncateTable,
    exp.Copy, exp.Command, exp.Transaction, exp.Commit, exp.Rollback, exp.Set, exp.Into, exp.Lock,
    exp.Grant, exp.Use, exp.Pragma, exp.Describe, exp.Analyze, exp.Kill, exp.LoadData, exp.Cache, exp.Uncache,
    exp.Refresh,
)
# Typed functions sqlglot recognises. Anything else (exp.Anonymous: pg_sleep, set_config, pg_read_file,
# dblink, lo_import, …) is rejected. Analytics only: aggregates, math, text, dates, windows, CASE.
ALLOWED_FUNCS = (
    exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max, exp.Stddev, exp.Variance, exp.Median,
    exp.PercentileCont, exp.PercentileDisc, exp.ApproxDistinct, exp.CountIf,
    exp.Round, exp.Abs, exp.Floor, exp.Ceil, exp.Sqrt, exp.Pow, exp.Ln, exp.Log, exp.Mod,
    exp.Coalesce, exp.Nullif, exp.Greatest, exp.Least, exp.Case, exp.If,
    exp.Lower, exp.Upper, exp.Trim, exp.Length, exp.Substring, exp.Concat, exp.Left, exp.Right,
    exp.Replace, exp.Initcap, exp.StrPosition, exp.RegexpLike,
    exp.Cast, exp.TryCast, exp.Extract, exp.DateTrunc, exp.TimestampTrunc, exp.CurrentDate, exp.DateDiff, exp.DateAdd, exp.ToChar,
    exp.RowNumber, exp.Rank, exp.DenseRank, exp.Ntile, exp.Lag, exp.Lead, exp.FirstValue,
    exp.ArrayAgg, exp.GroupConcat, exp.Filter,
)


@dataclass
class Validated:
    ok: bool
    reason: str | None = None
    sql: str | None = None        # what we show (LIMIT ≤ 100)
    exec_sql: str | None = None   # what we run (LIMIT 101 when our cap applies, to detect truncation)
    capped: bool = False          # True when OUR cap set the limit (vs the question asking for top-N)


def _reject(reason: str) -> Validated:
    return Validated(False, reason)


def validate(sql: str) -> Validated:
    if not sql or not sql.strip():
        return _reject("empty SQL")
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except ParseError as e:
        return _reject(f"does not parse as PostgreSQL: {str(e).splitlines()[0][:200]}")
    if len(statements) != 1:
        return _reject(f"exactly one statement allowed, got {len(statements)}")
    tree = statements[0]

    if not isinstance(tree, ROOTS):
        return _reject(f"only SELECT queries are allowed, got {type(tree).__name__}")
    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            return _reject(f"forbidden operation: {type(node).__name__}")
        if isinstance(node, exp.Select) and node.args.get("locks"):
            return _reject("row locking (FOR UPDATE/SHARE) is not allowed")
        if isinstance(node, exp.Anonymous):
            return _reject(f"function not allowed: {node.name}")
        if isinstance(node, exp.Func) and not isinstance(node, ALLOWED_FUNCS):
            return _reject(f"function not allowed: {node.sql_name().lower()}")

    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        if t.catalog or (t.db and t.db.lower() != "public"):
            return _reject(f"table not allowed: {t.sql()}")
        if name not in ALLOWED_TABLES and name not in ctes:
            return _reject(f"table not allowed: {t.name}")

    # Row cap on the outermost query. A literal LIMIT ≤ 100 is the question's own (top-N), kept as is.
    limit = tree.args.get("limit")
    if limit is not None:
        expr = limit.expression
        if not isinstance(expr, exp.Literal) or not expr.is_int:
            return _reject("LIMIT must be an integer literal")
        if int(expr.this) <= MAX_ROWS:
            out = tree.sql(dialect="postgres", comments=False)
            return Validated(True, sql=out, exec_sql=out, capped=False)
    # comments=False: what runs and what we show contain only what was validated (sqlglot keeps comments).
    shown = tree.copy().limit(MAX_ROWS).sql(dialect="postgres", comments=False)
    run = tree.copy().limit(MAX_ROWS + 1).sql(dialect="postgres", comments=False)
    return Validated(True, sql=shown, exec_sql=run, capped=True)
