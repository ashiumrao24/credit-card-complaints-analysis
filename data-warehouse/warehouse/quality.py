"""Post-load data quality checks. Any failed 'error' check rolls the whole load back."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    severity: str  # 'error' blocks the load, 'warning' is only recorded
    sql: str  # must return a single number
    max_allowed: float


CHECKS = [
    Check(
        "staged_rows_missing_from_fact", "error",
        """SELECT COUNT(*) FROM stg_complaints s
           LEFT JOIN fact_complaint f USING (complaint_id)
           WHERE f.complaint_id IS NULL""",
        0,
    ),
    Check(
        "timely_total_mismatch", "error",
        """SELECT ABS((SELECT COALESCE(SUM(is_timely), 0) FROM stg_complaints) -
                      (SELECT COALESCE(SUM(f.is_timely), 0) FROM fact_complaint f
                       JOIN stg_complaints s USING (complaint_id)))""",
        0,
    ),
    Check(
        "future_dated_complaints", "error",
        """SELECT COUNT(*) FROM fact_complaint f
           JOIN dim_date d ON d.date_key = f.date_received_key
           WHERE d.full_date > CURRENT_DATE""",
        0,
    ),
    Check(
        "sent_before_received_pct", "warning",
        "SELECT COALESCE(100 * AVG(is_date_anomaly), 0) FROM fact_complaint", 5,
    ),
    Check(
        "sent_more_than_1_day_before_received", "error",
        "SELECT COUNT(*) FROM fact_complaint WHERE days_to_forward < -1", 0,
    ),
    Check(
        "unknown_state_pct", "warning",
        """SELECT COALESCE(100 * AVG(g.state_code = 'XX'), 0) FROM fact_complaint f
           JOIN dim_geography g USING (geography_key)""",
        2,
    ),
    Check(
        "missing_zip_pct", "warning",
        "SELECT COALESCE(100 * AVG(zip_code IS NULL), 0) FROM fact_complaint", 25,
    ),
]


def run_checks(conn, checks=CHECKS) -> list[dict]:
    results = []
    with conn.cursor() as cur:
        for check in checks:
            cur.execute(check.sql)
            value = float(cur.fetchone()[0] or 0)
            passed = value <= check.max_allowed
            results.append(
                {
                    "name": check.name,
                    "severity": check.severity,
                    "value": round(value, 4),
                    "max_allowed": check.max_allowed,
                    "passed": passed,
                }
            )
    return results


def blocking_failures(results: list[dict]) -> list[dict]:
    return [r for r in results if r["severity"] == "error" and not r["passed"]]


def save_results(conn, run_id: int, results: list[dict]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO dq_result (run_id, check_name, severity, measured_value, "
            "max_allowed, passed) VALUES (%s, %s, %s, %s, %s, %s)",
            [
                (run_id, r["name"], r["severity"], r["value"], r["max_allowed"], r["passed"])
                for r in results
            ],
        )
