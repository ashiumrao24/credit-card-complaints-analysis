# AWS Serverless Ingestion Pipeline

Extends this project with an event-driven pipeline on AWS. A CSV landing in S3 triggers a Lambda function that validates it, publishes partitioned data, and makes it queryable with SQL through Athena.

> **Status:** not yet deployed to AWS. Tested locally against simulated AWS services (moto).

## Architecture

```text
CSV -> S3 landing/ -> Lambda -> S3 curated/year=YYYY/ -> Glue Data Catalog -> Athena SQL
                        |
                        +-> quarantine/   rejected rows, with reasons
                        +-> rejected/     whole files that fail validation
                        +-> audit/        one manifest per file
                        +-> SQS           events that fail after retries
```

All infrastructure is defined in [`template.yaml`](template.yaml).

## Design decisions

- **Serverless.** Nothing runs between uploads, which suits small batch files.
- **Safe reprocessing.** S3 can deliver an event twice, so output keys come from the source file name and a repeat overwrites the same objects.
- **Stale output cleanup.** Each manifest lists what a file wrote, so a corrected file removes output it no longer produces.
- **File-level quality gate.** A file with missing columns, or more than 5% bad rows, is moved to `rejected/` and publishes nothing.
- **Partition projection.** Athena computes partitions itself, so no crawler is needed.
- **Least-privilege IAM.** The function can read only `landing/` and `audit/`, and write only its output prefixes.
- **Cost guardrails.** Athena cancels queries over 1 GB, query results expire after 7 days, and logs expire after 14 days.
- **No loop.** The trigger only watches `landing/`, and the function never writes there.
- **No narratives in the cloud copy.** Free-text complaints are left out of the upload.

## Local test results

| Measure | Result in simulation |
|---|---:|
| Rows processed | 86,893 |
| Rows rejected | 0 |
| ZIP codes repaired | 6,952 |
| Curated output | 7 yearly partitions, 1.74 MB compressed |
| Tests | 23 passing |

The Athena queries could not run locally. They were checked for logic with DuckDB on the curated output, which returned 86,893 complaints and 85,934 timely responses, matching the dashboard.

## Deploy

You need an AWS account with credentials configured, such as a named profile in `~/.aws/credentials`. Set an AWS budget alert first.

```bash
cd aws-pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export AWS_PROFILE=complaints-project
export AWS_REGION=ap-south-1

python -m scripts.deploy          # creates the stack
python -m scripts.upload_data     # uploads 7 yearly CSVs, which triggers Lambda
python -m scripts.run_queries     # runs Athena SQL, saves CSVs to reports/
python -m scripts.teardown --yes  # deletes everything
```

Run `teardown` when you finish, so nothing stays in your account.

## Run the tests

```bash
pip install -r requirements-dev.txt
pytest
cfn-lint template.yaml
```

The tests use moto, so they need no AWS account and cost nothing.

## Limitations

- Lambda reads a whole file into memory, so files over 50 MB are rejected. Larger files would suit AWS Glue or EMR.
- Duplicate checks work within one file. A complaint repeated across files would appear twice.
- Curated data is gzipped JSON. Parquet would scan less, but needs a Lambda layer or an Athena conversion step.
- moto does not enforce IAM permissions, so those are only proven by a real deployment.
