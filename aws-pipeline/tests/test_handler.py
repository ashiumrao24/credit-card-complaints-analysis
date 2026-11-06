import csv
import gzip
import io
import json

import boto3
import pytest
from moto import mock_aws

from ingest.handler import REQUIRED_COLUMNS, lambda_handler, normalize_zip

BUCKET = "test-bucket"


def row(**overrides):
    base = {
        "complaint_id": "1", "date_received": "2020-01-02", "date_sent": "2020-01-03",
        "company": "Acme", "issue": "Billing disputes", "state": "NJ", "zip_code": "7030",
        "channel": "Web", "company_response": "Closed", "timely_response": "Yes",
        "consumer_disputed": "No",
    }
    return base | overrides


def to_csv(rows, columns=REQUIRED_COLUMNS):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def event(key):
    return {"Records": [{"s3": {"bucket": {"name": BUCKET}, "object": {"key": key}}}]}


@pytest.fixture
def s3(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def land(s3, body, key="landing/batch.csv"):
    s3.put_object(Bucket=BUCKET, Key=key, Body=body.encode("utf-8"))
    return lambda_handler(event(key), None)["results"][0]


def read_jsonl(s3, key):
    body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    return [json.loads(line) for line in gzip.decompress(body).splitlines()]


def keys(s3, prefix):
    return [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix).get("Contents", [])]


def test_valid_file_is_partitioned_by_year(s3):
    result = land(s3, to_csv([
        row(complaint_id="1"),
        row(complaint_id="2", date_received="2021-05-05", date_sent="2021-05-05"),
    ]))
    assert result["status"] == "success"
    assert keys(s3, "curated/") == [
        "curated/year=2020/batch.jsonl.gz", "curated/year=2021/batch.jsonl.gz",
    ]


def test_clean_row_is_typed_and_repaired(s3):
    result = land(s3, to_csv([row(date_sent="2020-01-01")]))
    record = read_jsonl(s3, "curated/year=2020/batch.jsonl.gz")[0]
    assert record["zip_code"] == "07030"
    assert record["is_timely"] == 1
    assert record["is_disputed"] == 0
    assert record["days_to_forward"] == -1
    assert record["is_date_anomaly"] == 1
    assert result["zip_codes_repaired"] == 1


def test_bad_rows_are_quarantined_with_reasons(s3):
    good = [row(complaint_id=str(i)) for i in range(1, 100)]
    result = land(s3, to_csv([*good, row(complaint_id="abc")]))
    assert result["rows_valid"] == 99
    assert result["rejection_reasons"] == {"invalid_complaint_id": 1}
    assert read_jsonl(s3, "quarantine/batch.jsonl.gz")[0]["reason"] == "invalid_complaint_id"


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"date_received": "nope"}, "invalid_date_received"),
        ({"date_sent": ""}, "invalid_date_sent"),
        ({"company": " "}, "missing_company"),
        ({"issue": ""}, "missing_issue"),
        ({"timely_response": "Maybe"}, "invalid_timely_response"),
        ({"complaint_id": "1"}, "duplicate_complaint_id"),
    ],
)
def test_each_rejection_reason(s3, overrides, reason):
    good = [row(complaint_id=str(i)) for i in range(1, 100)]
    bad = row(**({"complaint_id": "500"} | overrides))
    result = land(s3, to_csv([*good, bad]))
    assert result["rejection_reasons"] == {reason: 1}


def test_processing_same_event_twice_does_not_duplicate(s3):
    body = to_csv([row()])
    land(s3, body)
    lambda_handler(event("landing/batch.csv"), None)
    assert keys(s3, "curated/") == ["curated/year=2020/batch.jsonl.gz"]
    assert len(read_jsonl(s3, "curated/year=2020/batch.jsonl.gz")) == 1


def test_corrected_file_removes_stale_output(s3):
    land(s3, to_csv([row(complaint_id="1"),
                     row(complaint_id="2", date_received="2021-01-01", date_sent="2021-01-01")]))
    land(s3, to_csv([row(complaint_id="1")]))
    assert keys(s3, "curated/") == ["curated/year=2020/batch.jsonl.gz"]


def test_schema_drift_rejects_whole_file(s3):
    columns = [c for c in REQUIRED_COLUMNS if c != "company"]
    result = land(s3, to_csv([row()], columns))
    assert result["status"] == "rejected"
    assert result["missing_columns"] == ["company"]
    assert keys(s3, "curated/") == []
    assert keys(s3, "rejected/") == ["rejected/batch.csv"]


def test_too_many_bad_rows_rejects_whole_file(s3):
    result = land(s3, to_csv([row(complaint_id="1"), row(complaint_id="bad")]))
    assert result["reason"] == "too_many_bad_rows"
    assert keys(s3, "curated/") == []


def test_empty_file_is_rejected(s3):
    assert land(s3, to_csv([]))["reason"] == "empty_file"


def test_url_encoded_key_is_decoded(s3):
    s3.put_object(Bucket=BUCKET, Key="landing/my file.csv", Body=to_csv([row()]).encode())
    result = lambda_handler(event("landing/my+file.csv"), None)["results"][0]
    assert result["status"] == "success"


def test_manifest_records_the_run(s3):
    land(s3, to_csv([row()]))
    manifest = json.loads(s3.get_object(Bucket=BUCKET, Key="audit/batch.json")["Body"].read())
    assert manifest["rows_read"] == 1
    assert manifest["outputs"] == ["curated/year=2020/batch.jsonl.gz"]


def test_normalize_zip():
    assert normalize_zip("501") == ("00501", True)
    assert normalize_zip("94103") == ("94103", False)
    assert normalize_zip("ABCDE") == (None, False)
    assert normalize_zip("") == (None, False)
