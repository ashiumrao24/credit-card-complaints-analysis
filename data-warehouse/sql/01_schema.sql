-- Star schema. Grain of fact_complaint: one row per complaint.

CREATE TABLE IF NOT EXISTS etl_run (
    run_id             INT AUTO_INCREMENT PRIMARY KEY,
    source_file        VARCHAR(255) NOT NULL,
    status             VARCHAR(30)  NOT NULL,
    started_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at        TIMESTAMP    NULL,
    rows_read          INT,
    rows_loaded        INT,
    rows_rejected      INT,
    zip_codes_repaired INT
);

CREATE TABLE IF NOT EXISTS dq_result (
    run_id         INT NOT NULL,
    check_name     VARCHAR(80) NOT NULL,
    severity       VARCHAR(10) NOT NULL,
    measured_value DECIMAL(14,4) NOT NULL,
    max_allowed    DECIMAL(14,4) NOT NULL,
    passed         BOOLEAN NOT NULL,
    PRIMARY KEY (run_id, check_name),
    FOREIGN KEY (run_id) REFERENCES etl_run (run_id)
);

CREATE TABLE IF NOT EXISTS dq_quarantine (
    quarantine_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id        INT NOT NULL,
    source_id     VARCHAR(64),
    reason        VARCHAR(50) NOT NULL,
    raw_record    JSON NOT NULL,
    FOREIGN KEY (run_id) REFERENCES etl_run (run_id),
    INDEX idx_quarantine_reason (reason)
);

CREATE TABLE IF NOT EXISTS stg_complaints (
    complaint_id     BIGINT PRIMARY KEY,
    date_received    DATE NOT NULL,
    date_sent        DATE NOT NULL,
    company          VARCHAR(120) NOT NULL,
    issue            VARCHAR(120) NOT NULL,
    state            CHAR(2),
    zip_code         CHAR(5),
    channel          VARCHAR(30),
    company_response VARCHAR(60),
    public_response  VARCHAR(200),
    is_timely        BOOLEAN NOT NULL,
    is_disputed      BOOLEAN,
    consumer_consent VARCHAR(30),
    tags             VARCHAR(50),
    narrative        TEXT
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key     INT PRIMARY KEY,
    full_date    DATE NOT NULL UNIQUE,
    year         SMALLINT NOT NULL,
    quarter      TINYINT NOT NULL,
    month        TINYINT NOT NULL,
    month_name   VARCHAR(10) NOT NULL,
    calendar_month   CHAR(7) NOT NULL,
    day_of_week  TINYINT NOT NULL,
    day_name     VARCHAR(10) NOT NULL,
    is_weekend   BOOLEAN NOT NULL,
    INDEX idx_date_calendar_month (calendar_month)
);

CREATE TABLE IF NOT EXISTS dim_company (
    company_key  INT AUTO_INCREMENT PRIMARY KEY,
    company_name VARCHAR(120) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dim_issue (
    issue_key  INT AUTO_INCREMENT PRIMARY KEY,
    issue_name VARCHAR(120) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dim_geography (
    geography_key INT AUTO_INCREMENT PRIMARY KEY,
    state_code    CHAR(2) NOT NULL UNIQUE,
    state_type    VARCHAR(20) NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_channel (
    channel_key  INT AUTO_INCREMENT PRIMARY KEY,
    channel_name VARCHAR(30) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dim_response (
    response_key     INT AUTO_INCREMENT PRIMARY KEY,
    company_response VARCHAR(60) NOT NULL,
    public_response  VARCHAR(200) NOT NULL,
    UNIQUE KEY uq_response (company_response, public_response)
);

-- Junk dimension: low-cardinality consumer attributes kept out of the fact table.
CREATE TABLE IF NOT EXISTS dim_consumer_profile (
    profile_key       INT AUTO_INCREMENT PRIMARY KEY,
    consumer_consent  VARCHAR(30) NOT NULL,
    tags              VARCHAR(50) NOT NULL,
    is_older_american BOOLEAN NOT NULL,
    is_servicemember  BOOLEAN NOT NULL,
    UNIQUE KEY uq_profile (consumer_consent, tags)
);

CREATE TABLE IF NOT EXISTS fact_complaint (
    complaint_id      BIGINT PRIMARY KEY,
    date_received_key INT NOT NULL,
    date_sent_key     INT NOT NULL,
    company_key       INT NOT NULL,
    issue_key         INT NOT NULL,
    geography_key     INT NOT NULL,
    channel_key       INT NOT NULL,
    response_key      INT NOT NULL,
    profile_key       INT NOT NULL,
    zip_code          CHAR(5),
    days_to_forward   SMALLINT NOT NULL,
    is_timely         BOOLEAN NOT NULL,
    is_disputed       BOOLEAN,
    is_date_anomaly   BOOLEAN NOT NULL,
    has_narrative     BOOLEAN NOT NULL,
    FOREIGN KEY (date_received_key) REFERENCES dim_date (date_key),
    FOREIGN KEY (date_sent_key)     REFERENCES dim_date (date_key),
    FOREIGN KEY (company_key)       REFERENCES dim_company (company_key),
    FOREIGN KEY (issue_key)         REFERENCES dim_issue (issue_key),
    FOREIGN KEY (geography_key)     REFERENCES dim_geography (geography_key),
    FOREIGN KEY (channel_key)       REFERENCES dim_channel (channel_key),
    FOREIGN KEY (response_key)      REFERENCES dim_response (response_key),
    FOREIGN KEY (profile_key)       REFERENCES dim_consumer_profile (profile_key),
    INDEX idx_fact_company_date (company_key, date_received_key)
);

-- Long free text lives beside the fact table so fact scans stay narrow.
CREATE TABLE IF NOT EXISTS complaint_narrative (
    complaint_id BIGINT PRIMARY KEY,
    narrative    TEXT NOT NULL,
    FOREIGN KEY (complaint_id) REFERENCES fact_complaint (complaint_id)
);
