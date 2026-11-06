-- Dispute rate by resolution type. Only rows where the source recorded a dispute value count.
SELECT r.company_response,
       COUNT(*) AS complaints,
       ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_all,
       ROUND(100 * AVG(f.is_disputed), 2) AS disputed_pct,
       COUNT(f.is_disputed) AS complaints_with_dispute_value
FROM fact_complaint f
JOIN dim_response r USING (response_key)
GROUP BY r.company_response
ORDER BY complaints DESC
