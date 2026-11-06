"""Split the Excel source into one CSV per year and drop them into S3 landing/.

Free-text narratives are left out: Athena does not need them, and they keep consumer
writing out of the cloud copy.
"""
import argparse
from pathlib import Path

import pandas as pd

from scripts.common import data_bucket, session

SOURCE = Path(__file__).resolve().parents[2] / "Credit Card Dashboard.xlsx"
OUTPUT = Path("data/landing")
COLUMNS = {
    "Complaint ID": "complaint_id",
    "Date received": "date_received",
    "Date sent to company2": "date_sent",
    "Company": "company",
    "Issue": "issue",
    "State": "state",
    "ZIP code": "zip_code",
    "Submitted via": "channel",
    "Company response to consumer": "company_response",
    "Timely response?": "timely_response",
    "Consumer disputed?": "consumer_disputed",
}


def prepare(source: Path = SOURCE, output: Path = OUTPUT) -> list[Path]:
    raw = pd.read_excel(source, dtype=str).rename(columns=lambda c: str(c).strip())
    frame = raw[list(COLUMNS)].rename(columns=COLUMNS)
    frame["date_received"] = frame["date_received"].str[:10]
    frame["date_sent"] = frame["date_sent"].str[:10]
    output.mkdir(parents=True, exist_ok=True)
    paths = []
    for year, group in frame.groupby(frame["date_received"].str[:4]):
        path = output / f"complaints_{year}.csv"
        group.to_csv(path, index=False)
        paths.append(path)
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true", help="write CSVs, skip upload")
    args = parser.parse_args()

    files = prepare()
    print(f"Prepared {len(files)} files in {OUTPUT}")
    if not args.prepare_only:
        aws = session()
        client = aws.client("s3")
        bucket = data_bucket(aws)
        for file in files:
            client.upload_file(str(file), bucket, f"landing/{file.name}")
            print(f"Uploaded s3://{bucket}/landing/{file.name}")
