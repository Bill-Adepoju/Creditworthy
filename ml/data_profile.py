"""
T3: Dataset ingestion and integrity report
Profiles the Zindi SuperLender dataset for the dissertation.
"""
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"

def main():
    print("=== T3: Dataset Profiling ===\n")

    # Load datasets
    print("Loading datasets...")
    demographics = pd.read_csv(DATA_DIR / "traindemographics.csv")
    perf = pd.read_csv(DATA_DIR / "trainperf.csv")
    prevloans = pd.read_csv(DATA_DIR / "trainprevloans.csv")

    print(f"  traindemographics: {len(demographics):,} rows, {len(demographics.columns)} cols")
    print(f"  trainperf:         {len(perf):,} rows, {len(perf.columns)} cols")
    print(f"  trainprevloans:    {len(prevloans):,} rows, {len(prevloans.columns)} cols")

    # Column inventories
    print("\n=== Column Inventories ===")
    print(f"demographics: {list(demographics.columns)}")
    print(f"perf:         {list(perf.columns)}")
    print(f"prevloans:    {list(prevloans.columns)}")

    # Join coverage analysis
    print("\n=== Join Coverage ===")
    demo_ids = set(demographics["customerid"])
    perf_ids = set(perf["customerid"])
    prev_ids = set(prevloans["customerid"])

    all_three = demo_ids & perf_ids & prev_ids
    demo_and_perf = demo_ids & perf_ids

    print(f"Unique customers in demographics: {len(demo_ids):,}")
    print(f"Unique customers in perf:         {len(perf_ids):,}")
    print(f"Unique customers in prevloans:    {len(prev_ids):,}")
    print(f"Customers in ALL THREE tables:    {len(all_three):,}")
    print(f"Customers in demo + perf only:    {len(demo_and_perf):,}")

    # Check: customers in perf but not in prevloans (first-time borrowers?)
    perf_not_prev = perf_ids - prev_ids
    print(f"Customers in perf but NOT in prevloans (first-time?): {len(perf_not_prev):,}")

    # Class balance
    print("\n=== Class Balance (good_bad_flag) ===")
    class_counts = perf["good_bad_flag"].value_counts()
    print(class_counts)
    total = len(perf)
    bad_rate = (perf["good_bad_flag"] == "Bad").sum() / total
    print(f"Default rate (Bad): {bad_rate:.2%}")

    # Missingness
    print("\n=== Missingness ===")

    def missingness_report(df, name):
        missing = df.isnull().sum()
        missing_pct = (missing / len(df) * 100).round(2)
        report = pd.DataFrame({
            "missing_count": missing,
            "missing_pct": missing_pct
        })
        report = report[report["missing_count"] > 0].sort_values("missing_pct", ascending=False)
        return report

    print("\ndemographics:")
    demo_missing = missingness_report(demographics, "demographics")
    if len(demo_missing) > 0:
        print(demo_missing.to_string())
    else:
        print("  No missing values")

    print("\nperf:")
    perf_missing = missingness_report(perf, "perf")
    if len(perf_missing) > 0:
        print(perf_missing.to_string())
    else:
        print("  No missing values")

    print("\nprevloans:")
    prev_missing = missingness_report(prevloans, "prevloans")
    if len(prev_missing) > 0:
        print(prev_missing.to_string())
    else:
        print("  No missing values")

    # CRITICAL: Check for date fields in prevloans
    print("\n=== CRITICAL: Date Fields for Regularity Features ===")
    required_date_fields = [
        "approveddate", "creationdate", "closeddate",
        "firstduedate", "firstrepaiddate"
    ]
    prevloans_cols_lower = [c.lower() for c in prevloans.columns]

    found_dates = []
    missing_dates = []
    for field in required_date_fields:
        if field in prevloans_cols_lower:
            actual_col = prevloans.columns[prevloans_cols_lower.index(field)]
            found_dates.append(actual_col)
            # Sample values
            sample = prevloans[actual_col].dropna().head(3).tolist()
            print(f"  [OK] {actual_col}: {sample}")
        else:
            missing_dates.append(field)
            print(f"  [MISSING] {field}: NOT FOUND")

    # Check for alternative date column names
    print("\nAll columns in prevloans:")
    for col in prevloans.columns:
        dtype = prevloans[col].dtype
        sample = prevloans[col].dropna().head(2).tolist()
        print(f"  {col} ({dtype}): {sample}")

    # Build results JSON
    results = {
        "timestamp": datetime.now().isoformat(),
        "files": {
            "traindemographics": {
                "rows": len(demographics),
                "columns": len(demographics.columns),
                "column_names": list(demographics.columns)
            },
            "trainperf": {
                "rows": len(perf),
                "columns": len(perf.columns),
                "column_names": list(perf.columns)
            },
            "trainprevloans": {
                "rows": len(prevloans),
                "columns": len(prevloans.columns),
                "column_names": list(prevloans.columns)
            }
        },
        "join_coverage": {
            "unique_customers_demographics": len(demo_ids),
            "unique_customers_perf": len(perf_ids),
            "unique_customers_prevloans": len(prev_ids),
            "customers_in_all_three": len(all_three),
            "customers_in_demo_and_perf": len(demo_and_perf),
            "first_time_borrowers": len(perf_not_prev)
        },
        "class_balance": {
            "total": total,
            "good": int((perf["good_bad_flag"] == "Good").sum()),
            "bad": int((perf["good_bad_flag"] == "Bad").sum()),
            "default_rate": round(bad_rate, 4)
        },
        "missingness": {
            "demographics": demo_missing.to_dict() if len(demo_missing) > 0 else {},
            "perf": perf_missing.to_dict() if len(perf_missing) > 0 else {},
            "prevloans": prev_missing.to_dict() if len(prev_missing) > 0 else {}
        },
        "date_fields": {
            "required": required_date_fields,
            "found": found_dates,
            "missing": missing_dates,
            "usable_for_regularity_features": len(missing_dates) == 0
        }
    }

    # Write results
    RESULTS_DIR.mkdir(exist_ok=True)
    with open(RESULTS_DIR / "data_profile.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults written to {RESULTS_DIR / 'data_profile.json'}")

    # Summary
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    print(f"Total customers with labels: {len(perf_ids):,}")
    print(f"Default rate: {bad_rate:.2%}")
    print(f"Customers with loan history: {len(all_three):,} ({len(all_three)/len(perf_ids)*100:.1f}%)")
    print(f"First-time borrowers (no history): {len(perf_not_prev):,} ({len(perf_not_prev)/len(perf_ids)*100:.1f}%)")

    if missing_dates:
        print(f"\n[!] ESCALATE: Missing date fields: {missing_dates}")
        print("    Feature engineering strategy depends on these fields!")
    else:
        print(f"\n[OK] All required date fields present for regularity features")

    return results

if __name__ == "__main__":
    main()
