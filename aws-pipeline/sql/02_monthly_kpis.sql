-- Monthly volume with change from the prior month.
WITH monthly AS (
    SELECT substr(date_received, 1, 7) AS calendar_month,
           COUNT(*) AS complaints,
           AVG(is_timely) AS timely_rate
    FROM complaints
    GROUP BY substr(date_received, 1, 7)
)
SELECT calendar_month,
       complaints,
       complaints - LAG(complaints) OVER (ORDER BY calendar_month) AS change_vs_prior_month,
       ROUND(AVG(complaints) OVER (
           ORDER BY calendar_month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1)
           AS rolling_3_month_avg,
       ROUND(100 * timely_rate, 2) AS timely_pct
FROM monthly
ORDER BY calendar_month
