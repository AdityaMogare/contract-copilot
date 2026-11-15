"""Validator (design 07 layer 2). Every attack from the design's sqlglot probe, plus safe forms that must pass."""

import pytest

from app.sql.validate import MAX_ROWS, validate

SAFE = [
    "SELECT far_authority, count(*) FROM awards GROUP BY 1 ORDER BY 2 DESC",
    "WITH t AS (SELECT award_key, sum(federal_action_obligation) s FROM transactions GROUP BY 1) "
    "SELECT a.recipient_name, t.s FROM awards a JOIN t USING (award_key) ORDER BY t.s DESC LIMIT 5",
    "SELECT recipient_name FROM awards WHERE recipient_name ILIKE '%BOEING%' LIMIT 10",
    "SELECT recipient_name, sum(total_obligated), rank() OVER (ORDER BY sum(total_obligated) DESC) FROM awards GROUP BY 1",
    "SELECT piid FROM awards WHERE far_authority = '6.302-1' UNION SELECT award_key FROM transactions",
    "SELECT round(100.0 * avg(CASE WHEN number_of_offers_received = 1 THEN 1 ELSE 0 END), 1) FROM awards",
    "SELECT date_trunc('month', action_date) m, sum(federal_action_obligation) FROM transactions GROUP BY 1",
    "SELECT extract(month FROM action_date), count(*) FROM public.transactions GROUP BY 1",
    "SELECT coalesce(type_of_set_aside, 'NONE'), count(*) FILTER (WHERE total_obligated > 0) FROM awards GROUP BY 1",
    "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY total_obligated) FROM awards",
]

ATTACKS = {
    "two statements": ("SELECT 1; DROP TABLE awards", "exactly one statement"),
    "dml in cte": ("WITH d AS (DELETE FROM awards RETURNING *) SELECT * FROM d", "forbidden operation: Delete"),
    "insert in cte": ("WITH i AS (INSERT INTO awards (fiscal_year, award_key) VALUES (1,'x') RETURNING *) SELECT 1", "forbidden operation"),
    "update": ("UPDATE awards SET piid = 'x'", "only SELECT"),
    "drop": ("DROP TABLE awards", "only SELECT"),
    "pg_sleep": ("SELECT pg_sleep(10)", "function not allowed: pg_sleep"),
    "set_config": ("SELECT set_config('default_transaction_read_only', 'off', false)", "function not allowed"),
    "pg_read_file": ("SELECT pg_read_file('/etc/passwd')", "function not allowed"),
    "dblink": ("SELECT * FROM dblink('host=evil', 'select 1') AS t(x int)", "not allowed"),
    "system catalog": ("SELECT * FROM pg_catalog.pg_authid", "table not allowed"),
    "information_schema": ("SELECT * FROM information_schema.tables", "table not allowed"),
    "private table": ("SELECT * FROM load_runs", "table not allowed: load_runs"),
    "select into": ("SELECT * INTO newt FROM awards", "forbidden operation: Into"),
    "for update": ("SELECT * FROM awards FOR UPDATE", "row locking"),
    "copy": ("COPY awards TO PROGRAM 'id'", "only SELECT"),
    "union other table": ("SELECT piid FROM awards UNION SELECT usename FROM pg_user", "table not allowed: pg_user"),
    "subquery other table": ("SELECT * FROM awards WHERE award_key IN (SELECT rolname FROM pg_roles)", "table not allowed"),
    "generate_series bomb": ("SELECT count(*) FROM generate_series(1, 1000000000)", "not allowed"),
    "set role": ("SET ROLE postgres", "only SELECT"),
    "non-literal limit": ("SELECT * FROM awards LIMIT (SELECT 1000000)", "LIMIT must be an integer literal"),
    "garbage": ("this is not sql at all ((", ""),
    "empty": ("   ", "empty SQL"),
}


@pytest.mark.parametrize("sql", SAFE)
def test_safe_queries_pass(sql):
    v = validate(sql)
    assert v.ok, v.reason


@pytest.mark.parametrize("name", list(ATTACKS))
def test_attacks_rejected(name):
    sql, reason = ATTACKS[name]
    v = validate(sql)
    assert not v.ok, f"{name} passed: {v.sql}"
    assert reason in v.reason, v.reason


def test_comment_smuggling_is_harmless():
    v = validate("SELECT count(*) FROM awards -- ; DROP TABLE awards")
    assert v.ok and "DROP" not in v.sql.upper()


def test_limit_added_when_missing_and_capped_when_too_big():
    v = validate("SELECT piid FROM awards")
    assert v.capped and v.sql.endswith(f"LIMIT {MAX_ROWS}") and v.exec_sql.endswith(f"LIMIT {MAX_ROWS + 1}")
    v = validate("SELECT piid FROM awards LIMIT 5000")
    assert v.capped and v.sql.endswith(f"LIMIT {MAX_ROWS}")


def test_question_top_n_limit_is_kept():
    v = validate("SELECT recipient_name FROM awards ORDER BY total_obligated DESC LIMIT 5")
    assert v.ok and not v.capped and v.sql.endswith("LIMIT 5") and v.exec_sql == v.sql
