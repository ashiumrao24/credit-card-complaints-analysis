-- Monthly volume with month-over-month change, 3-month average and timely-response rate.
WITH monthly AS (
    SELECT d.calendar_month,
           COUNT(*) AS complaints,
           AVG(f.is_timely) AS timely_rate
    FROM fact_complaint f
    JOIN dim_date d ON d.date_key = f.date_received_key
    GROUP BY d.calendar_month
)
SELECT calendar_month,
       complaints,
       complaints - LAG(complaints) OVER w AS change_vs_prior_month,
       ROUND(100 * (complaints - LAG(complaints) OVER w) / LAG(complaints) OVER w, 1)
           AS pct_change_vs_prior_month,
       ROUND(AVG(complaints) OVER (ORDER BY calendar_month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1)
           AS rolling_3_month_avg,
       ROUND(100 * timely_rate, 2) AS timely_pct
FROM monthly
WINDOW w AS (ORDER BY calendar_month)
ORDER BY calendar_month
