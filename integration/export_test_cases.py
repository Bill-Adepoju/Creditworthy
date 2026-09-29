"""
T45: Export real test cases with actual model predictions for integration demo.

This script:
1. Loads the trained LogisticRegression model
2. Selects diverse test cases from the real test set
3. Exports feature vectors and predictions for use in the Node.js demo
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
import joblib

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"
OUTPUT_PATH = Path(__file__).parent / "test_cases.json"
MODEL_DIR = Path(__file__).parent.parent / "ml"

RANDOM_STATE = 42
N_TEST_CASES = 30  # More than 20 for warmup + actual runs


def load_and_prepare_data():
    """Load features and prepare data."""
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)

    feature_cols = feature_info["feature_sets"]["full"]["features"]
    X = df[feature_cols]
    y = df["target"]

    return df, X, y, feature_cols


def train_model(X, y):
    """Train LogisticRegression model."""
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    model.fit(X_train_scaled, y_train)

    return model, scaler, X_test, y_test, X_test_scaled


def select_diverse_cases(X_test, y_test, X_test_scaled, model, n_cases):
    """Select diverse test cases covering different score ranges."""

    # Get predictions
    y_prob = model.predict_proba(X_test_scaled)[:, 1]
    scores = np.round(1000 * (1 - y_prob)).astype(int)

    # Create dataframe for selection
    test_df = pd.DataFrame({
        "idx": range(len(scores)),
        "score": scores,
        "p_default": y_prob,
        "actual": y_test.values
    })

    # Select cases from different score ranges
    cases = []

    # Very high risk (score < 350)
    very_high = test_df[test_df["score"] < 350].sample(min(5, len(test_df[test_df["score"] < 350])), random_state=RANDOM_STATE)
    cases.append(very_high)

    # High risk (350-500)
    high = test_df[(test_df["score"] >= 350) & (test_df["score"] < 500)].sample(min(6, len(test_df[(test_df["score"] >= 350) & (test_df["score"] < 500)])), random_state=RANDOM_STATE)
    cases.append(high)

    # Borderline (500-600)
    borderline = test_df[(test_df["score"] >= 500) & (test_df["score"] < 600)].sample(min(6, len(test_df[(test_df["score"] >= 500) & (test_df["score"] < 600)])), random_state=RANDOM_STATE)
    cases.append(borderline)

    # Medium risk (600-750)
    medium = test_df[(test_df["score"] >= 600) & (test_df["score"] < 750)].sample(min(6, len(test_df[(test_df["score"] >= 600) & (test_df["score"] < 750)])), random_state=RANDOM_STATE)
    cases.append(medium)

    # Low risk (>= 750)
    low = test_df[test_df["score"] >= 750].sample(min(7, len(test_df[test_df["score"] >= 750])), random_state=RANDOM_STATE)
    cases.append(low)

    selected = pd.concat(cases).head(n_cases)

    return selected


def main():
    print("T45: Exporting real test cases for integration demo")
    print("=" * 60)

    # Load data
    print("Loading data...")
    df, X, y, feature_cols = load_and_prepare_data()

    # Train model
    print("Training model...")
    model, scaler, X_test, y_test, X_test_scaled = train_model(X, y)

    # Get demo data
    demo_df = pd.read_csv(DATA_DIR / "traindemographics.csv")

    # Select diverse cases
    print(f"Selecting {N_TEST_CASES} diverse test cases...")
    selected = select_diverse_cases(X_test, y_test, X_test_scaled, model, N_TEST_CASES)

    # Build output
    test_cases = []
    for _, row in selected.iterrows():
        idx = int(row["idx"])
        test_idx = X_test.index[idx]

        # Get customer info
        customer_id = df.loc[test_idx, "customerid"]
        demo_info = demo_df[demo_df["customerid"] == customer_id]

        case = {
            "id": int(idx),
            "customer_id": str(customer_id),
            "score": int(row["score"]),
            "p_default": round(float(row["p_default"]), 4),
            "actual_default": int(row["actual"]),
            "risk_category": (
                "very_high" if row["score"] < 350 else
                "high" if row["score"] < 500 else
                "borderline" if row["score"] < 600 else
                "medium" if row["score"] < 750 else
                "low"
            ),
            "bank_account_type": demo_info["bank_account_type"].values[0] if len(demo_info) > 0 else "Unknown",
            "feature_vector": [round(float(v), 6) for v in X_test_scaled[idx]],
            "feature_names": feature_cols
        }
        test_cases.append(case)

    # Sort by score for orderly output
    test_cases.sort(key=lambda x: x["score"])

    # Output
    output = {
        "generated": pd.Timestamp.now().isoformat(),
        "task": "T45",
        "model": {
            "type": "LogisticRegression",
            "n_features": len(feature_cols),
            "class_weight": "balanced",
            "random_state": RANDOM_STATE
        },
        "scaler_mean": [round(float(v), 6) for v in scaler.mean_],
        "scaler_scale": [round(float(v), 6) for v in scaler.scale_],
        "model_coef": [round(float(v), 6) for v in model.coef_[0]],
        "model_intercept": round(float(model.intercept_[0]), 6),
        "n_test_cases": len(test_cases),
        "test_cases": test_cases
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nExported {len(test_cases)} test cases to: {OUTPUT_PATH}")

    # Summary
    print("\nScore distribution:")
    for cat in ["very_high", "high", "borderline", "medium", "low"]:
        count = len([c for c in test_cases if c["risk_category"] == cat])
        print(f"  {cat}: {count}")

    print("\nSample cases:")
    for case in test_cases[:5]:
        print(f"  Score {case['score']}: {case['risk_category']}, actual={case['actual_default']}")


if __name__ == "__main__":
    main()
