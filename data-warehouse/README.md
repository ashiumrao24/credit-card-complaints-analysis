# Complaints Data Warehouse

Extends the Tableau dashboard in this repo with a MySQL star schema, a tested Python ETL pipeline, and SQL reporting.

## Pipeline

```text
Excel source -> schema check -> row validation -> staging -> star schema -> quality gate -> SQL reports
                                     |                                          |
                                 quarantine                               rollback on failure
```

## Star schema

Grain: one row per complaint.

- **Fact:** `fact_complaint`
- **Dimensions:** `dim_date`, `dim_company`, `dim_issue`, `dim_geography`, `dim_channel`, `dim_response`, `dim_consumer_profile`
- **Operational tables:** `etl_run`, `dq_result`, `dq_quarantine`
- **Side table:** `complaint_narrative` keeps long text out of fact table scans

## Results on the full dataset

| Measure | Result |
|---|---:|
| Rows read and loaded | 86,893 |
| Rows quarantined | 0 |
| Timely responses | 85,934 (98.90%, matches the dashboard) |
| ZIP codes repaired | 6,952 |
| Dates flagged | 1,148 |
| Tests | 18 passing |

## Data quality findings

- **Lost ZIP leading zeros:** 6,952 ZIP codes had fewer than 5 digits. After repair, 99.2% of ZIPs starting with 0 sit in the expected northeastern states or military mail codes.
- **Sent before received:** all 1,148 cases are exactly one day early and fall in 2015-2018. They are flagged and kept, because dropping them would change business totals.
- **Unusable columns:** `Sub-issue` and `Sub-product` are 100% empty. Tableau helper columns are also excluded.

## Design decisions

- **Validate in Python, transform in SQL.** Row rules are unit-testable without a database, while set-based joins belong in SQL.
- **One transaction for dimensions, fact, and checks.** A failed blocking check rolls all of them back.
- **Upserts on `complaint_id`.** Rerunning a load updates rows and never duplicates them.
- **Unknown members for nulls.** Fact foreign keys stay `NOT NULL`, so inner joins never lose rows.

## Run it

Requires Python 3.11+ and a MySQL 8+ server.

```bash
cd data-warehouse
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # add your MySQL settings
set -a; source .env; set +a

python -m warehouse.pipeline      # loads ../Credit Card Dashboard.xlsx
python -m warehouse.reports       # writes CSVs to reports/
pytest                            # unit tests only
RUN_DB_TESTS=1 pytest             # also runs integration tests
```

Integration tests drop and recreate a database named `complaints_dw_test`.

## SQL reports

| File | Techniques |
|---|---|
| `01_monthly_kpis.sql` | CTE, `LAG`, rolling average |
| `02_top_issues_per_company.sql` | `DENSE_RANK`, partitioned share of total |
| `03_company_scorecard.sql` | Conditional aggregation, `RANK`, `HAVING` |
| `04_state_pareto.sql` | Running total, `ROW_NUMBER` |
| `05_resolution_outcomes.sql` | Share of total with window functions |
| `06_forwarding_lag_by_channel.sql` | Median built from `ROW_NUMBER` |

## Limitations

- Each load reads the whole file. Rows deleted from the source are not removed from the warehouse.
- Dimensions keep current values only, with no change history.
- The pipeline runs by hand, with no scheduler.
