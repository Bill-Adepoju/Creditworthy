"""
T6: Fairness audit
Evaluates demographic parity and equal opportunity differences across
protected attributes, then produces accuracy-fairness trade-off curves.

Per CLAUDE.md: Fairness is not optional. Every model evaluation reports
fairness metrics alongside accuracy.
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings("ignore")

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, accuracy_score
from fairlearn.metrics import (
    demographic_parity_difference,
    equalized_odds_difference,
    MetricFrame
)
from fairlearn.postprocessing import ThresholdOptimizer
import matplotlib.pyplot as plt

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"

RANDOM_STATE = 42


def load_data():
    """Load processed features with sensitive attributes."""
    df = pd.read_csv(DATA_DIR / "features_processed.csv")

    # Reconstruct sensitive attributes from dummy columns
    # Region
    region_cols = [c for c in df.columns if c.startswith("region_lat_band_")]
    if region_cols:
        df["region"] = df[region_cols].idxmax(axis=1).str.replace("region_lat_band_", "")
    else:
        df["region"] = "Unknown"

    # Bank account type
    bank_cols = [c for c in df.columns if c.startswith("bank_account_type_")]
    if bank_cols:
        df["bank_account_type"] = df[bank_cols].idxmax(axis=1).str.replace("bank_account_type_", "")
    else:
        df["bank_account_type"] = "Unknown"

    # Employment status
    emp_cols = [c for c in df.columns if c.startswith("employment_status_")]
    if emp_cols:
        df["employment_status"] = df[emp_cols].idxmax(axis=1).str.replace("employment_status_", "")
    else:
        df["employment_status"] = "Unknown"

    # Age bands
    df["age_band"] = pd.cut(
        df["age"],
        bins=[0, 25, 35, 45, 100],
        labels=["18-25", "26-35", "36-45", "46+"]
    ).astype(str)

    return df


def get_feature_columns(df):
    """Get the full feature set columns."""
    exclude = ["customerid", "good_bad_flag", "target", "region", "bank_account_type",
               "employment_status", "age_band"]
    return [c for c in df.columns if c not in exclude and not c.startswith(("region_lat_band_", "bank_account_type_", "employment_status_"))]


def compute_fairness_metrics(y_true, y_pred, sensitive_feature):
    """Compute fairness metrics for a single sensitive attribute."""
    # Filter out missing values
    mask = sensitive_feature != "Unknown"
    y_true_f = y_true[mask]
    y_pred_f = y_pred[mask]
    sf_f = sensitive_feature[mask]

    if len(y_true_f) == 0:
        return None

    # Demographic parity difference
    dpd = demographic_parity_difference(y_true_f, y_pred_f, sensitive_features=sf_f)

    # Equalized odds difference (approximation via equal opportunity)
    eod = equalized_odds_difference(y_true_f, y_pred_f, sensitive_features=sf_f)

    # Per-group metrics
    mf = MetricFrame(
        metrics={"selection_rate": lambda y_t, y_p: np.mean(y_p),
                 "accuracy": accuracy_score},
        y_true=y_true_f,
        y_pred=y_pred_f,
        sensitive_features=sf_f
    )

    return {
        "demographic_parity_difference": float(dpd),
        "equalized_odds_difference": float(eod),
        "group_metrics": mf.by_group.to_dict(),
        "n_samples": int(len(y_true_f))
    }


def accuracy_fairness_tradeoff(X_train, y_train, X_test, y_test, sensitive_test):
    """
    Compute accuracy-fairness trade-off by varying decision threshold.
    """
    # Train model
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    model.fit(X_train_s, y_train)

    y_prob = model.predict_proba(X_test_s)[:, 1]

    # Vary threshold
    thresholds = np.linspace(0.1, 0.9, 17)
    results = []

    for thresh in thresholds:
        y_pred = (y_prob >= thresh).astype(int)

        # Accuracy
        acc = accuracy_score(y_test, y_pred)

        # Fairness (demographic parity)
        mask = sensitive_test != "Unknown"
        if mask.sum() > 0:
            dpd = abs(demographic_parity_difference(
                y_test[mask], y_pred[mask], sensitive_features=sensitive_test[mask]
            ))
        else:
            dpd = 0

        results.append({
            "threshold": float(thresh),
            "accuracy": float(acc),
            "dpd": float(dpd)
        })

    return results


def main():
    print("=== T6: Fairness Audit ===\n")

    df = load_data()
    feature_cols = get_feature_columns(df)

    # Use full feature set
    X = df[feature_cols]
    y = df["target"]

    # Sensitive attributes
    sensitive_attrs = {
        "region": df["region"],
        "bank_account_type": df["bank_account_type"],
        "employment_status": df["employment_status"],
        "age_band": df["age_band"]
    }

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE
    )

    # Also split sensitive attributes
    sensitive_test = {name: attr.iloc[y_test.index].reset_index(drop=True)
                      for name, attr in sensitive_attrs.items()}
    y_test = y_test.reset_index(drop=True)

    # Train model
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    model.fit(X_train_s, y_train)

    y_pred = model.predict(X_test_s)
    y_prob = model.predict_proba(X_test_s)[:, 1]

    # Overall performance
    roc_auc = roc_auc_score(y_test, y_prob)
    accuracy = accuracy_score(y_test, y_pred)

    print(f"Model: LogisticRegression (class_weight='balanced')")
    print(f"ROC-AUC: {roc_auc:.4f}")
    print(f"Accuracy: {accuracy:.4f}")

    # Compute fairness metrics for each sensitive attribute
    results = {
        "timestamp": datetime.now().isoformat(),
        "model": "LogisticRegression",
        "overall": {
            "roc_auc": float(roc_auc),
            "accuracy": float(accuracy),
            "n_test": int(len(y_test))
        },
        "sensitive_attributes": {}
    }

    print("\n" + "="*60)
    print("FAIRNESS METRICS")
    print("="*60)

    for attr_name, attr_values in sensitive_test.items():
        print(f"\n--- {attr_name} ---")

        # Group distribution
        dist = attr_values.value_counts()
        print(f"Distribution: {dict(dist)}")

        metrics = compute_fairness_metrics(y_test, y_pred, attr_values)
        if metrics:
            results["sensitive_attributes"][attr_name] = metrics
            print(f"Demographic Parity Difference: {metrics['demographic_parity_difference']:.4f}")
            print(f"Equalized Odds Difference: {metrics['equalized_odds_difference']:.4f}")
        else:
            print("Insufficient data for fairness metrics")

    # Accuracy-Fairness trade-off curve (using region as primary sensitive attribute)
    print("\n" + "="*60)
    print("ACCURACY-FAIRNESS TRADE-OFF")
    print("="*60)

    tradeoff = accuracy_fairness_tradeoff(
        X_train, y_train, X_test, y_test.values,
        sensitive_test["region"].values
    )
    results["tradeoff_curve"] = tradeoff

    # Plot trade-off
    fig, ax = plt.subplots(figsize=(8, 6))

    accuracies = [t["accuracy"] for t in tradeoff]
    dpds = [t["dpd"] for t in tradeoff]
    thresholds = [t["threshold"] for t in tradeoff]

    scatter = ax.scatter(dpds, accuracies, c=thresholds, cmap="viridis", s=100)
    ax.set_xlabel("Demographic Parity Difference (lower = fairer)", fontsize=12)
    ax.set_ylabel("Accuracy", fontsize=12)
    ax.set_title("Accuracy-Fairness Trade-off Curve\n(by varying classification threshold)", fontsize=14)

    cbar = plt.colorbar(scatter)
    cbar.set_label("Decision Threshold")

    # Annotate a few points
    for i in [0, len(thresholds)//2, -1]:
        ax.annotate(f"t={thresholds[i]:.2f}", (dpds[i], accuracies[i]),
                    xytext=(5, 5), textcoords="offset points", fontsize=9)

    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "fairness_tradeoff.png", dpi=150)
    print(f"Trade-off plot saved to {RESULTS_DIR / 'fairness_tradeoff.png'}")

    # Save results
    with open(RESULTS_DIR / "fairness.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to {RESULTS_DIR / 'fairness.json'}")

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"{'Attribute':<25} {'DPD':<10} {'EOD':<10}")
    print("-"*45)
    for attr_name, metrics in results["sensitive_attributes"].items():
        dpd = metrics["demographic_parity_difference"]
        eod = metrics["equalized_odds_difference"]
        print(f"{attr_name:<25} {dpd:>8.4f}  {eod:>8.4f}")

    # Fairness assessment
    print("\nFairness thresholds (common practice):")
    print("  DPD < 0.1: Generally considered fair")
    print("  EOD < 0.1: Generally considered fair")

    return results


if __name__ == "__main__":
    main()
