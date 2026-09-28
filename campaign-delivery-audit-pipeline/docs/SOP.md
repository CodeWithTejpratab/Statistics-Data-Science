# SOP: Campaign Delivery Reconciliation & Pacing Report

**Purpose:** Reconcile campaign delivery data from the ad-serving/traffic
feed against sales-system goals, flag data-quality issues, and produce a
stakeholder-ready pacing report — without manual VLOOKUP work in Excel.

**Owner:** Data Analyst, Local Inventory & Analytics
**Frequency:** Daily (or on-demand ad-hoc pull)
**Inputs:** `data/campaigns.csv`, `data/delivery_feed.csv`
**Outputs:** `output/pacing_report.xlsx`, `output/campaign_summary.csv`,
`output/discrepancy_log.csv`, `output/tableau_export.csv`

## Process steps

1. **Pull source files.** In production, these would be scheduled exports
   from the sales system and ad server (or a DOMO Dataflow output). Here they
   are represented as CSVs in `data/`.

2. **Run the reconciliation script.**
   ```bash
   python scripts/02_reconcile_and_report.py
   ```

3. **Normalize campaign IDs.** The script regexes out formatting drift
   (e.g., a missing hyphen) so a campaign isn't silently dropped from the
   join just because of a data-entry inconsistency between systems.

4. **De-duplicate delivery rows.** Exact-duplicate `(campaign_id, date,
   impressions)` rows are flagged and excluded from totals, and logged to
   `discrepancy_log.csv` under `DUPLICATE_DELIVERY_ROW` so the root cause can
   be traced back to the feed (not silently "fixed").

5. **Aggregate and compute pacing.** Delivery is summed per campaign and
   compared to `goal_impressions`. `expected_pct_elapsed` (based on flight
   dates) lets us tell "under goal because the flight isn't over yet" apart
   from "under goal and something's wrong."

6. **Apply flags:**
   - `NO DELIVERY DATA` — campaign exists in the sales system with zero
     matching delivery rows. Usually indicates a missing feed row or an ID
     mismatch the regex didn't catch — escalate to the traffic team.
   - `UNDER-DELIVERING` — pacing < 70% while >80% of the flight has elapsed.
   - `OVER-DELIVERING` — pacing > 115% (possible over-delivery makegood
     risk).
   - `ON PACE` — everything else.

7. **Review `discrepancy_log.csv` first**, before trusting the summary
   numbers. This is the data-quality gate: it's where reporting errors get
   caught before they reach a client-facing dashboard.

8. **Distribute `pacing_report.xlsx`** to stakeholders (Sales, Account
   Managers, Finance). The "By Market" tab is the roll-up view for leadership;
   the "Pacing Report" tab is the detail view for account-level follow-up.

9. **Refresh the Tableau dashboard** by pointing it at the newly generated
   `tableau_export.csv` (see `tableau_dashboard_spec.md`).

## Troubleshooting common issues

| Symptom | Likely cause | Fix |
|---|---|---|
| Campaign shows `NO DELIVERY DATA` but you know it ran | ID format mismatch not covered by the current regex | Check `campaign_id` in `delivery_feed.csv` for the affected campaign; extend `normalize_campaign_id()` if a new format appears |
| Pacing % looks inflated | Duplicate delivery rows not caught | Confirm the dedup key (`campaign_id`, `date`, `impressions_delivered`) still matches the feed's actual duplication pattern |
| Market totals don't tie to individual campaign rows | Aggregation done pre- vs. post-dedup | Always aggregate from `clean_delivery`, never the raw `delivery` frame |

## Change log
- v1.0 — Initial reconciliation + pacing report automation.
