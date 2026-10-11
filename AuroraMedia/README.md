# Aurora Media Group: SQLite Analytics Database

A synthetic, portfolio database that mirrors how a media conglomerate actually runs: **streaming + advertising + linear TV**. Built to (1) learn SQL properly and (2) power analytics / data science projects and dashboards.

**All data is synthetic. No real people, titles, or IP.**  ("synthetic dataset modeled on a streaming + linear media business").

## Files
| File | Purpose |
|---|---|
| `aurora_media.db` | The database (~70 MB, ready to query) |
| `build_db.py` | Generator. Edit the knobs at the top (`N_USERS`, `N_TITLES`, date range, `SEED`) and re-run to rebuild |
| `sql_curriculum.sql` | 36 queries in 6 levels, from SELECT to cohort retention. All tested |

Open with **DB Browser for SQLite** (easiest), **DBeaver**, VS Code's SQLite extension, or `sqlite3 aurora_media.db`. Python: `pd.read_sql("SELECT ...", sqlite3.connect("aurora_media.db"))`.

## What's inside (~720K rows)
```
STREAMING                                   ADVERTISING                LINEAR TV
genres ─< titles ─< episodes                advertisers ─< ad_campaigns   networks ─< linear_airings >─ titles
           │  └─< title_cast >─ people                      └─< ad_daily_performance >─ titles
           │
users ─< subscriptions >─ plans ─< plan_price_history
  │            └─< payments
  ├─< viewing_sessions >─ titles / episodes      marketing_spend (month x channel, for CAC)
  └─< user_ratings >─ titles                     dim_date (date spine for time-series joins)

Views: v_monthly_revenue, v_title_engagement, v_ad_campaign_summary
```
| Table | Rows | Notes |
|---|---|---|
| viewing_sessions | ~520K | the big fact table; has device, minutes, completion, ads shown |
| payments | ~87K | includes failed payments |
| linear_airings | 62K | Nielsen-style household / 18-49 ratings by daypart |
| ad_daily_performance | ~36K | impressions, clicks, revenue by campaign x title x day |
| subscriptions | ~7.6K | one row per plan period (supports upgrades, churn, resubscribe) |
| users | 6K | 2022-01 to 2026-09 signups |

Dates are stored as ISO text (`'2025-03-14'`), so use `date()`, `substr()`, `julianday()`.

## Patterns planted on purpose
- **Churn drivers:** highest in months 1-3; bundle-partner users churn least, paid-social most; ad tier churns more than Premium Plus; high-engagement users churn less
- **Price increases:** July 2024 (Basic + Premium) and June 2025 (Premium Plus) cause a churn bump
- **Premiere spikes:** big originals drive both signups and viewing, decaying over ~45 days
- **Seasonality:** winter/holiday up, summer down
- **Binge behavior:** originals release weekly; licensed seasons drop all at once; sessions chain episodes
- **Linear decline:** household ratings fall ~8%/yr; sports spike on weekends; news peaks early fringe
- **Messiness:** some NULL states and age bands, failed payments, users who never watch

## Learning path
1. Do `sql_curriculum.sql` top to bottom. Write your own answer first, then compare.
2. Rewrite 5 queries three ways (JOIN vs subquery vs CTE) and compare with `EXPLAIN QUERY PLAN`.
3. Add and drop an index on `viewing_sessions` and time a slow query. Learn why it matters.
4. Write your own views for your dashboard layer (`CREATE VIEW ...`).

## Portfolio projects
**Analytics / dashboard (Tableau Public, Power BI, or Streamlit)**
1. **Streaming executive dashboard:** MRR, active subs, churn, ARPU, cohort retention heatmap
2. **Content performance:** premiere-week curves, completion rate, hours per $ of budget, genre mix
3. **Ad sales dashboard:** revenue and CPM by industry/quarter, campaign pacing vs. budget, CTR leaders
4. **Linear vs streaming:** ratings decline by network and where the audience went

**Data science**
5. **Churn prediction:** features from sessions/plan/channel, logistic regression / gradient boosting, explain with SHAP, then size the revenue saved by a retention offer
6. **Price-increase impact:** difference-in-differences using the plan that was *not* raised in June 2025
7. **Premiere forecasting:** predict first-14-day viewing from genre, cast, budget, critic score
8. **Recommender:** item-item similarity from `viewing_sessions` and `user_ratings`; evaluate with a holdout
9. **Ad revenue forecast:** time-series on `ad_daily_performance` with seasonality

For each: state the business question, show the SQL, show the chart, end with a **recommendation** ("shift $X from paid social to bundle partners"). Recommendations are what separate analysts from chart-makers.

## Rebuilding
`python3 build_db.py` (needs `numpy`). Same `SEED` gives identical data; change it for a different universe.
