-- Active: 1791727170776@@127.0.0.1@3306
-- =====================================================================
-- AURORA MEDIA GROUP -- SQL CURRICULUM (SQLite)
-- Work top to bottom. Each query is separated by a blank line + a
-- "-- Q#" comment. Try to write your own answer BEFORE reading mine.
-- Open the DB in DB Browser for SQLite, DBeaver, or `sqlite3 aurora_media.db`.
-- =====================================================================


-- #####################################################################
-- LEVEL 1: SELECT, WHERE, ORDER BY, LIMIT, DISTINCT
-- #####################################################################

-- Q1. What does the catalog look like?
SELECT * FROM titles LIMIT 10;

-- Q2. Which Aurora originals premiered in 2025, newest first?
SELECT title_name, release_date, content_type
FROM titles
WHERE is_original = 1 AND release_date >= '2025-01-01'
ORDER BY release_date DESC;

-- Q3. What distinct acquisition channels exist?
SELECT DISTINCT acquisition_channel FROM users;

-- Q4. Highest critic-scored R-rated movies.
SELECT title_name, critic_score
FROM titles
WHERE content_type = 'movie' AND maturity_rating = 'R'
ORDER BY critic_score DESC
LIMIT 10;

-- Q5. Users missing demographic data (NULL handling).
SELECT COUNT(*) AS missing_age FROM users WHERE age_band IS NULL;


-- #####################################################################
-- LEVEL 2: AGGREGATION -- COUNT, SUM, AVG, GROUP BY, HAVING
-- #####################################################################

-- Q6. Titles per genre and content type.
SELECT g.genre_name, t.content_type, COUNT(*) AS n_titles
FROM titles t JOIN genres g ON g.genre_id = t.genre_id
GROUP BY g.genre_name, t.content_type
ORDER BY n_titles DESC;

-- Q7. Subscribers by signup year and acquisition channel.
SELECT substr(signup_date,1,4) AS signup_year, acquisition_channel, COUNT(*) AS users
FROM users
GROUP BY 1, 2
ORDER BY 1, users DESC;

-- Q8. Genres whose average critic score beats the catalog-wide average (HAVING + scalar subquery).
SELECT g.genre_name, ROUND(AVG(t.critic_score),1) AS avg_critic
FROM titles t JOIN genres g ON g.genre_id = t.genre_id
GROUP BY g.genre_name
HAVING AVG(t.critic_score) > (SELECT AVG(critic_score) FROM titles)
ORDER BY avg_critic DESC;

-- Q9. Total hours watched by device type.
SELECT device_type, ROUND(SUM(minutes_watched)/60.0, 0) AS hours_watched
FROM viewing_sessions
GROUP BY device_type
ORDER BY hours_watched DESC;


-- #####################################################################
-- LEVEL 3: JOINS (INNER, LEFT, anti-joins, self-joins)
-- #####################################################################

-- Q10. Top 10 titles by unique viewers, with genre.
SELECT t.title_name, g.genre_name, COUNT(DISTINCT vs.user_id) AS unique_viewers
FROM viewing_sessions vs
JOIN titles t ON t.title_id = vs.title_id
JOIN genres g ON g.genre_id = t.genre_id
GROUP BY t.title_id
ORDER BY unique_viewers DESC
LIMIT 10;

-- Q11. Users who paid but NEVER watched anything (anti-join with LEFT JOIN ... IS NULL).
-- Who are they, and which channels did they come from?
SELECT u.acquisition_channel, COUNT(*) AS never_watched
FROM users u
LEFT JOIN viewing_sessions vs ON vs.user_id = u.user_id
WHERE vs.session_id IS NULL
GROUP BY u.acquisition_channel
ORDER BY never_watched DESC;

-- Q12. Which actors appear in the most Aurora originals?
SELECT p.full_name, COUNT(*) AS originals
FROM title_cast tc
JOIN people p ON p.person_id = tc.person_id
JOIN titles t ON t.title_id = tc.title_id
WHERE p.primary_role = 'Actor' AND t.is_original = 1
GROUP BY p.person_id
ORDER BY originals DESC
LIMIT 10;

-- Q13. Revenue by plan and year (3-table join).
SELECT substr(p.payment_date,1,4) AS yr, pl.plan_name, ROUND(SUM(p.amount_usd),0) AS revenue
FROM payments p
JOIN subscriptions s ON s.subscription_id = p.subscription_id
JOIN plans pl ON pl.plan_id = s.plan_id
WHERE p.status = 'success'
GROUP BY 1, 2
ORDER BY 1, revenue DESC;


-- #####################################################################
-- LEVEL 4: SUBQUERIES, CTEs, CASE, DATES
-- #####################################################################

-- Q14. Users who watched more than the average user (subquery in HAVING).
SELECT user_id, SUM(minutes_watched) AS total_min
FROM viewing_sessions
GROUP BY user_id
HAVING SUM(minutes_watched) > (
    SELECT AVG(t) FROM (SELECT SUM(minutes_watched) AS t FROM viewing_sessions GROUP BY user_id)
)
ORDER BY total_min DESC
LIMIT 10;

-- Q15. Bucket users into engagement tiers with CASE + CTE.
WITH usage AS (
    SELECT user_id, SUM(minutes_watched)/60.0 AS hours
    FROM viewing_sessions GROUP BY user_id
)
SELECT CASE WHEN hours >= 100 THEN 'Power'
            WHEN hours >= 30  THEN 'Regular'
            ELSE 'Light' END AS tier,
       COUNT(*) AS users,
       ROUND(AVG(hours),1) AS avg_hours
FROM usage
GROUP BY tier
ORDER BY avg_hours DESC;

-- Q16. Average days from signup to first viewing session.
WITH first_view AS (
    SELECT user_id, MIN(date(session_start)) AS first_day
    FROM viewing_sessions GROUP BY user_id
)
SELECT ROUND(AVG(julianday(f.first_day) - julianday(u.signup_date)), 1) AS avg_days_to_first_view
FROM users u JOIN first_view f ON f.user_id = u.user_id;

-- Q17. Premiere-week performance for originals: sessions in the first 7 days after release.
SELECT t.title_name, t.release_date, COUNT(*) AS first_week_sessions
FROM titles t
JOIN viewing_sessions vs ON vs.title_id = t.title_id
WHERE t.is_original = 1
  AND date(vs.session_start) BETWEEN t.release_date AND date(t.release_date, '+6 days')
GROUP BY t.title_id
ORDER BY first_week_sessions DESC
LIMIT 10;


-- #####################################################################
-- LEVEL 5: WINDOW FUNCTIONS (the interview favorite)
-- #####################################################################

-- Q18. Top 3 titles within each genre by hours watched.
-- (SQLite has no QUALIFY, so filter the window result in an outer query.)
WITH h AS (
    SELECT t.title_id, t.title_name, g.genre_name, SUM(vs.minutes_watched)/60.0 AS hours
    FROM viewing_sessions vs
    JOIN titles t ON t.title_id = vs.title_id
    JOIN genres g ON g.genre_id = t.genre_id
    GROUP BY t.title_id
), ranked AS (
    SELECT genre_name, title_name, ROUND(hours,0) AS hours,
           RANK() OVER (PARTITION BY genre_name ORDER BY hours DESC) AS rnk
    FROM h
)
SELECT * FROM ranked WHERE rnk <= 3 ORDER BY genre_name, rnk;

-- Q19. Month-over-month revenue growth with LAG().
WITH m AS (
    SELECT substr(payment_date,1,7) AS month, SUM(amount_usd) AS revenue
    FROM payments WHERE status = 'success' GROUP BY 1
)
SELECT month, ROUND(revenue,0) AS revenue,
       ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month)) / LAG(revenue) OVER (ORDER BY month), 1) AS mom_pct
FROM m
ORDER BY month;

-- Q20. Running total of signups and a 3-month moving average.
WITH s AS (
    SELECT substr(signup_date,1,7) AS month, COUNT(*) AS signups
    FROM users GROUP BY 1
)
SELECT month, signups,
       SUM(signups) OVER (ORDER BY month) AS cumulative_signups,
       ROUND(AVG(signups) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1) AS moving_avg_3m
FROM s
ORDER BY month;

-- Q21. Binge detection: users with 3+ episodes of the same series in one day.
SELECT user_id, title_id, date(session_start) AS day, COUNT(*) AS eps
FROM viewing_sessions
WHERE episode_id IS NOT NULL
GROUP BY user_id, title_id, date(session_start)
HAVING COUNT(*) >= 3
ORDER BY eps DESC
LIMIT 10;

-- Q22. Each user's most-watched genre (ROW_NUMBER + top-1 per group).
WITH g AS (
    SELECT vs.user_id, t.genre_id, SUM(vs.minutes_watched) AS mins
    FROM viewing_sessions vs JOIN titles t ON t.title_id = vs.title_id
    GROUP BY vs.user_id, t.genre_id
), r AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY mins DESC) AS rn FROM g
)
SELECT ge.genre_name, COUNT(*) AS users_with_this_top_genre
FROM r JOIN genres ge ON ge.genre_id = r.genre_id
WHERE rn = 1
GROUP BY ge.genre_name
ORDER BY users_with_this_top_genre DESC;


-- #####################################################################
-- LEVEL 6: BUSINESS ANALYTICS -- the questions NBCU-style teams ask
-- #####################################################################

-- Q23. MRR (monthly recurring revenue) by month and plan.
SELECT month, plan_name, revenue_usd FROM v_monthly_revenue ORDER BY month, plan_name;

-- Q24. Active subscribers at the end of each month (date-spine join on dim_date).
WITH month_ends AS (
    SELECT substr(date,1,7) AS month, MAX(date) AS month_end FROM dim_date GROUP BY 1
)
SELECT me.month, COUNT(*) AS active_subs
FROM month_ends me
JOIN subscriptions s
  ON s.start_date <= me.month_end
 AND (s.end_date IS NULL OR s.end_date >= me.month_end)
GROUP BY me.month
ORDER BY me.month;

-- Q25. Monthly churn: users whose last subscription ended that month and did not renew.
WITH ends AS (
    SELECT user_id, MAX(end_date) AS last_end
    FROM subscriptions WHERE end_reason != 'plan_change' GROUP BY user_id
)
SELECT substr(last_end,1,7) AS month, COUNT(*) AS churned_users
FROM ends GROUP BY 1 ORDER BY 1;

-- Q26. Churn reasons by plan.
SELECT pl.plan_name, s.end_reason, COUNT(*) AS n,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY pl.plan_name), 1) AS pct_of_plan
FROM subscriptions s JOIN plans pl ON pl.plan_id = s.plan_id
WHERE s.status = 'ended' AND s.end_reason != 'plan_change'
GROUP BY pl.plan_name, s.end_reason
ORDER BY pl.plan_name, n DESC;

-- Q27. Cohort retention: share of each signup-month cohort still paying N months later.
WITH cohort AS (
    SELECT user_id, substr(signup_date,1,7) AS cohort_month FROM users
), paid AS (
    SELECT DISTINCT user_id, substr(payment_date,1,7) AS pay_month
    FROM payments WHERE status = 'success'
), j AS (
    SELECT c.cohort_month,
           (CAST(substr(p.pay_month,1,4) AS INT) - CAST(substr(c.cohort_month,1,4) AS INT)) * 12
         + (CAST(substr(p.pay_month,6,2) AS INT) - CAST(substr(c.cohort_month,6,2) AS INT)) AS month_n,
           c.user_id
    FROM cohort c JOIN paid p ON p.user_id = c.user_id
)
SELECT cohort_month,
       COUNT(DISTINCT CASE WHEN month_n = 0  THEN user_id END) AS m0,
       ROUND(100.0 * COUNT(DISTINCT CASE WHEN month_n = 3  THEN user_id END) / COUNT(DISTINCT CASE WHEN month_n = 0 THEN user_id END), 1) AS m3_pct,
       ROUND(100.0 * COUNT(DISTINCT CASE WHEN month_n = 6  THEN user_id END) / COUNT(DISTINCT CASE WHEN month_n = 0 THEN user_id END), 1) AS m6_pct,
       ROUND(100.0 * COUNT(DISTINCT CASE WHEN month_n = 12 THEN user_id END) / COUNT(DISTINCT CASE WHEN month_n = 0 THEN user_id END), 1) AS m12_pct
FROM j
GROUP BY cohort_month
HAVING m0 >= 30
ORDER BY cohort_month;

-- Q28. CAC by channel and year (signups joined to marketing spend).
WITH su AS (
    SELECT substr(signup_date,1,4) AS yr, acquisition_channel AS channel, COUNT(*) AS signups
    FROM users GROUP BY 1, 2
), sp AS (
    SELECT substr(month,1,4) AS yr, channel, SUM(spend_usd) AS spend
    FROM marketing_spend GROUP BY 1, 2
)
SELECT su.yr, su.channel, su.signups, ROUND(sp.spend,0) AS spend,
       ROUND(sp.spend / su.signups, 2) AS cac
FROM su JOIN sp ON sp.yr = su.yr AND sp.channel = su.channel
ORDER BY su.yr, cac DESC;

-- Q29. Customer lifetime value proxy: total revenue per user by acquisition channel.
SELECT u.acquisition_channel,
       COUNT(DISTINCT u.user_id) AS users,
       ROUND(SUM(p.amount_usd) / COUNT(DISTINCT u.user_id), 2) AS revenue_per_user
FROM users u JOIN payments p ON p.user_id = u.user_id AND p.status = 'success'
GROUP BY u.acquisition_channel
ORDER BY revenue_per_user DESC;

-- Q30. Did the July 2024 price increase hurt? Monthly cancellations around it, by plan.
SELECT substr(end_date,1,7) AS month, plan_id, COUNT(*) AS cancellations
FROM subscriptions
WHERE end_reason NOT IN ('plan_change') AND end_date BETWEEN '2024-03-01' AND '2024-12-31'
GROUP BY 1, 2
ORDER BY 2, 1;

-- Q31. Content ROI: hours watched per $1M of production budget, originals only.
SELECT t.title_name, t.production_budget_usd,
       ROUND(SUM(vs.minutes_watched)/60.0, 0) AS hours,
       ROUND((SUM(vs.minutes_watched)/60.0) / (t.production_budget_usd / 1e6), 0) AS hours_per_1m
FROM titles t JOIN viewing_sessions vs ON vs.title_id = t.title_id
WHERE t.is_original = 1
GROUP BY t.title_id
ORDER BY hours_per_1m DESC
LIMIT 10;

-- Q32. Does critic score predict viewing? Average completion rate by critic-score band.
SELECT CASE WHEN critic_score >= 80 THEN '80+'
            WHEN critic_score >= 65 THEN '65-79'
            WHEN critic_score >= 50 THEN '50-64'
            ELSE '<50' END AS critic_band,
       COUNT(DISTINCT t.title_id) AS titles,
       ROUND(AVG(vs.completed), 3) AS completion_rate
FROM titles t JOIN viewing_sessions vs ON vs.title_id = t.title_id
GROUP BY critic_band
ORDER BY critic_band DESC;

-- Q33. Ad revenue by industry and quarter.
SELECT a.industry,
       substr(d.perf_date,1,4) || '-Q' || ((CAST(substr(d.perf_date,6,2) AS INT) - 1) / 3 + 1) AS quarter,
       ROUND(SUM(d.revenue_usd), 0) AS revenue,
       ROUND(1000.0 * SUM(d.revenue_usd) / SUM(d.impressions), 2) AS effective_cpm
FROM ad_daily_performance d
JOIN ad_campaigns c ON c.campaign_id = d.campaign_id
JOIN advertisers a ON a.advertiser_id = c.advertiser_id
GROUP BY 1, 2
ORDER BY 2, revenue DESC;

-- Q34. Best-performing campaigns by CTR (min. 1M impressions).
SELECT campaign_name, advertiser_name, industry, impressions, ctr
FROM v_ad_campaign_summary
WHERE impressions >= 1000000
ORDER BY ctr DESC
LIMIT 10;

-- Q35. Linear TV: average prime-time household rating by network and year (decline trend).
SELECT n.network_name, substr(l.air_datetime,1,4) AS yr,
       ROUND(AVG(l.household_rating), 2) AS avg_hh_rating,
       ROUND(AVG(l.demo_18_49_rating), 2) AS avg_demo
FROM linear_airings l JOIN networks n ON n.network_id = l.network_id
WHERE l.daypart = 'Prime'
GROUP BY 1, 2
ORDER BY 1, 2;

-- Q36. Cross-platform: do titles that rate well on linear also stream well?
WITH lin AS (
    SELECT title_id, AVG(household_rating) AS avg_linear_rating
    FROM linear_airings WHERE title_id IS NOT NULL GROUP BY title_id
)
SELECT t.title_name, ROUND(lin.avg_linear_rating, 2) AS linear_hh,
       e.unique_viewers AS streaming_viewers
FROM lin
JOIN titles t ON t.title_id = lin.title_id
JOIN v_title_engagement e ON e.title_id = t.title_id
ORDER BY streaming_viewers DESC
LIMIT 15;
