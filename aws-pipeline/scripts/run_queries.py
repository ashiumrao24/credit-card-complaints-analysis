"""Run every query in sql/ on Athena and save the results to reports/."""
import csv
import time
from pathlib import Path

from scripts.common import session

ROOT = Path(__file__).resolve().parent.parent
DATABASE = "complaints_lake"
WORKGROUP = "complaints"


def run_query(athena, sql: str) -> tuple[list[list[str]], int]:
    """Return (rows including the header, bytes scanned)."""
    query_id = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": DATABASE},
        WorkGroup=WORKGROUP,
    )["QueryExecutionId"]

    while True:
        execution = athena.get_query_execution(QueryExecutionId=query_id)["QueryExecution"]
        state = execution["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            reason = execution["Status"].get("StateChangeReason", "unknown")
            raise RuntimeError(f"Athena query {state}: {reason}")
        time.sleep(1)

    rows = []
    for page in athena.get_paginator("get_query_results").paginate(QueryExecutionId=query_id):
        for row in page["ResultSet"]["Rows"]:
            rows.append([cell.get("VarCharValue", "") for cell in row["Data"]])
    return rows, execution.get("Statistics", {}).get("DataScannedInBytes", 0)


if __name__ == "__main__":
    client = session().client("athena")
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    for path in sorted((ROOT / "sql").glob("*.sql")):
        result, scanned = run_query(client, path.read_text(encoding="utf-8"))
        with (reports / f"{path.stem}.csv").open("w", newline="", encoding="utf-8") as output:
            csv.writer(output).writerows(result)
        print(f"{path.stem}: {len(result) - 1} rows, {scanned / 1_000_000:.2f} MB scanned")
