-- Idempotent dimension loads: INSERT IGNORE skips members that already exist.

SET SESSION cte_max_recursion_depth = 10000;

INSERT IGNORE INTO dim_date
WITH RECURSIVE calendar (d) AS (
    SELECT DATE('2015-01-01')
    UNION ALL
    SELECT d + INTERVAL 1 DAY FROM calendar WHERE d < '2027-12-31'
)
SELECT
    CAST(DATE_FORMAT(d, '%Y%m%d') AS UNSIGNED),
    d,
    YEAR(d),
    QUARTER(d),
    MONTH(d),
    MONTHNAME(d),
    DATE_FORMAT(d, '%Y-%m'),
    DAYOFWEEK(d),
    DAYNAME(d),
    DAYOFWEEK(d) IN (1, 7)
FROM calendar;

INSERT IGNORE INTO dim_company (company_name)
SELECT DISTINCT company FROM stg_complaints;

INSERT IGNORE INTO dim_issue (issue_name)
SELECT DISTINCT issue FROM stg_complaints;

INSERT IGNORE INTO dim_geography (state_code, state_type)
SELECT DISTINCT
    COALESCE(state, 'XX'),
    CASE
        WHEN state IS NULL THEN 'Unknown'
        WHEN state IN ('AA', 'AE', 'AP') THEN 'Military'
        WHEN state IN ('AS', 'FM', 'GU', 'MH', 'MP', 'PR', 'PW', 'VI') THEN 'Territory'
        ELSE 'State'
    END
FROM stg_complaints;

INSERT IGNORE INTO dim_channel (channel_name)
SELECT DISTINCT COALESCE(channel, 'Unknown') FROM stg_complaints;

INSERT IGNORE INTO dim_response (company_response, public_response)
SELECT DISTINCT
    COALESCE(company_response, 'Unknown'),
    COALESCE(public_response, 'None provided')
FROM stg_complaints;

INSERT IGNORE INTO dim_consumer_profile
    (consumer_consent, tags, is_older_american, is_servicemember)
SELECT DISTINCT
    COALESCE(consumer_consent, 'Not recorded'),
    COALESCE(tags, 'None'),
    COALESCE(tags, '') LIKE '%Older American%',
    COALESCE(tags, '') LIKE '%Servicemember%'
FROM stg_complaints;
