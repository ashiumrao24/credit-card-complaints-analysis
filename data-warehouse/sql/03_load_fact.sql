-- Upsert on complaint_id, so rerunning a load updates rows instead of duplicating them.

INSERT INTO fact_complaint (
    complaint_id, date_received_key, date_sent_key, company_key, issue_key, geography_key,
    channel_key, response_key, profile_key, zip_code, days_to_forward, is_timely,
    is_disputed, is_date_anomaly, has_narrative
)
SELECT * FROM (
    SELECT
        s.complaint_id,
        CAST(DATE_FORMAT(s.date_received, '%Y%m%d') AS UNSIGNED) AS date_received_key,
        CAST(DATE_FORMAT(s.date_sent, '%Y%m%d') AS UNSIGNED) AS date_sent_key,
        c.company_key,
        i.issue_key,
        g.geography_key,
        ch.channel_key,
        r.response_key,
        p.profile_key,
        s.zip_code,
        DATEDIFF(s.date_sent, s.date_received) AS days_to_forward,
        s.is_timely,
        s.is_disputed,
        s.date_sent < s.date_received AS is_date_anomaly,
        s.narrative IS NOT NULL AS has_narrative
    FROM stg_complaints s
    JOIN dim_company c ON c.company_name = s.company
    JOIN dim_issue i ON i.issue_name = s.issue
    JOIN dim_geography g ON g.state_code = COALESCE(s.state, 'XX')
    JOIN dim_channel ch ON ch.channel_name = COALESCE(s.channel, 'Unknown')
    JOIN dim_response r
        ON r.company_response = COALESCE(s.company_response, 'Unknown')
       AND r.public_response = COALESCE(s.public_response, 'None provided')
    JOIN dim_consumer_profile p
        ON p.consumer_consent = COALESCE(s.consumer_consent, 'Not recorded')
       AND p.tags = COALESCE(s.tags, 'None')
) AS incoming
ON DUPLICATE KEY UPDATE
    date_received_key = incoming.date_received_key,
    date_sent_key     = incoming.date_sent_key,
    company_key       = incoming.company_key,
    issue_key         = incoming.issue_key,
    geography_key     = incoming.geography_key,
    channel_key       = incoming.channel_key,
    response_key      = incoming.response_key,
    profile_key       = incoming.profile_key,
    zip_code          = incoming.zip_code,
    days_to_forward   = incoming.days_to_forward,
    is_timely         = incoming.is_timely,
    is_disputed       = incoming.is_disputed,
    is_date_anomaly   = incoming.is_date_anomaly,
    has_narrative     = incoming.has_narrative;

INSERT INTO complaint_narrative (complaint_id, narrative)
SELECT * FROM (
    SELECT complaint_id, narrative FROM stg_complaints WHERE narrative IS NOT NULL
) AS incoming
ON DUPLICATE KEY UPDATE narrative = incoming.narrative;
