# DOMO Equivalent Mapping

This project is built in pandas so it's runnable and reviewable outside a
paid DOMO instance, but every step maps directly to a DOMO concept called
out in the job posting. This doc is meant to show that translation
explicitly (and to talk through in an interview).

| Step in `02_reconcile_and_report.py` | DOMO equivalent |
|---|---|
| Loading `campaigns.csv` / `delivery_feed.csv` | **Dataflows** pulling in the sales-system and ad-server **Datasets** |
| `normalize_campaign_id()` regex cleanup | A **Magic ETL** "Transform Column" tile (formula/regex) to standardize the join key before merging |
| Merging campaigns + aggregated delivery | Magic ETL **Join** tile (campaign_id as the join key) |
| `flag_duplicate_delivery()` | Magic ETL **Rank & Window** tile (or a dedup tile) upstream of aggregation |
| `pacing_pct`, `expected_pct_elapsed`, `flag_row()` | **Beast Mode** calculated fields inside a DOMO card (equivalent to a calculated column at query time rather than ETL time) |
| `discrepancy_log.csv` audit trail | A separate DOMO **View** built specifically to expose data-quality exceptions to the ops/traffic team, kept apart from the client-facing card |
| `pacing_report.xlsx` distribution | A DOMO **scheduled report/card export** to stakeholders |
| Re-running the whole script to refresh | A DOMO Dataflow **scheduled trigger** |

The key point demonstrated here: the *logic* (normalize → join → dedup →
aggregate → flag → export) is tool-agnostic. Whether it's expressed as
pandas, Magic ETL tiles, or Beast Mode formulas, the reconciliation problem
and the solution shape are the same — which is the actual skill being
tested for, not the specific tool syntax.
