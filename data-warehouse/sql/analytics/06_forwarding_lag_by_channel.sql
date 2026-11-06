-- Days from CFPB receipt to forwarding, by channel. Median comes from row numbering
-- because MySQL has no built-in MEDIAN function.
WITH numbered AS (
    SELECT ch.channel_name,
           f.days_to_forward,
           ROW_NUMBER() OVER (PARTITION BY f.channel_key ORDER BY f.days_to_forward) AS rn,
           COUNT(*) OVER (PARTITION BY f.channel_key) AS n
    FROM fact_complaint f
    JOIN dim_channel ch USING (channel_key)
)
SELECT channel_name,
       MAX(n) AS complaints,
       ROUND(AVG(days_to_forward), 2) AS avg_days,
       ROUND(AVG(CASE WHEN rn IN (FLOOR((n + 1) / 2), CEIL((n + 1) / 2)) THEN days_to_forward END), 1)
           AS median_days,
       MAX(days_to_forward) AS max_days
FROM numbered
GROUP BY channel_name
ORDER BY complaints DESC
