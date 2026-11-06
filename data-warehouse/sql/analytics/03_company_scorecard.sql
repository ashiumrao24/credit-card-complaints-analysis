-- Service scorecard for companies with at least 500 complaints.
SELECT c.company_name,
       COUNT(*) AS complaints,
       ROUND(100 * AVG(f.is_timely), 2) AS timely_pct,
       ROUND(100 * AVG(f.is_disputed), 2) AS disputed_pct,
       ROUND(100 * AVG(r.company_response = 'Closed with monetary relief'), 2) AS monetary_relief_pct,
       RANK() OVER (ORDER BY AVG(f.is_disputed) ASC) AS lowest_dispute_rank
FROM fact_complaint f
JOIN dim_company c USING (company_key)
JOIN dim_response r USING (response_key)
GROUP BY c.company_key, c.company_name
HAVING COUNT(*) >= 500
ORDER BY complaints DESC
