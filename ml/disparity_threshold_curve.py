"""
T37: Disparity-vs-Threshold Curve

Report the full FPR disparity curve across all thresholds.
Quote a single headline figure at the profit-optimal threshold.

Key finding: The disparity is not a stable property of the model but a property
of the model + the deployment decision. A lender can materially change its
fairness profile by moving a cut-off.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"

RANDOM_STATE = 42
MIN_SUBGROUP_SIZE = 30

# Profit model parameters (from privacy_utility analysis)
REVENUE_PER_PERFORMING = 1.0
LGD = 3.0  # Loss given default


def load_data():
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)
    return df, feature_info


def compute_fpr_by_group(y_true, y_prob, threshold, group_mask):
    """Compute FPR (creditworthy rejected) for a group at a threshold."""
    y_pred = (y_prob >= threshold).astype(int)

    y_true_g = y_true[group_mask]
    y_pred_g = y_pred[group_mask]

    if len(y_true_g) < MIN_SUBGROUP_SIZE:
        return None

    # Confusion matrix
    tn, fp, fn, tp = confusion_matrix(y_true_g, y_pred_g, labels=[0, 1]).ravel()

    # FPR = FP / (FP + TN) = creditworthy rejected
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0

    return fpr


def compute_profit(y_true, y_prob, threshold):
    """Compute expected profit at a threshold."""
    y_pred = (y_prob >= threshold).astype(int)

    # Approved = pred=0 (not predicted default)
    approved = y_pred == 0

    # Among approved, who defaults?
    approved_defaults = (y_true == 1) & approved
    approved_performs = (y_true == 0) & approved

    profit = approved_performs.sum() * REVENUE_PER_PERFORMING - approved_defaults.sum() * LGD

    return profit, approved.sum()


def main():
    print("=" * 60)
    print("T37: Disparity-vs-Threshold Curve")
    print("=" * 60)
    print()

    df, feature_info = load_data()

    feature_cols = feature_info["feature_sets"]["full"]["features"]
    X = df[feature_cols]
    y = df["target"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    model.fit(X_train_scaled, y_train)

    y_prob = model.predict_proba(X_test_scaled)[:, 1]
    y_true = y_test.values

    # Get demographics
    test_indices = X_test.index
    demo_df = pd.read_csv(DATA_DIR / "traindemographics.csv")

    test_df = pd.DataFrame({
        "y_true": y_true,
        "y_prob": y_prob,
        "customerid": df.loc[test_indices, "customerid"].values
    })
    test_df = test_df.merge(demo_df, on="customerid", how="left")

    # Use values from merged dataframe consistently
    y_true = test_df["y_true"].values
    y_prob = test_df["y_prob"].values

    # Bank account type masks
    savings_mask = (test_df["bank_account_type"] == "Savings").values
    other_mask = (test_df["bank_account_type"] == "Other").values

    # Threshold range
    thresholds = np.arange(0.05, 0.95, 0.01)

    results_data = []
    profits = []

    print("Computing FPR disparity across thresholds...")
    print()

    for thresh in thresholds:
        fpr_savings = compute_fpr_by_group(y_true, y_prob, thresh, savings_mask)
        fpr_other = compute_fpr_by_group(y_true, y_prob, thresh, other_mask)

        profit, n_approved = compute_profit(y_true, y_prob, thresh)
        profits.append((thresh, profit, n_approved))

        if fpr_savings is not None and fpr_other is not None and fpr_other > 0:
            ratio = fpr_savings / fpr_other
            diff = fpr_savings - fpr_other
            results_data.append({
                "threshold": round(thresh, 2),
                "fpr_savings": round(fpr_savings, 4),
                "fpr_other": round(fpr_other, 4),
                "fpr_ratio": round(ratio, 2),
                "fpr_diff": round(diff, 4),
                "profit": int(profit),
                "n_approved": int(n_approved)
            })

    # Find profit-optimal threshold
    profit_optimal = max(profits, key=lambda x: x[1])
    optimal_thresh = float(profit_optimal[0])
    optimal_profit = float(profit_optimal[1])

    print(f"Profit-optimal threshold: {optimal_thresh:.2f}")
    print(f"Profit at optimum: {optimal_profit:.1f}")
    print()

    # Get disparity at optimal threshold
    optimal_result = next((r for r in results_data if abs(r["threshold"] - optimal_thresh) < 0.01), None)

    if optimal_result:
        print(f"At profit-optimal threshold ({optimal_thresh:.2f}):")
        print(f"  Savings FPR: {optimal_result['fpr_savings']:.1%}")
        print(f"  Other FPR: {optimal_result['fpr_other']:.1%}")
        print(f"  Ratio: {optimal_result['fpr_ratio']:.1f}x")
        print()

    # Summary statistics
    ratios = [r["fpr_ratio"] for r in results_data]
    print(f"Disparity range across thresholds:")
    print(f"  Min ratio: {min(ratios):.1f}x")
    print(f"  Max ratio: {max(ratios):.1f}x")
    print(f"  Median ratio: {np.median(ratios):.1f}x")
    print()

    # Create curve data for plotting
    curve_thresholds = [r["threshold"] for r in results_data]
    curve_ratios = [r["fpr_ratio"] for r in results_data]
    curve_fpr_savings = [r["fpr_savings"] for r in results_data]
    curve_fpr_other = [r["fpr_other"] for r in results_data]

    # Plot
    fig, axes = plt.subplots(2, 1, figsize=(10, 8))

    # Plot 1: FPR by group
    ax1 = axes[0]
    ax1.plot(curve_thresholds, curve_fpr_savings, 'b-', label='Savings (disadvantaged)', linewidth=2)
    ax1.plot(curve_thresholds, curve_fpr_other, 'g-', label='Other (favored)', linewidth=2)
    ax1.axvline(optimal_thresh, color='r', linestyle='--', label=f'Profit-optimal ({optimal_thresh:.2f})')
    ax1.set_xlabel('Threshold (P(default))')
    ax1.set_ylabel('FPR (creditworthy rejected)')
    ax1.set_title('FPR by Bank Account Type vs Threshold')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Plot 2: Disparity ratio
    ax2 = axes[1]
    ax2.plot(curve_thresholds, curve_ratios, 'purple', linewidth=2)
    ax2.axvline(optimal_thresh, color='r', linestyle='--', label=f'Profit-optimal ({optimal_thresh:.2f})')
    ax2.axhline(1.0, color='gray', linestyle=':', alpha=0.5, label='Parity (1.0x)')
    ax2.set_xlabel('Threshold (P(default))')
    ax2.set_ylabel('FPR Ratio (Savings / Other)')
    ax2.set_title('Disparity Ratio vs Threshold')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "disparity_threshold_curve.png", dpi=150)
    print(f"Plot saved to: {RESULTS_DIR / 'disparity_threshold_curve.png'}")

    # Compile results
    results = {
        "timestamp": datetime.now().isoformat(),
        "task": "T37",
        "positive_class": "DEFAULT (target=1)",
        "metric": "FPR (creditworthy borrowers wrongly rejected)",
        "sensitive_attribute": "bank_account_type",
        "groups_compared": ["Savings", "Other"],
        "profit_model": {
            "revenue_per_performing": REVENUE_PER_PERFORMING,
            "loss_given_default": LGD
        },
        "profit_optimal_threshold": optimal_thresh,
        "at_profit_optimal": optimal_result if optimal_result else None,
        "disparity_range": {
            "min_ratio": round(min(ratios), 2),
            "max_ratio": round(max(ratios), 2),
            "median_ratio": round(np.median(ratios), 2)
        },
        "key_finding": (
            f"The FPR disparity ratio ranges from {min(ratios):.1f}x to {max(ratios):.1f}x "
            f"across operating points. At the profit-optimal threshold ({optimal_thresh:.2f}), "
            f"the ratio is {optimal_result['fpr_ratio']:.1f}x. "
            f"The disparity is not a stable property of the model but depends on the "
            f"deployment decision - a lender can materially change its fairness profile "
            f"by moving a cut-off."
        ),
        "full_curve": results_data
    }

    output_path = RESULTS_DIR / "disparity_threshold_curve.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to: {output_path}")

    return results


if __name__ == "__main__":
    main()
