"""
T47: Fairness-Profit Exchange Rate

Produce a proper trade-off curve: x = profit as % of maximum, y = FPR ratio.
Identify the Pareto frontier - thresholds where no alternative gives both
more profit and less disparity.

Key insight from HANDOVER.md:
- Giving up ~9% of profit cuts the disparity by ~28%
- Moving the other way costs 3% of profit and nearly doubles the ratio
- The profit surface is flat across this region; the fairness surface is not
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

# Profit model parameters
REVENUE_PER_PERFORMING = 1.0
LGD = 3.0  # Loss given default


def compute_fpr_by_group(y_true, y_prob, threshold, group_mask):
    """Compute FPR for a group at a threshold."""
    y_pred = (y_prob >= threshold).astype(int)

    y_true_g = y_true[group_mask]
    y_pred_g = y_pred[group_mask]

    if len(y_true_g) < MIN_SUBGROUP_SIZE:
        return None

    tn, fp, fn, tp = confusion_matrix(y_true_g, y_pred_g, labels=[0, 1]).ravel()

    # FPR = FP / (FP + TN)
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0

    return fpr


def compute_profit(y_true, y_prob, threshold):
    """Compute profit at a threshold."""
    y_pred = (y_prob >= threshold).astype(int)

    # Approved = pred=0 (not predicted default)
    approved = y_pred == 0

    # Among approved, who defaults?
    approved_defaults = (y_true == 1) & approved
    approved_performs = (y_true == 0) & approved

    profit = approved_performs.sum() * REVENUE_PER_PERFORMING - approved_defaults.sum() * LGD

    return float(profit), int(approved.sum())


def find_pareto_frontier(points):
    """
    Find Pareto frontier: points where no other point dominates.
    We want to maximize profit AND minimize FPR ratio.
    So a point is dominated if another has higher profit AND lower FPR ratio.
    """
    frontier = []

    for p in points:
        dominated = False
        for q in points:
            if q["profit_pct"] > p["profit_pct"] and q["fpr_ratio"] < p["fpr_ratio"]:
                dominated = True
                break
        if not dominated:
            frontier.append(p)

    # Sort by profit descending
    frontier.sort(key=lambda x: -x["profit_pct"])

    return frontier


def main():
    print("=" * 60)
    print("T47: Fairness-Profit Exchange Rate")
    print("=" * 60)
    print()

    # Load data
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)

    feature_cols = feature_info["feature_sets"]["full"]["features"]
    X = df[feature_cols]
    y = df["target"]

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE
    )

    # Scale and train
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

    y_true = test_df["y_true"].values
    y_prob = test_df["y_prob"].values

    # Group masks
    savings_mask = (test_df["bank_account_type"] == "Savings").values
    other_mask = (test_df["bank_account_type"] == "Other").values

    print(f"Test set: {len(y_true)}")
    print(f"  Savings: {savings_mask.sum()}")
    print(f"  Other: {other_mask.sum()}")
    print()

    # Sweep thresholds
    thresholds = np.arange(0.10, 0.90, 0.01)

    all_points = []

    for thresh in thresholds:
        fpr_savings = compute_fpr_by_group(y_true, y_prob, thresh, savings_mask)
        fpr_other = compute_fpr_by_group(y_true, y_prob, thresh, other_mask)
        profit, n_approved = compute_profit(y_true, y_prob, thresh)

        if fpr_savings is not None and fpr_other is not None and fpr_other > 0:
            fpr_ratio = fpr_savings / fpr_other
            all_points.append({
                "threshold": round(float(thresh), 2),
                "profit": profit,
                "n_approved": n_approved,
                "fpr_savings": round(fpr_savings, 4),
                "fpr_other": round(fpr_other, 4),
                "fpr_ratio": round(fpr_ratio, 2)
            })

    # Find max profit
    max_profit = max(p["profit"] for p in all_points)

    # Add profit percentage
    for p in all_points:
        p["profit_pct"] = round(100 * p["profit"] / max_profit, 1)

    # Find Pareto frontier
    pareto = find_pareto_frontier(all_points)

    print(f"Total points: {len(all_points)}")
    print(f"Pareto frontier points: {len(pareto)}")
    print()

    # Find profit-optimal threshold
    optimal = max(all_points, key=lambda x: x["profit"])
    print(f"Profit-optimal threshold: {optimal['threshold']}")
    print(f"  Profit: {optimal['profit']:.0f} (100%)")
    print(f"  FPR ratio: {optimal['fpr_ratio']:.2f}x")
    print()

    # Show key trade-off points
    print("Key trade-off points:")
    print("| Threshold | Profit | % of Max | FPR Ratio | On Frontier? |")
    print("|-----------|--------|----------|-----------|--------------|")

    for p in sorted(all_points, key=lambda x: x["threshold"]):
        if 0.40 <= p["threshold"] <= 0.65:
            on_frontier = "YES" if p in pareto else "NO"
            print(f"| {p['threshold']:.2f} | {p['profit']:.0f} | {p['profit_pct']:.1f}% | {p['fpr_ratio']:.2f}x | {on_frontier} |")

    print()

    # Find the exchange rate at profit-optimal
    # What does giving up 5%, 10% of profit buy in fairness terms?
    print("Exchange rate analysis:")

    # Find threshold that gives ~95% profit with lowest FPR ratio
    high_profit = [p for p in all_points if p["profit_pct"] >= 95]
    if high_profit:
        best_fairness_95 = min(high_profit, key=lambda x: x["fpr_ratio"])
        print(f"\nAt >=95% profit ({best_fairness_95['threshold']}):")
        print(f"  Profit: {best_fairness_95['profit_pct']:.1f}%")
        print(f"  FPR ratio: {best_fairness_95['fpr_ratio']:.2f}x")
        print(f"  vs optimal: Sacrifice {100 - best_fairness_95['profit_pct']:.1f}% profit for {optimal['fpr_ratio'] - best_fairness_95['fpr_ratio']:.2f} ratio reduction")

    high_profit_90 = [p for p in all_points if p["profit_pct"] >= 90]
    if high_profit_90:
        best_fairness_90 = min(high_profit_90, key=lambda x: x["fpr_ratio"])
        print(f"\nAt >=90% profit ({best_fairness_90['threshold']}):")
        print(f"  Profit: {best_fairness_90['profit_pct']:.1f}%")
        print(f"  FPR ratio: {best_fairness_90['fpr_ratio']:.2f}x")
        print(f"  vs optimal: Sacrifice {100 - best_fairness_90['profit_pct']:.1f}% profit for {optimal['fpr_ratio'] - best_fairness_90['fpr_ratio']:.2f} ratio reduction")

    # Calculate exchange rate
    if high_profit_90:
        profit_drop = optimal["profit"] - best_fairness_90["profit"]
        ratio_drop = optimal["fpr_ratio"] - best_fairness_90["fpr_ratio"]
        if ratio_drop > 0:
            exchange_rate = profit_drop / ratio_drop
            print(f"\nExchange rate: {exchange_rate:.1f} profit units per 1.0 FPR ratio reduction")

    # Create plot
    print("\n" + "=" * 60)
    print("Creating plots...")
    print("=" * 60)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Plot 1: Profit vs FPR ratio with Pareto frontier
    ax1 = axes[0]

    # All points
    profits = [p["profit_pct"] for p in all_points]
    fpr_ratios = [p["fpr_ratio"] for p in all_points]
    ax1.scatter(profits, fpr_ratios, c='lightblue', s=30, alpha=0.5, label='All thresholds')

    # Pareto frontier
    pareto_profits = [p["profit_pct"] for p in pareto]
    pareto_ratios = [p["fpr_ratio"] for p in pareto]
    pareto_sorted = sorted(zip(pareto_profits, pareto_ratios), reverse=True)
    ax1.plot([p[0] for p in pareto_sorted], [p[1] for p in pareto_sorted],
             'r-o', linewidth=2, markersize=8, label='Pareto frontier')

    # Highlight profit-optimal
    ax1.scatter([optimal["profit_pct"]], [optimal["fpr_ratio"]],
               c='green', s=200, marker='*', zorder=5, label=f'Profit-optimal ({optimal["threshold"]:.2f})')

    # Highlight best fairness at 90%+ profit
    if high_profit_90:
        ax1.scatter([best_fairness_90["profit_pct"]], [best_fairness_90["fpr_ratio"]],
                   c='purple', s=200, marker='D', zorder=5,
                   label=f'Best fairness >=90% ({best_fairness_90["threshold"]:.2f})')

    ax1.set_xlabel('Profit (% of maximum)', fontsize=12)
    ax1.set_ylabel('FPR Ratio (Savings / Other)', fontsize=12)
    ax1.set_title('Fairness-Profit Trade-off\n(Lower ratio = more fair)', fontsize=14)
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    ax1.invert_xaxis()  # Higher profit on left

    # Annotate the trade-off
    if high_profit_90:
        ax1.annotate('',
                    xy=(best_fairness_90["profit_pct"], best_fairness_90["fpr_ratio"]),
                    xytext=(optimal["profit_pct"], optimal["fpr_ratio"]),
                    arrowprops=dict(arrowstyle='->', color='orange', lw=2))
        mid_x = (optimal["profit_pct"] + best_fairness_90["profit_pct"]) / 2
        mid_y = (optimal["fpr_ratio"] + best_fairness_90["fpr_ratio"]) / 2
        ax1.annotate(f'-{100 - best_fairness_90["profit_pct"]:.0f}% profit\n-{optimal["fpr_ratio"] - best_fairness_90["fpr_ratio"]:.1f} ratio',
                    xy=(mid_x, mid_y), fontsize=10, color='orange', ha='center')

    # Plot 2: FPR ratio and profit vs threshold
    ax2 = axes[1]

    sorted_points = sorted(all_points, key=lambda x: x["threshold"])
    thresholds = [p["threshold"] for p in sorted_points]
    profits_sorted = [p["profit_pct"] for p in sorted_points]
    ratios_sorted = [p["fpr_ratio"] for p in sorted_points]

    ax2_twin = ax2.twinx()

    line1 = ax2.plot(thresholds, profits_sorted, 'b-', linewidth=2, label='Profit (% of max)')
    ax2.axvline(optimal["threshold"], color='green', linestyle='--', alpha=0.7, label='Profit-optimal')

    line2 = ax2_twin.plot(thresholds, ratios_sorted, 'r-', linewidth=2, label='FPR Ratio')
    ax2_twin.axhline(1.0, color='gray', linestyle=':', alpha=0.5)

    ax2.set_xlabel('Threshold (P(default))', fontsize=12)
    ax2.set_ylabel('Profit (% of max)', color='blue', fontsize=12)
    ax2_twin.set_ylabel('FPR Ratio', color='red', fontsize=12)
    ax2.set_title('Profit and Fairness vs Threshold', fontsize=14)

    # Shade the "sweet spot" region where profit > 90%
    ax2.axvspan(0.40, 0.55, alpha=0.1, color='green', label='Sweet spot')

    ax2.legend(loc='upper left')
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plot_path = RESULTS_DIR / "fairness_profit_tradeoff.png"
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved to: {plot_path}")

    # Compile results
    results = {
        "timestamp": datetime.now().isoformat(),
        "task": "T47",
        "title": "Fairness-Profit Exchange Rate",
        "positive_class": "DEFAULT (target=1)",
        "random_state": RANDOM_STATE,
        "profit_model": {
            "revenue_per_performing": REVENUE_PER_PERFORMING,
            "loss_given_default": LGD
        },

        "profit_optimal": {
            "threshold": optimal["threshold"],
            "profit": optimal["profit"],
            "profit_pct": 100.0,
            "fpr_ratio": optimal["fpr_ratio"],
            "n_approved": optimal["n_approved"]
        },

        "pareto_frontier": pareto,
        "n_pareto_points": len(pareto),

        "exchange_rate_analysis": {
            "at_95pct_profit": {
                "threshold": best_fairness_95["threshold"] if high_profit else None,
                "profit_pct": best_fairness_95["profit_pct"] if high_profit else None,
                "fpr_ratio": best_fairness_95["fpr_ratio"] if high_profit else None,
                "profit_sacrifice": round(100 - best_fairness_95["profit_pct"], 1) if high_profit else None,
                "ratio_improvement": round(optimal["fpr_ratio"] - best_fairness_95["fpr_ratio"], 2) if high_profit else None
            } if high_profit else None,
            "at_90pct_profit": {
                "threshold": best_fairness_90["threshold"] if high_profit_90 else None,
                "profit_pct": best_fairness_90["profit_pct"] if high_profit_90 else None,
                "fpr_ratio": best_fairness_90["fpr_ratio"] if high_profit_90 else None,
                "profit_sacrifice": round(100 - best_fairness_90["profit_pct"], 1) if high_profit_90 else None,
                "ratio_improvement": round(optimal["fpr_ratio"] - best_fairness_90["fpr_ratio"], 2) if high_profit_90 else None
            } if high_profit_90 else None,
            "exchange_rate_profit_per_ratio": round(exchange_rate, 1) if high_profit_90 and ratio_drop > 0 else None
        },

        "key_finding": (
            f"The profit surface is flat in the near-optimal region while the fairness surface is not. "
            f"At profit-optimal threshold ({optimal['threshold']}), FPR ratio is {optimal['fpr_ratio']:.2f}x. "
            f"Sacrificing {100 - best_fairness_90['profit_pct']:.1f}% profit (threshold {best_fairness_90['threshold']}) "
            f"reduces the ratio to {best_fairness_90['fpr_ratio']:.2f}x — "
            f"a {(optimal['fpr_ratio'] - best_fairness_90['fpr_ratio']) / optimal['fpr_ratio'] * 100:.0f}% fairness improvement "
            f"for <{100 - best_fairness_90['profit_pct']:.0f}% profit cost."
        ) if high_profit_90 else "Insufficient data for exchange rate analysis",

        "all_points": all_points
    }

    output_path = RESULTS_DIR / "fairness_profit_tradeoff.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {output_path}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"\nProfit-optimal: threshold={optimal['threshold']}, ratio={optimal['fpr_ratio']:.2f}x")
    if high_profit_90:
        print(f"Best fairness >=90%: threshold={best_fairness_90['threshold']}, ratio={best_fairness_90['fpr_ratio']:.2f}x")
        print(f"\nTrade-off: {100 - best_fairness_90['profit_pct']:.1f}% profit -> {(optimal['fpr_ratio'] - best_fairness_90['fpr_ratio']) / optimal['fpr_ratio'] * 100:.0f}% fairness improvement")
    print(f"\nPareto frontier: {len(pareto)} efficient points")

    return results


if __name__ == "__main__":
    main()
