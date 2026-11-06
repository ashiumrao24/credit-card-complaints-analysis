"""Load: write validated rows to staging and rejected rows to quarantine."""
import json

import pandas as pd

BATCH_SIZE = 5000

STAGING_COLUMNS = [
    "complaint_id", "date_received", "date_sent", "company", "issue", "state", "zip_code",
    "channel", "company_response", "public_response", "is_timely", "is_disputed",
    "consumer_consent", "tags", "narrative",
]


def _clean(value):
    return None if pd.isna(value) else value


def load_staging(conn, valid: pd.DataFrame) -> int:
    placeholders = ", ".join(["%s"] * len(STAGING_COLUMNS))
    sql = f"INSERT INTO stg_complaints ({', '.join(STAGING_COLUMNS)}) VALUES ({placeholders})"
    rows = [
        tuple(_clean(v) for v in row)
        for row in valid[STAGING_COLUMNS].itertuples(index=False, name=None)
    ]
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE stg_complaints")
        for start in range(0, len(rows), BATCH_SIZE):
            cur.executemany(sql, rows[start : start + BATCH_SIZE])
    return len(rows)


def load_quarantine(conn, run_id: int, rejected: pd.DataFrame) -> int:
    rows = [
        (
            run_id,
            None if _clean(r["complaint_id"]) is None else str(r["complaint_id"])[:64],
            r["reason"],
            json.dumps({k: _clean(v) for k, v in r.items() if k not in ("reason", "narrative")},
                       default=str),
        )
        for r in rejected.to_dict("records")
    ]
    if rows:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO dq_quarantine (run_id, source_id, reason, raw_record) "
                "VALUES (%s, %s, %s, %s)",
                rows,
            )
    return len(rows)
