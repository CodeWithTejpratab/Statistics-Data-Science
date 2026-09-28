"""
01_generate_data.py

Generates synthetic ad-sales data simulating an NBCU-style Local Inventory &
Analytics environment:
  - campaigns.csv:        master campaign/order data (sales system)
  - delivery_feed.csv:    daily impression delivery data (ad-serving/traffic
                          system) -- deliberately contains gaps, duplicates,
                          and mismatched IDs vs. the sales system to simulate
                          real-world reconciliation problems.

Run:
    python 01_generate_data.py
Outputs to ../data/
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

random.seed(42)
np.random.seed(42)

OUT_DIR = "../data"

MARKETS = ["New York", "Los Angeles", "Chicago", "Philadelphia", "Dallas",
           "Washington DC", "San Francisco", "Boston", "Atlanta", "Miami"]

ADVERTISERS = ["Acme Auto Group", "Coastal Bank", "Peak Insurance",
               "BrightSmile Dental", "Summit Law Partners", "UrbanEats Delivery",
               "Northline Furniture", "Vantage Health System", "Metro Realty",
               "Evergreen Energy Co"]

PRODUCTS = ["Linear Spot", "Peacock Pre-roll", "Peacock Mid-roll", "OTT Display",
            "Local Digital Display", "CTV Video"]

SALES_REPS = ["J. Alvarez", "K. Chen", "M. Douglas", "R. Foster", "S. Patel"]

NUM_CAMPAIGNS = 120
START_DATE = datetime(2026, 1, 5)

def make_campaigns():
    rows = []
    for i in range(1, NUM_CAMPAIGNS + 1):
        campaign_id = f"CMP-{1000 + i}"
        advertiser = random.choice(ADVERTISERS)
        market = random.choice(MARKETS)
        product = random.choice(PRODUCTS)
        rep = random.choice(SALES_REPS)
        flight_start = START_DATE + timedelta(days=random.randint(0, 200))
        flight_length = random.choice([7, 14, 21, 28])
        flight_end = flight_start + timedelta(days=flight_length)
        goal_impressions = random.choice([50_000, 100_000, 150_000, 250_000,
                                           500_000, 750_000])
        budget = round(goal_impressions * random.uniform(8, 22) / 1000, 2)  # CPM-based
        rows.append({
            "campaign_id": campaign_id,
            "advertiser": advertiser,
            "market": market,
            "product": product,
            "sales_rep": rep,
            "flight_start": flight_start.date().isoformat(),
            "flight_end": flight_end.date().isoformat(),
            "goal_impressions": goal_impressions,
            "budget": budget,
        })
    return pd.DataFrame(rows)


def make_delivery_feed(campaigns: pd.DataFrame):
    """
    Simulate a daily delivery feed from an ad-serving/traffic system.
    Intentionally introduces real-world data problems:
      - ~8% of campaigns missing entirely some days (under-delivery)
      - ~5% of campaign_ids have a typo/format mismatch vs. sales system
      - ~3% duplicate rows (double-counted delivery)
      - random day-to-day variance in delivery pace
    """
    rows = []
    for _, camp in campaigns.iterrows():
        start = datetime.fromisoformat(camp["flight_start"])
        end = datetime.fromisoformat(camp["flight_end"])
        days = (end - start).days
        goal = camp["goal_impressions"]

        # simulate a pacing curve with noise; some campaigns under-deliver,
        # some over-deliver slightly
        pace_factor = np.random.normal(loc=0.94, scale=0.12)
        total_to_deliver = max(0, goal * pace_factor)
        daily_avg = total_to_deliver / max(days, 1)

        cid = camp["campaign_id"]
        # introduce ID mismatch for ~5% of campaigns (simulates manual entry
        # error between systems)
        if random.random() < 0.05:
            cid = cid.replace("CMP-", "CMP")  # dropped hyphen

        for d in range(days):
            date = start + timedelta(days=d)
            # ~8% chance a day's delivery is simply missing from the feed
            if random.random() < 0.08:
                continue
            daily_impressions = max(0, int(np.random.normal(daily_avg, daily_avg * 0.25)))
            rows.append({
                "campaign_id": cid,
                "date": date.date().isoformat(),
                "impressions_delivered": daily_impressions,
            })
            # ~3% chance this row gets accidentally duplicated in the feed
            if random.random() < 0.03:
                rows.append({
                    "campaign_id": cid,
                    "date": date.date().isoformat(),
                    "impressions_delivered": daily_impressions,
                })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    campaigns = make_campaigns()
    delivery = make_delivery_feed(campaigns)

    campaigns.to_csv(f"{OUT_DIR}/campaigns.csv", index=False)
    delivery.to_csv(f"{OUT_DIR}/delivery_feed.csv", index=False)

    print(f"campaigns.csv: {len(campaigns)} rows")
    print(f"delivery_feed.csv: {len(delivery)} rows")
