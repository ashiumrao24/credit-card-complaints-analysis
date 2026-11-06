-- Top 3 issues for each of the 10 largest companies.
WITH top_companies AS (
    SELECT company_key
    FROM fact_complaint
    GROUP BY company_key
    ORDER BY COUNT(*) DESC
    LIMIT 10
),
ranked AS (
    SELECT c.company_name,
           i.issue_name,
           COUNT(*) AS complaints,
           DENSE_RANK() OVER (PARTITION BY c.company_key ORDER BY COUNT(*) DESC) AS issue_rank,
           ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY c.company_key), 1)
               AS pct_of_company
    FROM fact_complaint f
    JOIN top_companies t USING (company_key)
    JOIN dim_company c USING (company_key)
    JOIN dim_issue i USING (issue_key)
    GROUP BY c.company_key, c.company_name, i.issue_key, i.issue_name
)
SELECT company_name, issue_rank, issue_name, complaints, pct_of_company
FROM ranked
WHERE issue_rank <= 3
ORDER BY company_name, issue_rank, issue_name
