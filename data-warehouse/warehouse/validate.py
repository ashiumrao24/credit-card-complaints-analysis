"""Validate: row-level cleaning and rules. Pure pandas, so it is unit-testable without a DB.

Hard failures go to quarantine with a reason. Soft issues stay in the data and are
flagged or repaired, because dropping them would change the business totals.
"""
from dataclasses import dataclass

import pandas as pd

YES_NO = {"yes": 1, "no": 0}


@dataclass
class ValidationResult:
    valid: pd.DataFrame
    rejected: pd.DataFrame
    zip_codes_repaired: int


def normalize_zip(series: pd.Series) -> tuple[pd.Series, int]:
    """Restore leading zeros lost when ZIPs were stored as numbers.

    '7030' becomes '07030'. Values that are not 3-5 digits become null.
    """
    repaired = 0
    fixed = []
    for value in series:
        text = value.strip() if isinstance(value, str) else ""
        if text.isdigit() and 3 <= len(text) <= 5:
            repaired += len(text) < 5
            fixed.append(text.zfill(5))
        else:
            fixed.append(None)
    return pd.Series(fixed, index=series.index, dtype="object"), repaired


def _strip_text(df: pd.DataFrame) -> pd.DataFrame:
    df = df.astype("object").where(df.notna(), None)
    for col in df.columns:
        df[col] = df[col].map(lambda v: (v.strip() or None) if isinstance(v, str) else v)
    return df


def validate(df: pd.DataFrame) -> ValidationResult:
    df = _strip_text(df.copy())

    ids = pd.to_numeric(df["complaint_id"], errors="coerce")
    received = pd.to_datetime(df["date_received"], errors="coerce")
    sent = pd.to_datetime(df["date_sent"], errors="coerce")
    timely = df["timely_response"].map(
        lambda v: YES_NO.get(v.lower()) if isinstance(v, str) else None
    )

    reasons = pd.Series([None] * len(df), index=df.index, dtype="object")

    def reject(mask: pd.Series, reason: str) -> None:
        reasons[mask & reasons.isna()] = reason

    reject(ids.isna(), "invalid_complaint_id")
    reject(received.isna(), "invalid_date_received")
    reject(sent.isna(), "invalid_date_sent")
    reject(df["company"].isna(), "missing_company")
    reject(df["issue"].isna(), "missing_issue")
    reject(timely.isna(), "invalid_timely_response")
    # Keep the first occurrence of each id; later copies are rejected, not merged.
    reject(ids.duplicated(keep="first") & ids.notna(), "duplicate_complaint_id")

    is_bad = reasons.notna()
    rejected = df[is_bad].copy()
    rejected["reason"] = reasons[is_bad]

    valid = df[~is_bad].copy()
    valid["complaint_id"] = ids[~is_bad].astype("int64")
    valid["date_received"] = received[~is_bad].dt.date
    valid["date_sent"] = sent[~is_bad].dt.date
    valid["is_timely"] = timely[~is_bad].astype("int64")
    valid["is_disputed"] = valid["consumer_disputed"].map(
        lambda v: YES_NO.get(v.lower()) if isinstance(v, str) else None
    )
    valid["zip_code"], repaired = normalize_zip(valid["zip_code"])
    valid = valid.drop(columns=["timely_response", "consumer_disputed"])
    return ValidationResult(valid=valid, rejected=rejected, zip_codes_repaired=repaired)
