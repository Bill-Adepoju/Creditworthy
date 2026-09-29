"""
T48: Establish one canonical test split

The Savings subgroup has been reported as n = 537, 533, 407, then 520;
test-set size as 876, 879, 885. Every shift makes cross-cycle comparison unreliable.

This script:
1. Fixes one seeded split
2. Persists the indices
3. Records the seed and split sizes

All future analyses should use this canonical split.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
from sklearn.model_selection import train_test_split

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"

# The canonical random state - DO NOT CHANGE
CANONICAL_RANDOM_STATE = 42
TEST_SIZE = 0.2


def main():
    print("=" * 60)
    print("T48: Establishing Canonical Test Split")
    print("=" * 60)
    print()

    # Load the processed features
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    print(f"Total samples in features_processed.csv: {len(df)}")

    # Load feature sets to get feature columns
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)

    feature_cols = feature_info["feature_sets"]["full"]["features"]
    X = df[feature_cols]
    y = df["target"]

    # Create the canonical split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=CANONICAL_RANDOM_STATE
    )

    train_indices = X_train.index.tolist()
    test_indices = X_test.index.tolist()

    print(f"\nCanonical split established:")
    print(f"  Train size: {len(train_indices)}")
    print(f"  Test size: {len(test_indices)}")
    print(f"  Train default rate: {y_train.mean():.4f}")
    print(f"  Test default rate: {y_test.mean():.4f}")
    print()

    # Verify with demographics
    demo_df = pd.read_csv(DATA_DIR / "traindemographics.csv")

    # Get test demographics
    test_customers = df.loc[test_indices, "customerid"].values
    test_demo = demo_df[demo_df["customerid"].isin(test_customers)]

    # Count subgroups
    bank_account_counts = test_demo["bank_account_type"].value_counts()
    print("Bank account type distribution in TEST set:")
    for account_type, count in bank_account_counts.items():
        print(f"  {account_type}: {count}")

    # Create merged test dataframe for accurate counting
    test_df = pd.DataFrame({
        "y_true": y_test.values,
        "customerid": df.loc[test_indices, "customerid"].values
    })
    test_df = test_df.merge(demo_df, on="customerid", how="left")

    print("\nAfter merge with demographics:")
    final_counts = test_df["bank_account_type"].value_counts(dropna=False)
    for account_type, count in final_counts.items():
        print(f"  {account_type}: {count}")

    # The canonical numbers
    savings_count = (test_df["bank_account_type"] == "Savings").sum()
    other_count = (test_df["bank_account_type"] == "Other").sum()

    print(f"\n*** CANONICAL COUNTS ***")
    print(f"  Total test set: {len(test_indices)}")
    print(f"  Savings: {savings_count}")
    print(f"  Other: {other_count}")

    # Save the canonical split
    canonical_split = {
        "timestamp": datetime.now().isoformat(),
        "task": "T48",
        "random_state": CANONICAL_RANDOM_STATE,
        "test_size": TEST_SIZE,
        "data_file": "features_processed.csv",

        "split_sizes": {
            "total": len(df),
            "train": len(train_indices),
            "test": len(test_indices)
        },

        "default_rates": {
            "train": round(float(y_train.mean()), 4),
            "test": round(float(y_test.mean()), 4)
        },

        "canonical_subgroup_sizes": {
            "test_total": len(test_indices),
            "savings": int(savings_count),
            "other": int(other_count),
            "note": "Use these exact counts for consistency across analyses"
        },

        "indices": {
            "train": train_indices,
            "test": test_indices
        },

        "usage_instructions": (
            "To use this canonical split in any analysis:\n"
            "1. Load canonical_split.json\n"
            "2. Use indices['train'] and indices['test'] to subset the data\n"
            "3. Do NOT call train_test_split() again - use these indices directly\n"
            "4. Report these canonical sizes in results files"
        )
    }

    output_path = RESULTS_DIR / "canonical_split.json"
    with open(output_path, "w") as f:
        json.dump(canonical_split, f, indent=2)

    print(f"\nCanonical split saved to: {output_path}")

    # Verify the split is deterministic
    print("\n" + "=" * 60)
    print("Verification: Re-running split with same seed...")
    print("=" * 60)

    X_train2, X_test2, y_train2, y_test2 = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=CANONICAL_RANDOM_STATE
    )

    match = (X_test2.index == X_test.index).all()
    print(f"\nIndices match on re-run: {match}")

    if match:
        print("VERIFICATION PASSED: Split is deterministic")
    else:
        print("VERIFICATION FAILED: Split is not deterministic!")

    # Summary for HANDOVER
    print("\n" + "=" * 60)
    print("SUMMARY FOR HANDOVER.md")
    print("=" * 60)
    print(f"\nCanonical test set: n={len(test_indices)}")
    print(f"  Savings: {savings_count}")
    print(f"  Other: {other_count}")
    print(f"  Random state: {CANONICAL_RANDOM_STATE}")
    print(f"\nAll future analyses MUST use canonical_split.json indices.")

    return canonical_split


if __name__ == "__main__":
    main()
