"""
Cleans the raw fermentation dataset (1000 Trichoderma cellulase production
runs). This is real, messy data -- every cleaning decision below is
documented so it can be defended in an interview, not just applied silently.

Data quality issues found on inspection:
  1. Duplicate Run_ID (TRICH_15 appears twice, with different process
     conditions) -- a real ID-collision bug in the source system.
  2. 144/1000 rows (14.4%) have negative Max FPU/ml. Enzyme activity
     (FPU/mL) cannot physically be negative -- this is assay measurement
     noise around a true value near zero (blank-subtracted colorimetric
     assays commonly do this for low/failed runs). Decision: floor these
     at 0 for yield-magnitude analysis, but keep a flag column so the
     "failed run" information isn't silently discarded.
  3. Notes/yield-category column has inconsistent text: "Low yeild",
     "Medium Yeild", "High Yeild", "Medium yeild" -- misspelling +
     inconsistent casing. Standardized to a clean categorical.
  4. Contamination (Y/N) converted to boolean.
"""

import os
import pandas as pd

BASE_DIR = os.path.dirname(__file__)
RAW_PATH = os.path.join(BASE_DIR, "data", "raw_data.xlsx")
CLEAN_PATH = os.path.join(BASE_DIR, "data", "clean_runs.csv")

# canonical column names -- shorter, snake_case, unit-explicit
COLUMN_MAP = {
    "Run_ID": "run_id",
    "Avg_temp": "avg_temp_C",
    "Avg_pH": "avg_ph",
    "Min_DO %": "min_do_pct",
    "Inoculum size (mL)": "inoculum_size_mL",
    "Max_RPM": "max_rpm",
    "Total feed of Lactose (mL)": "total_lactose_feed_mL",
    "Total culture duration (days)": "culture_duration_days",
    "Contamination (Y/N)": "contaminated",
    "Total media volume (mL)": "total_media_volume_mL",
    "Max FPU/ml": "max_fpu_ml",
    "Notes": "yield_category_raw",
}

NOTES_MAP = {
    "low yeild": "Low",
    "medium yeild": "Medium",
    "high yeild": "High",
}


def clean():
    df = pd.read_excel(RAW_PATH)
    df = df.rename(columns=COLUMN_MAP)

    issues = {}

    # --- 1. duplicate run_id ---
    dupe_mask = df["run_id"].duplicated(keep=False)
    issues["duplicate_run_id_rows"] = int(dupe_mask.sum())
    # disambiguate rather than drop -- both rows are real observations,
    # they just collided on ID generation upstream
    dup_counter = {}
    new_ids = []
    for rid in df["run_id"]:
        if dupe_mask[df["run_id"] == rid].sum() > 1:
            dup_counter[rid] = dup_counter.get(rid, 0) + 1
            new_ids.append(f"{rid}_dup{dup_counter[rid]}")
        else:
            new_ids.append(rid)
    df["run_id"] = new_ids

    # --- 2. negative yield values ---
    neg_mask = df["max_fpu_ml"] < 0
    issues["negative_fpu_rows"] = int(neg_mask.sum())
    df["fpu_measurement_flag"] = neg_mask.map({True: "negative_floored_to_zero", False: "ok"})
    df["max_fpu_ml_raw"] = df["max_fpu_ml"]
    df["max_fpu_ml"] = df["max_fpu_ml"].clip(lower=0)

    # --- 3. standardize yield category text ---
    df["yield_category"] = (
        df["yield_category_raw"].str.strip().str.lower().map(NOTES_MAP)
    )
    unmapped = df["yield_category"].isna().sum()
    issues["unmapped_yield_category_rows"] = int(unmapped)
    df = df.drop(columns=["yield_category_raw"])

    # --- 4. contamination to boolean ---
    df["contaminated"] = df["contaminated"].str.strip().str.upper().map({"Y": True, "N": False})
    issues["contaminated_runs"] = int(df["contaminated"].sum())
    issues["total_rows"] = len(df)

    df.to_csv(CLEAN_PATH, index=False)
    return df, issues


if __name__ == "__main__":
    df, issues = clean()
    print("Cleaning summary:")
    for k, v in issues.items():
        print(f"  {k}: {v}")
    print(f"\nSaved cleaned data to {CLEAN_PATH}")
    print(df.head())
