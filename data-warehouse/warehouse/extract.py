"""Extract: read the source file and map it to clean snake_case column names."""
from pathlib import Path

import pandas as pd

# Source column -> warehouse column. Tableau helper columns (donut, Number of Records,
# Dimension, Table Name) and the 100% empty Sub-issue/Sub-product are dropped on purpose.
COLUMN_MAP = {
    "Complaint ID": "complaint_id",
    "Date received": "date_received",
    "Date sent to company2": "date_sent",
    "Company": "company",
    "Issue": "issue",
    "State": "state",
    "ZIP code": "zip_code",
    "Submitted via": "channel",
    "Company response to consumer": "company_response",
    "Company public response": "public_response",
    "Timely response?": "timely_response",
    "Consumer disputed?": "consumer_disputed",
    "Consumer consent provided?": "consumer_consent",
    "Tags": "tags",
    "Consumer complaint narrative": "narrative",
}


class SchemaDriftError(Exception):
    """The source file no longer has the columns this pipeline depends on."""


def apply_schema(raw: pd.DataFrame) -> pd.DataFrame:
    """Fail fast on schema drift, then keep and rename only the mapped columns."""
    raw = raw.rename(columns=lambda c: str(c).strip())
    missing = sorted(set(COLUMN_MAP) - set(raw.columns))
    if missing:
        raise SchemaDriftError(f"Source is missing required columns: {missing}")
    return raw[list(COLUMN_MAP)].rename(columns=COLUMN_MAP)


def read_source(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    # Read everything as text: type conversion belongs in validation, where failures
    # can be reported row by row instead of crashing the load.
    if path.suffix.lower() == ".csv":
        raw = pd.read_csv(path, dtype=str)
    else:
        raw = pd.read_excel(path, dtype=str)
    return apply_schema(raw)
