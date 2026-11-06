"""End-to-end tests against a real MySQL server. Skipped unless RUN_DB_TESTS=1."""
import os

import pandas as pd
import pytest

from tests.test_validate import record
from warehouse import quality
from warehouse.config import load_config
from warehouse.db import connect
from warehouse.pipeline import QualityGateError, run_pipeline
from warehouse.reports import run_reports

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="set RUN_DB_TESTS=1 with a MySQL server available"
)
TEST_DB = "complaints_dw_test"


def rows():
    return pd.DataFrame(
        [
            record(complaint_id="1"),
            record(complaint_id="2", date_received="2020-02-01", date_sent="2020-01-31",
                   state=None, channel=None, zip_code="7030", tags="Older American"),
            record(complaint_id="3", company="Other Bank", timely_response="No",
                   narrative="Charged twice", consumer_disputed=None),
            record(complaint_id="bad"),
            record(complaint_id="1", company="Duplicate"),
        ]
    )


@pytest.fixture
def conn():
    cfg = load_config(TEST_DB)
    connection = connect(cfg)
    with connection.cursor() as cur:
        cur.execute(f"DROP DATABASE `{TEST_DB}`")
        cur.execute(f"CREATE DATABASE `{TEST_DB}`")
        cur.execute(f"USE `{TEST_DB}`")
    yield connection
    connection.close()


def scalar(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()[0]


def test_load_builds_star_schema_and_quarantines_bad_rows(conn):
    stats = run_pipeline(rows(), conn)
    assert (stats["read"], stats["loaded"], stats["rejected"]) == (5, 3, 2)
    assert scalar(conn, "SELECT COUNT(*) FROM fact_complaint") == 3
    assert scalar(conn, "SELECT COUNT(*) FROM dq_quarantine") == 2
    assert scalar(conn, "SELECT COUNT(*) FROM complaint_narrative") == 1
    assert scalar(conn, "SELECT zip_code FROM fact_complaint WHERE complaint_id=2") == "07030"
    assert scalar(conn, "SELECT is_date_anomaly FROM fact_complaint WHERE complaint_id=2") == 1
    assert scalar(conn, "SELECT status FROM etl_run ORDER BY run_id DESC LIMIT 1") == "success"


def test_nulls_map_to_unknown_members(conn):
    run_pipeline(rows(), conn)
    sql = """SELECT g.state_code FROM fact_complaint f
             JOIN dim_geography g USING (geography_key) WHERE f.complaint_id = 2"""
    assert scalar(conn, sql) == "XX"


def test_rerun_is_idempotent(conn):
    run_pipeline(rows(), conn)
    first = scalar(conn, "SELECT COUNT(*) FROM fact_complaint")
    dims = scalar(conn, "SELECT COUNT(*) FROM dim_company")
    run_pipeline(rows(), conn)
    assert scalar(conn, "SELECT COUNT(*) FROM fact_complaint") == first
    assert scalar(conn, "SELECT COUNT(*) FROM dim_company") == dims


def test_changed_source_row_updates_fact(conn):
    run_pipeline(rows(), conn)
    changed = pd.DataFrame([record(complaint_id="3", timely_response="Yes")])
    run_pipeline(changed, conn)
    assert scalar(conn, "SELECT is_timely FROM fact_complaint WHERE complaint_id=3") == 1


def test_failed_quality_gate_rolls_back_all_warehouse_changes(conn):
    run_pipeline(rows(), conn)
    before = scalar(conn, "SELECT COUNT(*) FROM fact_complaint")
    always_fails = [quality.Check("forced_failure", "error", "SELECT 1", 0)]
    new_row = pd.DataFrame([record(complaint_id="99", company="Brand New Co")])

    with pytest.raises(QualityGateError):
        run_pipeline(new_row, conn, checks=always_fails)

    assert scalar(conn, "SELECT COUNT(*) FROM fact_complaint") == before
    assert scalar(conn, "SELECT COUNT(*) FROM dim_company WHERE company_name='Brand New Co'") == 0
    status = "SELECT status FROM etl_run ORDER BY run_id DESC LIMIT 1"
    assert scalar(conn, status) == "failed_quality_gate"
    assert scalar(conn, "SELECT passed FROM dq_result WHERE check_name='forced_failure'") == 0


def test_all_analytics_queries_run(conn, tmp_path):
    run_pipeline(rows(), conn)
    conn.commit()
    counts = run_reports(conn, tmp_path)
    assert len(counts) == 6
    assert counts["01_monthly_kpis"] >= 1
