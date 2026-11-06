-- The year filter uses partition projection, so Athena reads only one partition.
WITH ranked AS (
    SELECT company,
           issue,
           COUNT(*) AS complaints,
           DENSE_RANK() OVER (PARTITION BY company ORDER BY COUNT(*) DESC) AS issue_rank
    FROM complaints
    WHERE year = 2020
    GROUP BY company, issue
),
largest AS (
    SELECT company
    FROM complaints
    WHERE year = 2020
    GROUP BY company
    ORDER BY COUNT(*) DESC
    LIMIT 5
)
SELECT r.company, r.issue_rank, r.issue, r.complaints
FROM ranked r
JOIN largest l ON r.company = l.company
WHERE r.issue_rank <= 3
ORDER BY r.company, r.issue_rank, r.issue
