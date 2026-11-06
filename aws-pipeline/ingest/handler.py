"""S3-triggered Lambda: validate a landed CSV and publish it as partitioned JSON.

Uses only the standard library and boto3, so it deploys without a Lambda layer.

S3 can deliver the same event more than once. Output keys are derived from the source
file name, so processing a file again overwrites the same objects instead of duplicating.
"""
import csv
import datetime as dt
import gzip
import io
import json
import os
from collections import Counter, defaultdict
from urllib.parse import unquote_plus

import boto3

REQUIRED_COLUMNS = (
    "complaint_id", "date_received", "date_sent", "company", "issue", "state", "zip_code",
    "channel", "company_response", "timely_response", "consumer_disputed",
)
YES_NO = {"yes": 1, "no": 0}
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_REJECTED_PCT = float(os.getenv("MAX_REJECTED_PCT", "5"))


def _parse_date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def normalize_zip(value: str) -> tuple[str | None, bool]:
    """Return (zip, repaired). Restores leading zeros lost when ZIPs were stored as numbers."""
    text = value.strip()
    if text.isdigit() and 3 <= len(text) <= 5:
        return text.zfill(5), len(text) < 5
    return None, False


def validate_row(row: dict, seen_ids: set) -> tuple[dict | None, str | None, bool]:
    """Return (clean row, rejection reason, zip repaired)."""
    complaint_id = (row.get("complaint_id") or "").strip()
    if not complaint_id.isdigit():
        return None, "invalid_complaint_id", False
    if complaint_id in seen_ids:
        return None, "duplicate_complaint_id", False

    received = _parse_date(row.get("date_received") or "")
    sent = _parse_date(row.get("date_sent") or "")
    if received is None:
        return None, "invalid_date_received", False
    if sent is None:
        return None, "invalid_date_sent", False

    company = (row.get("company") or "").strip()
    issue = (row.get("issue") or "").strip()
    if not company:
        return None, "missing_company", False
    if not issue:
        return None, "missing_issue", False

    timely = YES_NO.get((row.get("timely_response") or "").strip().lower())
    if timely is None:
        return None, "invalid_timely_response", False

    seen_ids.add(complaint_id)
    zip_code, repaired = normalize_zip(row.get("zip_code") or "")
    disputed = YES_NO.get((row.get("consumer_disputed") or "").strip().lower())
    clean = {
        "complaint_id": int(complaint_id),
        "date_received": received.isoformat(),
        "date_sent": sent.isoformat(),
        "company": company,
        "issue": issue,
        "state": (row.get("state") or "").strip() or None,
        "zip_code": zip_code,
        "channel": (row.get("channel") or "").strip() or None,
        "company_response": (row.get("company_response") or "").strip() or None,
        "is_timely": timely,
        "is_disputed": disputed,
        "days_to_forward": (sent - received).days,
        "is_date_anomaly": int(sent < received),
    }
    return clean, None, repaired


def _jsonl_gz(rows: list[dict]) -> bytes:
    text = "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows)
    return gzip.compress(text.encode("utf-8"), mtime=0)


def _source_name(key: str) -> str:
    return key.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _previous_outputs(s3, bucket: str, name: str) -> list[str]:
    try:
        body = s3.get_object(Bucket=bucket, Key=f"audit/{name}.json")["Body"].read()
    except s3.exceptions.NoSuchKey:
        return []
    return json.loads(body).get("outputs", [])


def _write_manifest(s3, bucket: str, name: str, manifest: dict) -> dict:
    s3.put_object(Bucket=bucket, Key=f"audit/{name}.json",
                  Body=json.dumps(manifest, indent=2).encode("utf-8"),
                  ContentType="application/json")
    print(json.dumps(manifest))
    return manifest


def _reject_file(s3, bucket: str, key: str, name: str, reason: str, **details) -> dict:
    """Move a whole file aside. Retrying would fail the same way, so this does not raise."""
    s3.copy_object(Bucket=bucket, Key=f"rejected/{key.rsplit('/', 1)[-1]}",
                   CopySource={"Bucket": bucket, "Key": key})
    return _write_manifest(s3, bucket, name, {
        "source": key, "status": "rejected", "reason": reason, "outputs": [], **details,
    })


def process_object(s3, bucket: str, key: str) -> dict:
    name = _source_name(key)
    head = s3.head_object(Bucket=bucket, Key=key)
    if head["ContentLength"] > MAX_FILE_BYTES:
        return _reject_file(s3, bucket, key, name, "file_too_large")

    text = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    missing = sorted(set(REQUIRED_COLUMNS) - set(reader.fieldnames or []))
    if missing:
        return _reject_file(s3, bucket, key, name, "schema_drift", missing_columns=missing)

    by_year = defaultdict(list)
    rejected = []
    reasons = Counter()
    seen_ids = set()
    rows_read = zip_repaired = 0
    for row in reader:
        rows_read += 1
        clean, reason, repaired = validate_row(row, seen_ids)
        if reason:
            reasons[reason] += 1
            rejected.append({"reason": reason, "row": row})
            continue
        zip_repaired += repaired
        by_year[clean["date_received"][:4]].append(clean)

    if rows_read == 0:
        return _reject_file(s3, bucket, key, name, "empty_file")
    rejected_pct = 100 * len(rejected) / rows_read
    if rejected_pct > MAX_REJECTED_PCT:
        return _reject_file(s3, bucket, key, name, "too_many_bad_rows",
                            rows_read=rows_read, rejected_pct=round(rejected_pct, 2),
                            rejection_reasons=dict(reasons))

    previous = _previous_outputs(s3, bucket, name)
    outputs = []
    for year, rows in sorted(by_year.items()):
        output_key = f"curated/year={year}/{name}.jsonl.gz"
        s3.put_object(Bucket=bucket, Key=output_key, Body=_jsonl_gz(rows))
        outputs.append(output_key)
    # A corrected file may cover fewer years, so remove what the last version wrote.
    for stale_key in sorted(set(previous) - set(outputs)):
        s3.delete_object(Bucket=bucket, Key=stale_key)

    quarantine_key = f"quarantine/{name}.jsonl.gz"
    if rejected:
        s3.put_object(Bucket=bucket, Key=quarantine_key, Body=_jsonl_gz(rejected))
    else:
        s3.delete_object(Bucket=bucket, Key=quarantine_key)

    return _write_manifest(s3, bucket, name, {
        "source": key,
        "status": "success",
        "rows_read": rows_read,
        "rows_valid": rows_read - len(rejected),
        "rows_rejected": len(rejected),
        "rejection_reasons": dict(reasons),
        "zip_codes_repaired": zip_repaired,
        "outputs": outputs,
    })


def lambda_handler(event, context):
    s3 = boto3.client("s3")
    results = []
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        results.append(process_object(s3, bucket, key))
    return {"processed": len(results), "results": results}
