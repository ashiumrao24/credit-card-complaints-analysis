import pandas as pd
import pytest

from warehouse.extract import COLUMN_MAP, SchemaDriftError, apply_schema
from warehouse.validate import normalize_zip, validate


def record(**overrides):
    base = {
        "complaint_id": "1", "date_received": "2020-01-02", "date_sent": "2020-01-03",
        "company": "Acme Bank", "issue": "Billing disputes", "state": "NJ",
        "zip_code": "07030", "channel": "Web", "company_response": "Closed",
        "public_response": None, "timely_response": "Yes", "consumer_disputed": "No",
        "consumer_consent": None, "tags": None, "narrative": None,
    }
    return base | overrides


def frame(*rows):
    return pd.DataFrame(list(rows))


def test_valid_row_is_typed():
    result = validate(frame(record()))
    row = result.valid.iloc[0]
    assert len(result.rejected) == 0
    assert row["complaint_id"] == 1
    assert row["is_timely"] == 1
    assert row["is_disputed"] == 0


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"complaint_id": "abc"}, "invalid_complaint_id"),
        ({"date_received": "not a date"}, "invalid_date_received"),
        ({"date_sent": None}, "invalid_date_sent"),
        ({"company": "   "}, "missing_company"),
        ({"issue": None}, "missing_issue"),
        ({"timely_response": "Maybe"}, "invalid_timely_response"),
    ],
)
def test_bad_rows_are_quarantined_with_reason(overrides, reason):
    result = validate(frame(record(**overrides)))
    assert len(result.valid) == 0
    assert result.rejected.iloc[0]["reason"] == reason


def test_duplicate_id_keeps_first_row():
    result = validate(frame(record(company="First"), record(company="Second")))
    assert result.valid["company"].tolist() == ["First"]
    assert result.rejected.iloc[0]["reason"] == "duplicate_complaint_id"


def test_missing_dispute_value_stays_null():
    result = validate(frame(record(consumer_disputed=None)))
    assert result.valid.iloc[0]["is_disputed"] is None


def test_zip_leading_zeros_are_restored_and_junk_is_nulled():
    fixed, repaired = normalize_zip(pd.Series(["7030", "501", "94103", "ABCDE", None]))
    assert fixed.tolist() == ["07030", "00501", "94103", None, None]
    assert repaired == 2


def test_schema_drift_fails_fast():
    raw = pd.DataFrame({name: ["x"] for name in COLUMN_MAP}).drop(columns=["Company"])
    with pytest.raises(SchemaDriftError, match="Company"):
        apply_schema(raw)


def test_source_column_names_with_stray_spaces_are_accepted():
    raw = pd.DataFrame({f"{name} ": ["x"] for name in COLUMN_MAP})
    assert list(apply_schema(raw).columns) == list(COLUMN_MAP.values())
