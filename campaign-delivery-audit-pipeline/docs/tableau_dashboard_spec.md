# Tableau Dashboard Spec — Campaign Delivery Pacing

**Data source:** `output/tableau_export.csv`
Grain: one row per `campaign_id` per `date`, with `impressions_delivered` and
`goal_impressions` (goal repeats across every day of a campaign — required
for the LOD expression below).

## Calculated fields

**1. Pacing % (LOD — fixed at campaign level)**
Regardless of any date filter applied to the view, this always shows total
delivery-to-date over the *full* campaign goal, not just the visible date
range:

```
{ FIXED [Campaign Id] : SUM([Impressions Delivered]) } / 
{ FIXED [Campaign Id] : MAX([Goal Impressions]) }
```

**2. Delivery Status (calculated field)**
```
IF [Pacing %] < 0.70 THEN "Under-Delivering"
ELSEIF [Pacing %] > 1.15 THEN "Over-Delivering"
ELSE "On Pace"
END
```

**3. Market Share of Delivery (LOD — % of total regardless of filter)**
```
SUM([Impressions Delivered]) / 
{ FIXED : SUM([Impressions Delivered]) }
```
Useful for a "market mix" view that doesn't collapse to 100% when a single
market is selected.

## Parameters

- **Market Selector** (string parameter, values pulled from `[Market]`,
  includes an "All Markets" option) — drives a parameter action that filters
  the main view while keeping the KPI tile on the FIXED LOD (so the KPI tile
  always shows the true total, while the detail table filters).
- **Pacing Threshold Sensitivity** (float parameter, default 0.70) — lets a
  sales manager tighten/loosen the under-delivery threshold without editing
  the calculated field, by swapping the hardcoded `0.70` in *Delivery Status*
  for `[Pacing Threshold Sensitivity]`.

## Suggested sheets

1. **KPI tile row** — Total Goal, Total Delivered, Overall Pacing % (all
   FIXED LOD so they never change when the view is filtered/drilled).
2. **Pacing by Market** — bar chart, colored by `Delivery Status`.
3. **Pacing Trend** — line chart of cumulative delivery vs. a straight-line
   pacing goal, one line per campaign (filterable by Market parameter).
4. **Campaign Detail table** — sortable table with `Delivery Status` as a
   colored indicator column, filtered by the Market Selector parameter.

## Dashboard interactivity

- Parameter action: clicking a market bar in "Pacing by Market" sets the
  Market Selector parameter, updating the detail table below.
- Highlight action: hovering a campaign in the trend chart highlights the
  matching row in the detail table.
