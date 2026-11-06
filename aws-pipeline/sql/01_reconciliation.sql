-- Should match the warehouse and dashboard: 86,893 complaints and 85,934 timely.
SELECT COUNT(*) AS complaints,
       COUNT(DISTINCT complaint_id) AS distinct_complaints,
       SUM(is_timely) AS timely,
       ROUND(100.0 * AVG(is_timely), 2) AS timely_pct,
       SUM(is_date_anomaly) AS date_anomalies
FROM complaints
