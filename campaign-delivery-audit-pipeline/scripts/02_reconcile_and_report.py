"""
02_reconcile_and_report.py

Core analytics engine for the project. Simulates the "Local Inventory &
Analytics" workflow:

  1. Load campaign (sales system) and delivery (traffic system) data.
  2. Clean/normalize campaign_id formatting so mismatched IDs between
     systems can still be joined (a common real-world reconciliation task).
  3. Aggregate delivery to the campaign level.
  4. Reconcile against goals: compute pacing %, flag under/over-delivery,
     flag campaigns with no delivery data at all (a "reporting error").
  5. Detect duplicate delivery rows (double-counted impressions) as a
     separate data-quality flag.
  6. Export:
       - output/pacing_report.xlsx   (formatted Excel workbook w/ pivot-style
         summary, conditional flags -- mirrors "advanced Excel" deliverable)
       - output/tableau_export.csv   (tidy, Tableau-ready extract for the
         dashboard, with LOD-friendly grain: one row per campaign per day)
       - output/discrepancy_log.csv  (audit trail of every flagged issue)

Run:
    python 02_reconcile_and_report.py
"""

import pandas as pd
import numpy as np
import re

DATA_DIR = "../data"
OUT_DIR = "../output"


def normalize_campaign_id(cid: str) -> str:
    """Normalize IDs like 'CMP1004' -> 'CMP-1004' so systems with formatting
    drift still join correctly."""
    match = re.match(r"CMP-?(\d+)", str(cid))
    if match:
        return f"CMP-{match.group(1)}"
    return cid


def load_data():
    campaigns = pd.read_csv(f"{DATA_DIR}/campaigns.csv", parse_dates=["flight_start", "flight_end"])
    delivery = pd.read_csv(f"{DATA_DIR}/delivery_feed.csv", parse_dates=["date"])
    return campaigns, delivery


def flag_duplicate_delivery(delivery: pd.DataFrame) -> pd.DataFrame:
    """Identify exact duplicate (campaign_id, date, impressions) rows -- a
    common double-counting error from ad-serving feeds."""
    dup_mask = delivery.duplicated(subset=["campaign_id", "date", "impressions_delivered"], keep="first")
    delivery = delivery.copy()
    delivery["is_duplicate"] = dup_mask
    return delivery


def reconcile(campaigns: pd.DataFrame, delivery: pd.DataFrame):
    delivery = flag_duplicate_delivery(delivery)
    delivery["campaign_id_norm"] = delivery["campaign_id"].apply(normalize_campaign_id)

    # De-duplicated delivery for accurate totals
    clean_delivery = delivery[~delivery["is_duplicate"]].copy()

    agg = (
        clean_delivery.groupby("campaign_id_norm")["impressions_delivered"]
        .sum()
        .reset_index()
        .rename(columns={"campaign_id_norm": "campaign_id", "impressions_delivered": "impressions_actual"})
    )

    merged = campaigns.merge(agg, on="campaign_id", how="left")
    merged["impressions_actual"] = merged["impressions_actual"].fillna(0)
    merged["pacing_pct"] = (merged["impressions_actual"] / merged["goal_impressions"] * 100).round(1)

    days_elapsed = (pd.Timestamp.today().normalize() - merged["flight_start"]).dt.days.clip(lower=0)
    flight_length = (merged["flight_end"] - merged["flight_start"]).dt.days.replace(0, 1)
    merged["expected_pct_elapsed"] = (days_elapsed / flight_length * 100).clip(upper=100).round(1)

    def flag_row(r):
        if r["impressions_actual"] == 0:
            return "NO DELIVERY DATA"
        if r["pacing_pct"] < 70 and r["expected_pct_elapsed"] > 80:
            return "UNDER-DELIVERING"
        if r["pacing_pct"] > 115:
            return "OVER-DELIVERING"
        return "ON PACE"

    merged["flag"] = merged.apply(flag_row, axis=1)

    dup_count = delivery["is_duplicate"].sum()
    missing_camps = merged[merged["impressions_actual"] == 0][["campaign_id", "advertiser", "market"]]

    discrepancy_log = pd.concat([
        pd.DataFrame({
            "issue_type": ["DUPLICATE_DELIVERY_ROW"] * dup_count,
            "detail": delivery.loc[delivery["is_duplicate"], "campaign_id"].values,
        }),
        pd.DataFrame({
            "issue_type": ["NO_DELIVERY_DATA"] * len(missing_camps),
            "detail": missing_camps["campaign_id"].values,
        }),
    ], ignore_index=True)

    return merged, delivery, discrepancy_log


def export_excel(summary: pd.DataFrame, path: str):
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        summary.to_excel(writer, sheet_name="Pacing Report", index=False)
        workbook = writer.book
        ws = writer.sheets["Pacing Report"]

        header_fmt = workbook.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white", "border": 1})
        pct_fmt = workbook.add_format({"num_format": "0.0%"})
        red_fmt = workbook.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
        yellow_fmt = workbook.add_format({"bg_color": "#FFEB9C", "font_color": "#9C6500"})
        green_fmt = workbook.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})

        for col_num, col_name in enumerate(summary.columns):
            ws.write(0, col_num, col_name, header_fmt)
            ws.set_column(col_num, col_num, max(14, len(col_name) + 2))

        pacing_col = summary.columns.get_loc("pacing_pct")
        flag_col = summary.columns.get_loc("flag")
        n_rows = len(summary)

        # Convert pacing_pct to fraction for % formatting, then apply conditional format
        ws.conditional_format(1, flag_col, n_rows, flag_col, {
            "type": "text", "criteria": "containing", "value": "UNDER", "format": red_fmt
        })
        ws.conditional_format(1, flag_col, n_rows, flag_col, {
            "type": "text", "criteria": "containing", "value": "NO DELIVERY", "format": red_fmt
        })
        ws.conditional_format(1, flag_col, n_rows, flag_col, {
            "type": "text", "criteria": "containing", "value": "OVER", "format": yellow_fmt
        })
        ws.conditional_format(1, flag_col, n_rows, flag_col, {
            "type": "text", "criteria": "containing", "value": "ON PACE", "format": green_fmt
        })

        # Summary pivot-style tab: pacing by market
        pivot = summary.groupby("market").agg(
            campaigns=("campaign_id", "count"),
            total_goal=("goal_impressions", "sum"),
            total_actual=("impressions_actual", "sum"),
        ).reset_index()
        pivot["pacing_pct"] = (pivot["total_actual"] / pivot["total_goal"] * 100).round(1)
        pivot.to_excel(writer, sheet_name="By Market", index=False)
        ws2 = writer.sheets["By Market"]
        for col_num, col_name in enumerate(pivot.columns):
            ws2.write(0, col_num, col_name, header_fmt)
            ws2.set_column(col_num, col_num, max(14, len(col_name) + 2))


if __name__ == "__main__":
    campaigns, delivery = load_data()
    summary, delivery_flagged, discrepancy_log = reconcile(campaigns, delivery)

    summary.to_csv(f"{OUT_DIR}/campaign_summary.csv", index=False)
    discrepancy_log.to_csv(f"{OUT_DIR}/discrepancy_log.csv", index=False)
    export_excel(summary, f"{OUT_DIR}/pacing_report.xlsx")

    # Tableau-ready daily-grain extract (good for LOD expressions/parameters)
    tableau_extract = delivery_flagged[~delivery_flagged["is_duplicate"]].merge(
        campaigns[["campaign_id", "advertiser", "market", "product", "sales_rep", "goal_impressions"]],
        left_on="campaign_id_norm", right_on="campaign_id", suffixes=("", "_camp")
    )
    tableau_extract = tableau_extract[["date", "campaign_id_norm", "advertiser", "market",
                                        "product", "sales_rep", "impressions_delivered", "goal_impressions"]]
    tableau_extract = tableau_extract.rename(columns={"campaign_id_norm": "campaign_id"})
    tableau_extract.to_csv(f"{OUT_DIR}/tableau_export.csv", index=False)

    print("Reconciliation complete.")
    print(f"  Campaigns processed: {len(summary)}")
    print(f"  Flags -> {summary['flag'].value_counts().to_dict()}")
    print(f"  Discrepancies logged: {len(discrepancy_log)}")
    print(f"  Files written to {OUT_DIR}/")
