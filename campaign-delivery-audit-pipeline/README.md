# Ad Sales Inventory & Delivery Reconciliation Engine

A simulated **Local Inventory & Analytics** 


## The scenario

Two systems that don't perfectly agree, which is realistic for any ad-sales
org:

1. **Sales system** (`data/campaigns.csv`) — campaign/order-level data: goals,
   budgets, flight dates, advertiser, market, product, rep.
2. **Delivery/traffic system** (`data/delivery_feed.csv`) — daily impression
   delivery, generated with intentional real-world messiness:
   - ~8% of campaign-days missing from the feed entirely
   - ~5% of campaign IDs formatted inconsistently between systems (`CMP-1004`
     vs `CMP1004`)
   - ~3% duplicate rows (double-counted delivery)

The reconciliation script joins these two systems, normalizes mismatched IDs,
strips duplicates, computes pacing vs. goal, and flags anything that needs a
human look — then produces stakeholder-ready outputs automatically.

## Project structure

```
nbcu_project/
├── data/
│   ├── campaigns.csv          # sales system export
│   └── delivery_feed.csv      # delivery/traffic system export (messy, by design)
├── scripts/
│   ├── 01_generate_data.py    # synthetic data generator
│   └── 02_reconcile_and_report.py   # reconciliation + report automation
├── output/
│   ├── campaign_summary.csv   # reconciled, pacing-flagged campaign data
│   ├── discrepancy_log.csv    # audit trail of every data-quality issue caught
│   ├── pacing_report.xlsx     # formatted Excel deliverable
│   └── tableau_export.csv     # tidy extract for the Tableau dashboard
└── docs/
    ├── SOP.md                       # how to run/refresh this process
    ├── tableau_dashboard_spec.md     # dashboard + LOD/parameter design
```

## How to run it

```bash
cd scripts
python 01_generate_data.py
python 02_reconcile_and_report.py
```

Regenerating the source data and rerunning the reconciliation script produces
fresh outputs end-to-end