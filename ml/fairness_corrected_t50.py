"""
T50: Corrected Fairness-Profit Analysis

FIXES T47's fundamental error: FPR ratio can recommend interventions that
make the disadvantaged group WORSE OFF.

T47 recommended threshold 0.46 because the FPR ratio improves (1.94x vs 2.68x).
But what actually happens:
- Savings FPR WORSENS from 27.3% to 41.2% (+51%)
- FPR gap WIDENS from 0.171 to 0.200 (+17%)
- Only the ratio improves because Other gets harmed faster

The correct metrics track WELFARE:
1. Absolute FPR for the disadvantaged group (Savings)
2. FPR difference (Savings - Other)

Key insight: ratio parity can be achieved by harming the favored group.
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

# Use canonical split
RANDOM_STATE = 42
TEST_SIZE = 0.2

# Profit model
REVENUE_PER_PERFORMING = 1.0
LGD = 3.0


def compute_metrics_at_threshold(y_true, y_prob, threshold, savings_mask, other_mask):
    """Compute FPR for each group at a threshold."""
    y_pred = (y_prob >= threshold).astype(int)

    # Savings group
    y_true_s = y_true[savings_mask]
    y_pred_s = y_pred[savings_mask]
    tn_s, fp_s, fn_s, tp_s = confusion_matrix(y_true_s, y_pred_s, labels=[0, 1]).ravel()
    fpr_s = fp_s / (fp_s + tn_s) if (fp_s + tn_s) > 0 else 0
    fnr_s = fn_s / (fn_s + tp_s) if (fn_s + tp_s) > 0 else 0

    # Other group
    y_true_o = y_true[other_mask]
    y_pred_o = y_pred[other_mask]
    tn_o, fp_o, fn_o, tp_o = confusion_matrix(y_true_o, y_pred_o, labels=[0, 1]).ravel()
    fpr_o = fp_o / (fp_o + tn_o) if (fp_o + tn_o) > 0 else 0
    fnr_o = fn_o / (fn_o + tp_o) if (fn_o + tp_o) > 0 else 0

    # Profit (overall)
    approved = y_pred == 0
    approved_defaults = (y_true == 1) & approved
    approved_performs = (y_true == 0) & approved
    profit = approved_performs.sum() * REVENUE_PER_PERFORMING - approved_defaults.sum() * LGD

    return {
        "threshold": round(float(threshold), 2),
        "fpr_savings": round(fpr_s, 4),
        "fpr_other": round(fpr_o, 4),
        "fpr_difference": round(fpr_s - fpr_o, 4),
        "fpr_ratio": round(fpr_s / fpr_o, 2) if fpr_o > 0 else None,
        "fnr_savings": round(fnr_s, 4),
        "fnr_other": round(fnr_o, 4),
        "profit": float(profit),
        "n_approved": int(approved.sum())
    }


def find_pareto_frontier_welfare(points, metric="fpr_difference"):
    """
    Find Pareto frontier over (profit, welfare metric).
    A point is dominated if another has MORE profit AND LESS harm.
    """
    frontier = []

    for p in points:
        dominated = False
        for q in points:
            # q dominates p if q has higher profit AND lower metric (less harm)
            if q["profit_pct"] > p["profit_pct"] and q[metric] < p[metric]:
                dominated = True
                break
        if not dominated:
            frontier.append(p)

    # Sort by profit descending
    frontier.sort(key=lambda x: -x["profit_pct"])
    return frontier


def main():
    print("=" * 60)
    print("T50: Corrected Fairness-Profit Analysis")
    print("=" * 60)
    print()

    # Load canonical split
    canonical_path = RESULTS_DIR / "canonical_split.json"
    if canonical_path.exists():
        with open(canonical_path) as f:
            canonical = json.load(f)
        print(f"Using canonical split: n={canonical['split_sizes']['test']}")
    else:
        print("WARNING: canonical_split.json not found, using default split")

    # Load data
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)

    feature_cols = feature_info["feature_sets"]["full"]["features"]
    X = df[feature_cols]
    y = df["target"]

    # Use canonical split indices if available
    if canonical_path.exists():
        test_indices = canonical["indices"]["test"]
        train_indices = canonical["indices"]["train"]
        X_train = X.loc[train_indices]
        X_test = X.loc[test_indices]
        y_train = y.loc[train_indices]
        y_test = y.loc[test_indices]
    else:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
        )
        test_indices = X_test.index.tolist()

    # Scale and train
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    model.fit(X_train_scaled, y_train)

    y_prob = model.predict_proba(X_test_scaled)[:, 1]
    y_true = y_test.values

    # Get demographics (drop duplicates to avoid row expansion)
    demo_df = pd.read_csv(DATA_DIR / "traindemographics.csv").drop_duplicates(subset=['customerid'])
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
    print(f"  Savings: {savings_mask.sum()} (disadvantaged group)")
    print(f"  Other: {other_mask.sum()}")
    print()

    # Sweep thresholds
    thresholds = np.arange(0.10, 0.90, 0.01)
    all_points = []

    for thresh in thresholds:
        metrics = compute_metrics_at_threshold(y_true, y_prob, thresh, savings_mask, other_mask)
        if metrics["fpr_ratio"] is not None:
            all_points.append(metrics)

    # Add profit percentage
    max_profit = max(p["profit"] for p in all_points)
    for p in all_points:
        p["profit_pct"] = round(100 * p["profit"] / max_profit, 1)

    # Find profit-optimal
    optimal = max(all_points, key=lambda x: x["profit"])

    print("=" * 60)
    print("THE T47 ERROR EXPLAINED")
    print("=" * 60)
    print()
    print("T47 recommended threshold 0.46 because FPR RATIO improves.")
    print("But look at what happens to the DISADVANTAGED GROUP (Savings):")
    print()
    print("| Threshold | Profit % | Savings FPR | Other FPR | Difference | Ratio |")
    print("|-----------|----------|-------------|-----------|------------|-------|")

    key_thresholds = [0.46, 0.50, 0.53, 0.59, 0.62]
    for t in key_thresholds:
        p = next((x for x in all_points if abs(x["threshold"] - t) < 0.005), None)
        if p:
            marker = " <-- T47 recommended" if t == 0.46 else (" <-- profit optimal" if t == 0.53 else "")
            print(f"| {p['threshold']:.2f}      | {p['profit_pct']:>8.1f} | {p['fpr_savings']:>11.1%} | {p['fpr_other']:>9.1%} | {p['fpr_difference']:>10.4f} | {p['fpr_ratio']:>5.2f}x |{marker}")

    print()
    print("PROBLEM: Moving 0.53 -> 0.46:")
    p_53 = next(x for x in all_points if abs(x["threshold"] - 0.53) < 0.005)
    p_46 = next(x for x in all_points if abs(x["threshold"] - 0.46) < 0.005)

    fpr_change = (p_46["fpr_savings"] - p_53["fpr_savings"]) / p_53["fpr_savings"] * 100
    diff_change = (p_46["fpr_difference"] - p_53["fpr_difference"]) / p_53["fpr_difference"] * 100

    print(f"  - Savings FPR WORSENS: {p_53['fpr_savings']:.1%} -> {p_46['fpr_savings']:.1%} ({fpr_change:+.0f}%)")
    print(f"  - FPR gap WIDENS: {p_53['fpr_difference']:.4f} -> {p_46['fpr_difference']:.4f} ({diff_change:+.0f}%)")
    print(f"  - Only the RATIO improves (because Other is harmed faster)")
    print()

    print("CORRECT DIRECTION: Moving 0.53 -> 0.62:")
    p_62 = next((x for x in all_points if abs(x["threshold"] - 0.62) < 0.005), None)
    if p_62:
        fpr_improve = (p_53["fpr_savings"] - p_62["fpr_savings"]) / p_53["fpr_savings"] * 100
        diff_improve = (p_53["fpr_difference"] - p_62["fpr_difference"]) / p_53["fpr_difference"] * 100
        print(f"  - Savings FPR IMPROVES: {p_53['fpr_savings']:.1%} -> {p_62['fpr_savings']:.1%} ({fpr_improve:+.0f}%)")
        print(f"  - FPR gap NARROWS: {p_53['fpr_difference']:.4f} -> {p_62['fpr_difference']:.4f} ({diff_improve:+.0f}%)")
        print(f"  - Profit cost: {100 - p_62['profit_pct']:.1f}%")

    # Find Pareto frontiers
    print("\n" + "=" * 60)
    print("CORRECTED PARETO FRONTIERS")
    print("=" * 60)

    # Frontier over (profit, FPR_savings) - minimize disadvantaged group harm
    pareto_fpr_savings = find_pareto_frontier_welfare(all_points, "fpr_savings")
    print(f"\nPareto frontier (profit vs Savings FPR): {len(pareto_fpr_savings)} points")

    # Frontier over (profit, FPR_difference) - minimize gap
    pareto_fpr_diff = find_pareto_frontier_welfare(all_points, "fpr_difference")
    print(f"Pareto frontier (profit vs FPR difference): {len(pareto_fpr_diff)} points")

    # Best points at various profit levels
    print("\n" + "=" * 60)
    print("CORRECTED EXCHANGE RATE ANALYSIS")
    print("=" * 60)

    print("\nBest fairness at each profit level (minimizing Savings FPR):")
    print("| Min Profit | Best Threshold | Savings FPR | FPR Diff | Profit % |")
    print("|------------|----------------|-------------|----------|----------|")

    for min_pct in [100, 95, 90, 85]:
        candidates = [p for p in all_points if p["profit_pct"] >= min_pct]
        if candidates:
            best = min(candidates, key=lambda x: x["fpr_savings"])
            print(f"| {min_pct:>10}% | {best['threshold']:>14.2f} | {best['fpr_savings']:>11.1%} | {best['fpr_difference']:>8.4f} | {best['profit_pct']:>8.1f}% |")

    # Corrected recommendation
    print("\n" + "=" * 60)
    print("CORRECTED RECOMMENDATION")
    print("=" * 60)

    # Find best within 90% profit
    high_profit = [p for p in all_points if p["profit_pct"] >= 90]
    best_welfare = min(high_profit, key=lambda x: x["fpr_savings"])

    print(f"\nWithin 90% of maximum profit, the fairness-optimal threshold is {best_welfare['threshold']:.2f}:")
    print(f"  Savings FPR: {best_welfare['fpr_savings']:.1%}")
    print(f"  Other FPR: {best_welfare['fpr_other']:.1%}")
    print(f"  FPR difference: {best_welfare['fpr_difference']:.4f}")
    print(f"  FPR ratio: {best_welfare['fpr_ratio']:.2f}x")
    print(f"  Profit: {best_welfare['profit_pct']:.1f}%")

    print(f"\nCompared to profit-optimal ({optimal['threshold']:.2f}):")
    savings_improvement = (optimal["fpr_savings"] - best_welfare["fpr_savings"]) / optimal["fpr_savings"] * 100
    diff_improvement = (optimal["fpr_difference"] - best_welfare["fpr_difference"]) / optimal["fpr_difference"] * 100
    print(f"  Savings FPR: {optimal['fpr_savings']:.1%} -> {best_welfare['fpr_savings']:.1%} ({savings_improvement:+.0f}%)")
    print(f"  FPR gap: {optimal['fpr_difference']:.4f} -> {best_welfare['fpr_difference']:.4f} ({diff_improvement:+.0f}%)")
    print(f"  Profit cost: {100 - best_welfare['profit_pct']:.1f}%")

    # Create plots
    print("\n" + "=" * 60)
    print("Creating corrected plots...")
    print("=" * 60)

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))

    # Plot 1: FPR absolute values vs threshold
    ax1 = axes[0, 0]
    sorted_points = sorted(all_points, key=lambda x: x["threshold"])
    thresholds_plot = [p["threshold"] for p in sorted_points]
    fpr_savings_plot = [p["fpr_savings"] for p in sorted_points]
    fpr_other_plot = [p["fpr_other"] for p in sorted_points]

    ax1.plot(thresholds_plot, fpr_savings_plot, 'b-', linewidth=2, label='Savings (disadvantaged)')
    ax1.plot(thresholds_plot, fpr_other_plot, 'g-', linewidth=2, label='Other')
    ax1.axvline(optimal["threshold"], color='red', linestyle='--', alpha=0.7, label=f'Profit-optimal ({optimal["threshold"]})')
    ax1.axvline(best_welfare["threshold"], color='purple', linestyle='--', alpha=0.7, label=f'Fairness-optimal >=90% ({best_welfare["threshold"]})')
    ax1.set_xlabel('Threshold')
    ax1.set_ylabel('False Positive Rate')
    ax1.set_title('Absolute FPR by Group\n(Lower = better for borrowers)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Plot 2: Profit vs Savings FPR (Pareto)
    ax2 = axes[0, 1]
    profits = [p["profit_pct"] for p in all_points]
    fpr_savings = [p["fpr_savings"] for p in all_points]
    ax2.scatter(profits, fpr_savings, c='lightblue', s=30, alpha=0.5, label='All thresholds')

    # Pareto frontier
    pareto_profits = [p["profit_pct"] for p in pareto_fpr_savings]
    pareto_fpr = [p["fpr_savings"] for p in pareto_fpr_savings]
    sorted_pareto = sorted(zip(pareto_profits, pareto_fpr), reverse=True)
    ax2.plot([p[0] for p in sorted_pareto], [p[1] for p in sorted_pareto],
             'r-o', linewidth=2, markersize=6, label='Pareto frontier')

    ax2.scatter([optimal["profit_pct"]], [optimal["fpr_savings"]],
               c='red', s=200, marker='*', zorder=5, label=f'Profit-optimal')
    ax2.scatter([best_welfare["profit_pct"]], [best_welfare["fpr_savings"]],
               c='purple', s=200, marker='D', zorder=5, label=f'Best welfare >=90%')

    ax2.set_xlabel('Profit (% of maximum)')
    ax2.set_ylabel('Savings FPR (disadvantaged group)')
    ax2.set_title('Corrected Fairness-Profit Trade-off\n(Lower FPR = better)')
    ax2.legend(loc='upper left')
    ax2.grid(True, alpha=0.3)
    ax2.invert_xaxis()

    # Plot 3: FPR difference vs threshold
    ax3 = axes[1, 0]
    fpr_diff_plot = [p["fpr_difference"] for p in sorted_points]
    ax3.plot(thresholds_plot, fpr_diff_plot, 'purple', linewidth=2)
    ax3.axvline(optimal["threshold"], color='red', linestyle='--', alpha=0.7)
    ax3.axvline(best_welfare["threshold"], color='blue', linestyle='--', alpha=0.7)
    ax3.axhline(0, color='gray', linestyle=':', alpha=0.5)
    ax3.set_xlabel('Threshold')
    ax3.set_ylabel('FPR Difference (Savings - Other)')
    ax3.set_title('FPR Gap vs Threshold\n(Closer to 0 = more equal)')
    ax3.grid(True, alpha=0.3)

    # Plot 4: The ratio trap visualization
    ax4 = axes[1, 1]
    fpr_ratio_plot = [p["fpr_ratio"] for p in sorted_points]

    ax4_twin = ax4.twinx()
    line1, = ax4.plot(thresholds_plot, fpr_savings_plot, 'b-', linewidth=2, label='Savings FPR (absolute)')
    line2, = ax4_twin.plot(thresholds_plot, fpr_ratio_plot, 'r--', linewidth=2, label='FPR Ratio')

    ax4.axvline(0.46, color='orange', linestyle=':', alpha=0.7, label='T47 recommendation (0.46)')
    ax4.axvline(optimal["threshold"], color='green', linestyle='--', alpha=0.7, label='Profit-optimal (0.53)')

    ax4.set_xlabel('Threshold')
    ax4.set_ylabel('Savings FPR (absolute)', color='blue')
    ax4_twin.set_ylabel('FPR Ratio', color='red')
    ax4.set_title('The Ratio Trap\nT47 followed ratio (red) but harmed Savings (blue)')

    # Combined legend
    lines = [line1, line2]
    labels = ['Savings FPR', 'FPR Ratio']
    ax4.legend(lines, labels, loc='upper right')
    ax4.grid(True, alpha=0.3)

    plt.tight_layout()
    plot_path = RESULTS_DIR / "fairness_corrected_t50.png"
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved to: {plot_path}")

    # Compile results
    results = {
        "timestamp": datetime.now().isoformat(),
        "task": "T50",
        "title": "Corrected Fairness-Profit Analysis",
        "canonical_test_size": len(y_true),
        "random_state": RANDOM_STATE,

        "t47_error": {
            "problem": "T47 used FPR RATIO as the fairness metric. This can recommend interventions that harm the disadvantaged group.",
            "example": {
                "t47_recommendation": "Move threshold 0.53 -> 0.46",
                "ratio_change": f"{p_53['fpr_ratio']:.2f}x -> {p_46['fpr_ratio']:.2f}x (looks better)",
                "savings_fpr_change": f"{p_53['fpr_savings']:.1%} -> {p_46['fpr_savings']:.1%} (WORSE)",
                "fpr_gap_change": f"{p_53['fpr_difference']:.4f} -> {p_46['fpr_difference']:.4f} (WIDER)"
            },
            "root_cause": "Ratio parity can be achieved by harming the favored group. If Other FPR drops from 10% to 2%, Savings FPR rising from 27% to 41% still improves the ratio."
        },

        "corrected_metrics": {
            "primary": "FPR for disadvantaged group (Savings) - tracks actual harm",
            "secondary": "FPR difference (Savings - Other) - tracks equality",
            "reported_but_not_driving": "FPR ratio"
        },

        "profit_optimal": {
            "threshold": optimal["threshold"],
            "profit_pct": optimal["profit_pct"],
            "fpr_savings": optimal["fpr_savings"],
            "fpr_other": optimal["fpr_other"],
            "fpr_difference": optimal["fpr_difference"],
            "fpr_ratio": optimal["fpr_ratio"]
        },

        "corrected_recommendation": {
            "threshold": best_welfare["threshold"],
            "profit_pct": best_welfare["profit_pct"],
            "fpr_savings": best_welfare["fpr_savings"],
            "fpr_other": best_welfare["fpr_other"],
            "fpr_difference": best_welfare["fpr_difference"],
            "fpr_ratio": best_welfare["fpr_ratio"],
            "improvement_vs_profit_optimal": {
                "savings_fpr_reduction": f"{savings_improvement:.0f}%",
                "fpr_gap_reduction": f"{diff_improvement:.0f}%",
                "profit_cost": f"{100 - best_welfare['profit_pct']:.1f}%"
            },
            "direction": "HIGHER thresholds (toward 0.62), not lower (0.46)"
        },

        "pareto_frontiers": {
            "profit_vs_savings_fpr": {
                "n_points": len(pareto_fpr_savings),
                "points": pareto_fpr_savings[:10]
            },
            "profit_vs_fpr_difference": {
                "n_points": len(pareto_fpr_diff),
                "points": pareto_fpr_diff[:10]
            }
        },

        "methodological_finding": (
            "Ratio-based fairness metrics (e.g., disparate impact ratio, FPR ratio) can recommend "
            "interventions that make the disadvantaged group worse off. A ratio improves when the "
            "favored group is harmed faster than the disadvantaged group. Welfare-based metrics "
            "(absolute rates, differences) should drive recommendations; ratios may be reported "
            "alongside but must never be the primary decision criterion."
        ),

        "all_points": all_points
    }

    output_path = RESULTS_DIR / "fairness_corrected_t50.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {output_path}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"\nT47 ERROR: Recommended 0.46 based on ratio, which HARMS Savings group.")
    print(f"CORRECT: Higher thresholds (toward 0.62) improve welfare.")
    print(f"\nAt profit-optimal ({optimal['threshold']}):")
    print(f"  Savings FPR: {optimal['fpr_savings']:.1%}")
    print(f"  FPR gap: {optimal['fpr_difference']:.4f}")
    print(f"\nAt fairness-optimal within 90% profit ({best_welfare['threshold']}):")
    print(f"  Savings FPR: {best_welfare['fpr_savings']:.1%} ({savings_improvement:+.0f}%)")
    print(f"  FPR gap: {best_welfare['fpr_difference']:.4f} ({diff_improvement:+.0f}%)")
    print(f"  Profit cost: {100 - best_welfare['profit_pct']:.1f}%")

    return results


if __name__ == "__main__":
    main()
