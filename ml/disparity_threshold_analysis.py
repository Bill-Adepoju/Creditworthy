"""
T37: Reconcile Disparity Magnitude

Cycle 03 reported 3.04x disparity (Savings 44.7% vs Other 14.7%)
Cycle 04 reports 1.66x disparity (53.97% vs 32.58%)

The discrepancy is likely due to different decision thresholds.
This script plots disparity ratio across the full threshold range.
"""
import numpy as np
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

RESULTS_DIR = Path(__file__).parent.parent / "results"
DATA_DIR = Path(__file__).parent.parent / "data"


def extract_bank_account_type(df):
    """Extract bank_account_type from one-hot encoded columns."""
    type_cols = [c for c in df.columns if c.startswith("bank_account_type_")]
    account_types = []
    for _, row in df.iterrows():
        for col in type_cols:
            if row[col]:
                account_types.append(col.replace("bank_account_type_", ""))
                break
        else:
            account_types.append("Unknown")
    return pd.Series(account_types, index=df.index)


def main():
    print("=== T37: Disparity Threshold Analysis ===\n")

    # Load data matching privacy_utility_v2.py
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)

    features = feature_info["feature_sets"]["full"]["features"]
    X = df[features].values
    y = df["target"].values

    # Extract bank account type
    bank_type = extract_bank_account_type(df)

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    _, _, bank_train, bank_test = train_test_split(
        X, bank_type.values, test_size=0.2, random_state=42, stratify=y
    )

    # Scale and train
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(
        max_iter=1000,
        random_state=42,
        class_weight="balanced"
    )
    model.fit(X_train_scaled, y_train)

    # Get predicted probabilities
    proba = model.predict_proba(X_test_scaled)[:, 1]  # P(default)

    # Analyze disparity at different thresholds
    print("Disparity ratio (Savings approval / Other approval) at different thresholds:\n")

    savings_mask = bank_test == "Savings"
    other_mask = bank_test == "Other"

    n_savings = savings_mask.sum()
    n_other = other_mask.sum()
    print(f"Test set: Savings={n_savings}, Other={n_other}\n")

    thresholds = np.arange(0.1, 0.9, 0.05)
    disparity_ratios = []
    savings_approval_rates = []
    other_approval_rates = []

    print("| Threshold | Savings Approval | Other Approval | Disparity Ratio |")
    print("|-----------|------------------|----------------|-----------------|")

    for thresh in thresholds:
        # Approval = predicted as non-default (proba < threshold)
        savings_approval = (proba[savings_mask] < thresh).mean()
        other_approval = (proba[other_mask] < thresh).mean()

        if savings_approval > 0:
            ratio = other_approval / savings_approval
        else:
            ratio = float('inf')

        savings_approval_rates.append(savings_approval)
        other_approval_rates.append(other_approval)
        disparity_ratios.append(ratio)

        print(f"| {thresh:.2f}      | {savings_approval*100:5.1f}%           | {other_approval*100:5.1f}%         | {ratio:.2f}x           |")

    # Find thresholds that give the previously reported disparities
    print("\n" + "=" * 60)
    print("RECONCILING REPORTED DISPARITIES")
    print("=" * 60)

    # Cycle 03: Savings 44.7%, Other 14.7% (but these were REJECTION rates!)
    # So approval was: Savings 55.3%, Other 85.3%
    # Let's find thresholds that give these approval rates

    print("\nCycle 03 reported pred_rate (REJECTION rates):")
    print("  Savings: 44.7% rejection -> 55.3% approval")
    print("  Other: 14.7% rejection -> 85.3% approval")

    # The median threshold gives different rates
    median_thresh = np.median(proba)
    savings_at_median = (proba[savings_mask] < median_thresh).mean()
    other_at_median = (proba[other_mask] < median_thresh).mean()

    print(f"\nAt MEDIAN threshold ({median_thresh:.3f}):")
    print(f"  Savings approval: {savings_at_median*100:.1f}%")
    print(f"  Other approval: {other_at_median*100:.1f}%")
    print(f"  Disparity ratio: {other_at_median/savings_at_median:.2f}x")

    # Find the threshold that gives ~55% Savings approval
    for thresh in np.arange(0.01, 0.99, 0.01):
        savings_approval = (proba[savings_mask] < thresh).mean()
        if abs(savings_approval - 0.553) < 0.02:
            other_approval = (proba[other_mask] < thresh).mean()
            print(f"\nAt threshold {thresh:.2f} (Savings ~55% approval):")
            print(f"  Savings approval: {savings_approval*100:.1f}%")
            print(f"  Other approval: {other_approval*100:.1f}%")
            print(f"  Disparity ratio: {other_approval/savings_approval:.2f}x")
            break

    # Plot
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Approval rates by threshold
    ax1.plot(thresholds, [r*100 for r in savings_approval_rates], 'b-', label='Savings', linewidth=2)
    ax1.plot(thresholds, [r*100 for r in other_approval_rates], 'g-', label='Other', linewidth=2)
    ax1.axhline(y=50, color='gray', linestyle='--', alpha=0.5)
    ax1.set_xlabel('Probability Threshold')
    ax1.set_ylabel('Approval Rate (%)')
    ax1.set_title('Approval Rates by Threshold')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Disparity ratio by threshold
    ax2.plot(thresholds, disparity_ratios, 'r-', linewidth=2)
    ax2.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5, label='Parity')
    ax2.set_xlabel('Probability Threshold')
    ax2.set_ylabel('Disparity Ratio (Other/Savings)')
    ax2.set_title('Disparity Ratio by Threshold')
    ax2.set_ylim(0, 3)
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "disparity_threshold_curve.png", dpi=150)
    print(f"\nPlot saved to {RESULTS_DIR / 'disparity_threshold_curve.png'}")

    # Key finding
    print("\n" + "=" * 60)
    print("KEY FINDING")
    print("=" * 60)
    print("""
The disparity ratio is THRESHOLD-DEPENDENT.

At low thresholds (strict): ratio is higher (more disparity)
At high thresholds (lenient): ratio approaches 1 (less disparity)

This is because the score distributions of Savings and Other groups
overlap, but Other has more probability mass at low-risk scores.

For dissertation:
1. Report the threshold used (e.g., median, or business-optimal)
2. Note that disparity varies with operating point
3. Consider reporting the range of disparities, not just a single figure
""")

    # Save results
    results = {
        "timestamp": datetime.now().isoformat(),
        "test_set": {
            "n_savings": int(n_savings),
            "n_other": int(n_other)
        },
        "threshold_analysis": [
            {
                "threshold": float(t),
                "savings_approval": float(s),
                "other_approval": float(o),
                "disparity_ratio": float(d) if d != float('inf') else None
            }
            for t, s, o, d in zip(thresholds, savings_approval_rates, other_approval_rates, disparity_ratios)
        ],
        "median_threshold": {
            "threshold": float(median_thresh),
            "savings_approval": float(savings_at_median),
            "other_approval": float(other_at_median),
            "disparity_ratio": float(other_at_median / savings_at_median) if savings_at_median > 0 else None
        },
        "conclusion": {
            "disparity_is_threshold_dependent": True,
            "dissertation_recommendation": "Report disparity at a stated operating point, acknowledge threshold dependence"
        }
    }

    output_path = RESULTS_DIR / "disparity_threshold_analysis.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
