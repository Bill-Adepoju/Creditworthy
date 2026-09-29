"""
T4: Feature engineering — regularity over magnitude
Builds three feature sets to test the seminar's central claim:
- FS_magnitude: amount-based features only
- FS_regularity: consistency/timing features only
- FS_full: both

Per CLAUDE.md: The design commitment is that *consistency* predicts better
than *size* in informal economies. This module lets us test that empirically.
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"


def load_data():
    """Load all three datasets."""
    demographics = pd.read_csv(DATA_DIR / "traindemographics.csv")
    perf = pd.read_csv(DATA_DIR / "trainperf.csv")
    prevloans = pd.read_csv(DATA_DIR / "trainprevloans.csv")

    # Parse dates
    date_cols_prev = ["approveddate", "creationdate", "closeddate", "firstduedate", "firstrepaiddate"]
    for col in date_cols_prev:
        prevloans[col] = pd.to_datetime(prevloans[col], errors="coerce")

    date_cols_perf = ["approveddate", "creationdate"]
    for col in date_cols_perf:
        perf[col] = pd.to_datetime(perf[col], errors="coerce")

    demographics["birthdate"] = pd.to_datetime(demographics["birthdate"], errors="coerce")

    return demographics, perf, prevloans


def compute_prevloan_features(prevloans):
    """
    Compute per-customer aggregates from loan history.
    Returns both magnitude and regularity features.
    """
    features = []

    for cust_id, group in prevloans.groupby("customerid"):
        group = group.sort_values("approveddate")

        # --- REGULARITY FEATURES ---

        # Repayment delay: days between firstduedate and closeddate
        # Negative = early, positive = late
        group["repay_delay"] = (group["closeddate"] - group["firstduedate"]).dt.days
        repay_delay_mean = group["repay_delay"].mean()
        repay_delay_std = group["repay_delay"].std()
        if pd.isna(repay_delay_std):
            repay_delay_std = 0  # Single loan

        # Early repayment ratio
        early_repay_ratio = (group["repay_delay"] < 0).mean()

        # Loan count and relationship tenure
        loan_count = len(group)
        first_loan = group["approveddate"].min()
        last_loan = group["approveddate"].max()
        relationship_tenure_days = (last_loan - first_loan).days

        # Interval regularity: std of gaps between successive applications
        if loan_count > 1:
            gaps = group["approveddate"].diff().dt.days.dropna()
            interval_regularity = gaps.std()
            interval_mean = gaps.mean()
            if pd.isna(interval_regularity):
                interval_regularity = 0
        else:
            interval_regularity = 0
            interval_mean = 0

        # Term escalation: slope of term over time (normalized)
        if loan_count > 1:
            x = np.arange(loan_count)
            y = group["termdays"].values
            if np.std(y) > 0:
                term_escalation = np.corrcoef(x, y)[0, 1]
                if pd.isna(term_escalation):
                    term_escalation = 0
            else:
                term_escalation = 0
        else:
            term_escalation = 0

        # --- MAGNITUDE FEATURES ---

        # Amount statistics
        amount_mean = group["loanamount"].mean()
        amount_max = group["loanamount"].max()
        amount_total = group["loanamount"].sum()

        # Amount CV (coefficient of variation) — consistency measure
        amount_std = group["loanamount"].std()
        if pd.isna(amount_std) or amount_mean == 0:
            amount_cv = 0
        else:
            amount_cv = amount_std / amount_mean

        # Total due statistics
        totaldue_mean = group["totaldue"].mean()

        # Term statistics
        term_mean = group["termdays"].mean()

        features.append({
            "customerid": cust_id,
            # Regularity features
            "repay_delay_mean": repay_delay_mean,
            "repay_delay_std": repay_delay_std,
            "early_repay_ratio": early_repay_ratio,
            "loan_count": loan_count,
            "relationship_tenure_days": relationship_tenure_days,
            "interval_regularity": interval_regularity,
            "interval_mean": interval_mean,
            "term_escalation": term_escalation,
            # Magnitude features
            "amount_mean": amount_mean,
            "amount_max": amount_max,
            "amount_total": amount_total,
            "amount_cv": amount_cv,
            "totaldue_mean": totaldue_mean,
            "term_mean": term_mean,
        })

    return pd.DataFrame(features)


def compute_demographic_features(demographics, reference_date=None):
    """
    Compute features from demographics.
    """
    if reference_date is None:
        reference_date = pd.Timestamp("2018-01-01")  # Approximate data collection date

    df = demographics.copy()

    # Age from birthdate
    df["age"] = (reference_date - df["birthdate"]).dt.days / 365.25
    df["age"] = df["age"].clip(lower=18, upper=100)  # Sanity bounds

    # Bank account type (categorical -> dummies later)
    df["bank_account_type"] = df["bank_account_type"].fillna("Unknown")

    # Employment status (categorical -> dummies later)
    df["employment_status"] = df["employment_status_clients"].fillna("Unknown")

    # GPS-based region proxy (simple binning by latitude)
    # Nigeria roughly spans 4-14 degrees latitude
    df["region_lat_band"] = pd.cut(
        df["latitude_gps"],
        bins=[0, 7, 9, 11, 15],
        labels=["South", "Middle", "North-Central", "North"]
    ).astype(str).fillna("Unknown")

    return df[["customerid", "age", "bank_account_type", "employment_status", "region_lat_band"]]


def build_feature_sets(demographics, perf, prevloans):
    """
    Build the three feature sets: magnitude, regularity, full.
    Returns a dict with feature matrices and the target.
    """
    print("Computing loan history features...")
    loan_features = compute_prevloan_features(prevloans)

    print("Computing demographic features...")
    demo_features = compute_demographic_features(demographics)

    # Start with perf (has the target)
    df = perf[["customerid", "good_bad_flag"]].copy()
    df["target"] = (df["good_bad_flag"] == "Bad").astype(int)

    # Merge loan features
    df = df.merge(loan_features, on="customerid", how="left")

    # Merge demographic features
    df = df.merge(demo_features, on="customerid", how="left")

    # Handle missing values for customers without loan history
    # Fill loan features with 0 (first-time borrowers)
    loan_cols = [c for c in loan_features.columns if c != "customerid"]
    for col in loan_cols:
        df[col] = df[col].fillna(0)

    # Fill demographic features
    df["age"] = df["age"].fillna(df["age"].median())
    df["bank_account_type"] = df["bank_account_type"].fillna("Unknown")
    df["employment_status"] = df["employment_status"].fillna("Unknown")
    df["region_lat_band"] = df["region_lat_band"].fillna("Unknown")

    # Create dummy variables for categoricals
    df = pd.get_dummies(df, columns=["bank_account_type", "employment_status", "region_lat_band"])

    # Define feature sets
    regularity_cols = [
        "repay_delay_mean", "repay_delay_std", "early_repay_ratio",
        "loan_count", "relationship_tenure_days", "interval_regularity",
        "interval_mean", "term_escalation"
    ]

    magnitude_cols = [
        "amount_mean", "amount_max", "amount_total", "amount_cv",
        "totaldue_mean", "term_mean"
    ]

    demographic_cols = [c for c in df.columns if c.startswith(("age", "bank_account_type_", "employment_status_", "region_lat_band_"))]

    # Include age in both sets as it's a basic demographic
    fs_regularity = regularity_cols + demographic_cols
    fs_magnitude = magnitude_cols + demographic_cols
    fs_full = regularity_cols + magnitude_cols + demographic_cols

    # Ensure all columns exist
    fs_regularity = [c for c in fs_regularity if c in df.columns]
    fs_magnitude = [c for c in fs_magnitude if c in df.columns]
    fs_full = [c for c in fs_full if c in df.columns]

    print(f"\nFeature set sizes:")
    print(f"  FS_regularity: {len(fs_regularity)} features")
    print(f"  FS_magnitude:  {len(fs_magnitude)} features")
    print(f"  FS_full:       {len(fs_full)} features")

    return {
        "df": df,
        "target": df["target"],
        "feature_sets": {
            "regularity": fs_regularity,
            "magnitude": fs_magnitude,
            "full": fs_full
        },
        "X_regularity": df[fs_regularity],
        "X_magnitude": df[fs_magnitude],
        "X_full": df[fs_full],
        "y": df["target"]
    }


def main():
    print("=== T4: Feature Engineering ===\n")

    demographics, perf, prevloans = load_data()
    result = build_feature_sets(demographics, perf, prevloans)

    # Save feature definitions
    feature_info = {
        "timestamp": datetime.now().isoformat(),
        "n_samples": len(result["df"]),
        "target_distribution": {
            "good": int((result["y"] == 0).sum()),
            "bad": int((result["y"] == 1).sum()),
            "default_rate": float(result["y"].mean())
        },
        "feature_sets": {
            name: {
                "n_features": len(cols),
                "features": cols
            }
            for name, cols in result["feature_sets"].items()
        }
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    with open(RESULTS_DIR / "feature_sets.json", "w") as f:
        json.dump(feature_info, f, indent=2)

    # Save the processed dataset for model training
    result["df"].to_csv(DATA_DIR / "features_processed.csv", index=False)

    print(f"\nFeature definitions saved to {RESULTS_DIR / 'feature_sets.json'}")
    print(f"Processed features saved to {DATA_DIR / 'features_processed.csv'}")

    # Print feature statistics
    print("\n=== Feature Statistics ===")
    for name, cols in result["feature_sets"].items():
        print(f"\n{name.upper()}:")
        desc = result["df"][cols].describe().T[["mean", "std", "min", "max"]]
        print(desc.to_string())

    return result


if __name__ == "__main__":
    main()
