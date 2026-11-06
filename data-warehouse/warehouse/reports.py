"""Run every query in sql/analytics and save the results as CSV for BI tools."""
import csv
from pathlib import Path

from warehouse.config import load_config
from warehouse.db import SQL_DIR, connect

REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"


def run_reports(conn, output_dir: Path = REPORT_DIR) -> dict[str, int]:
    output_dir.mkdir(exist_ok=True)
    counts = {}
    for path in sorted((SQL_DIR / "analytics").glob("*.sql")):
        with conn.cursor() as cur:
            cur.execute(path.read_text(encoding="utf-8"))
            rows = cur.fetchall()
            header = [col[0] for col in cur.description]
        with (output_dir / f"{path.stem}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
        counts[path.stem] = len(rows)
    return counts


if __name__ == "__main__":
    connection = connect(load_config())
    for name, count in run_reports(connection).items():
        print(f"{name}: {count} rows")
    connection.close()
