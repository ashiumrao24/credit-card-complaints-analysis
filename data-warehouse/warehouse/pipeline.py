"""Run the full ETL: extract -> validate -> stage -> build star schema -> quality gate."""
import argparse
import logging
import time

from warehouse import extract, load, quality
from warehouse.config import load_config
from warehouse.db import connect, run_script
from warehouse.validate import validate

log = logging.getLogger("warehouse")


class QualityGateError(Exception):
    """A blocking data quality check failed, so the load was rolled back."""


def _start_run(conn, source: str) -> int:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO etl_run (source_file, status) VALUES (%s, 'running')", (source,))
        run_id = cur.lastrowid
    conn.commit()
    return run_id


def _finish_run(conn, run_id: int, status: str, stats: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE etl_run SET status=%s, finished_at=CURRENT_TIMESTAMP, rows_read=%s,
               rows_loaded=%s, rows_rejected=%s, zip_codes_repaired=%s WHERE run_id=%s""",
            (status, stats.get("read"), stats.get("loaded"), stats.get("rejected"),
             stats.get("zip_repaired"), run_id),
        )
    conn.commit()


def run_pipeline(df, conn, source: str = "dataframe", checks=None) -> dict:
    run_script(conn, "01_schema.sql")
    run_id = _start_run(conn, source)
    stats = {"run_id": run_id, "read": len(df)}
    try:
        result = validate(df)
        stats["rejected"] = len(result.rejected)
        stats["zip_repaired"] = result.zip_codes_repaired
        load.load_quarantine(conn, run_id, result.rejected)
        conn.commit()

        # TRUNCATE commits implicitly, so staging is filled before the transaction starts.
        stats["loaded"] = load.load_staging(conn, result.valid)
        conn.commit()

        # Dimensions, fact and checks share one transaction: a failed gate undoes all of it.
        run_script(conn, "02_load_dimensions.sql")
        run_script(conn, "03_load_fact.sql")
        results = quality.run_checks(conn, checks if checks is not None else quality.CHECKS)
        failures = quality.blocking_failures(results)
        stats["checks"] = results
        if failures:
            conn.rollback()
            quality.save_results(conn, run_id, results)
            _finish_run(conn, run_id, "failed_quality_gate", stats)
            raise QualityGateError(f"Blocking checks failed: {[f['name'] for f in failures]}")
        conn.commit()
        quality.save_results(conn, run_id, results)
        _finish_run(conn, run_id, "success", stats)
        return stats
    except QualityGateError:
        raise
    except Exception:
        conn.rollback()
        _finish_run(conn, run_id, "failed", stats)
        raise


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="../Credit Card Dashboard.xlsx")
    args = parser.parse_args()

    started = time.perf_counter()
    df = extract.read_source(args.source)
    log.info("Extracted %s rows in %.1fs", len(df), time.perf_counter() - started)

    conn = connect(load_config())
    try:
        load_started = time.perf_counter()
        stats = run_pipeline(df, conn, source=args.source)
    finally:
        conn.close()
    log.info(
        "Run %s: read=%s loaded=%s rejected=%s zip_repaired=%s in %.1fs",
        stats["run_id"], stats["read"], stats["loaded"], stats["rejected"],
        stats["zip_repaired"], time.perf_counter() - load_started,
    )
    for check in stats["checks"]:
        log.info("%-40s %-8s value=%-10s limit=%-6s %s", check["name"], check["severity"],
                 check["value"], check["max_allowed"], "PASS" if check["passed"] else "FAIL")


if __name__ == "__main__":
    main()
