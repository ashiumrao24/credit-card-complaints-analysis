-- Pareto view: how few states account for most complaints.
WITH by_state AS (
    SELECT g.state_code, COUNT(*) AS complaints
    FROM fact_complaint f
    JOIN dim_geography g USING (geography_key)
    WHERE g.state_type = 'State'
    GROUP BY g.state_code
)
SELECT state_code,
       complaints,
       ROW_NUMBER() OVER (ORDER BY complaints DESC, state_code) AS state_rank,
       ROUND(100 * SUM(complaints) OVER (ORDER BY complaints DESC, state_code)
             / SUM(complaints) OVER (), 2) AS cumulative_pct
FROM by_state
ORDER BY state_rank
