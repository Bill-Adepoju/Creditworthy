"""
T60: Full Fairness Table at Thresholds 0.53 and 0.62

Reports FPR, FNR, approval rate, and profit for both groups at both thresholds.

Addresses HANDOVER issue: T50's threshold 0.62 recommendation has consequences
that must be stated explicitly - fnr_other = 1.0 (every Other defaulter approved).
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"

RANDOM_STATE = 42

# Profit model (same as T47)
REVENUE_PER_PERFORMING = 1.0
LGD = 3.0


def compute_full_metrics(y_true, y_prob, threshold):
    """Compute FPR, FNR, TPR, TNR, approval rate, and confusion matrix."""
    y_pred = (y_prob >= threshold).astype(int)  # predict=1 means predicted default -> reject

    # Confusion matrix: TN, FP, FN, TP
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()

    # FPR = FP / (FP + TN) - non-defaulters wrongly classified as default -> wrongly rejected
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0

    # FNR = FN / (FN + TP) - defaulters wrongly classified as non-default -> wrongly approved
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0

    # TPR = TP / (TP + FN) - defaulters correctly classified as default -> correctly rejected
    tpr = tp / (fn + tp) if (fn + tp) > 0 else 0

    # TNR = TN / (TN + FP) - non-defaulters correctly classified as non-default -> correctly approved
    tnr = tn / (fp + tn) if (fp + tn) > 0 else 0

    # Approval rate = proportion predicted as non-default (pred=0)
    approval_rate = (tn + fn) / (tn + fp + fn + tp)

    # Rejection rate = proportion predicted as default (pred=1)
    rejection_rate = (fp + tp) / (tn + fp + fn + tp)

    return {
        'fpr': fpr,
        'fnr': fnr,
        'tpr': tpr,
        'tnr': tnr,
        'approval_rate': approval_rate,
        'rejection_rate': rejection_rate,
        'tn': int(tn),
        'fp': int(fp),
        'fn': int(fn),
        'tp': int(tp)
    }


def compute_profit(y_true, y_prob, threshold):
    """
    Compute profit using the same model as T47.
    y_pred=0 -> approve (model predicts non-default)
    y_pred=1 -> reject (model predicts default)
    """
    y_pred = (y_prob >= threshold).astype(int)

    # Approved borrowers (pred=0)
    approved_mask = y_pred == 0

    # Among approved: performers (true=0) and defaulters (true=1)
    approved_performers = np.sum((y_true == 0) & approved_mask)
    approved_defaulters = np.sum((y_true == 1) & approved_mask)

    profit = approved_performers * REVENUE_PER_PERFORMING - approved_defaulters * LGD

    return {
        'profit': profit,
        'n_approved': int(np.sum(approved_mask)),
        'approved_performers': int(approved_performers),
        'approved_defaulters': int(approved_defaulters)
    }


def main():
    print("=" * 70)
    print("T60: Full Fairness Table at Thresholds 0.53 and 0.62")
    print("=" * 70)
    print()

    # Load canonical split
    canonical_path = RESULTS_DIR / "canonical_split.json"
    with open(canonical_path) as f:
        canonical = json.load(f)

    # Load data
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)

    feature_cols = feature_info["feature_sets"]["full"]["features"]
    X = df[feature_cols]
    y = df["target"]

    # Use canonical split
    train_indices = canonical["indices"]["train"]
    test_indices = canonical["indices"]["test"]

    X_train = X.iloc[train_indices]
    X_test = X.iloc[test_indices]
    y_train = y.iloc[train_indices]
    y_test = y.iloc[test_indices]

    # Scale and train model
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    model.fit(X_train_scaled, y_train)

    y_prob = model.predict_proba(X_test_scaled)[:, 1]

    # Get demographics (drop duplicates per T55)
    demo_df = pd.read_csv(DATA_DIR / "traindemographics.csv").drop_duplicates(subset=['customerid'])

    test_df = pd.DataFrame({
        "y_true": y_test.values,
        "y_prob": y_prob,
        "customerid": df.iloc[test_indices]["customerid"].values
    })
    test_df = test_df.merge(demo_df[['customerid', 'bank_account_type']], on="customerid", how="left")

    savings_mask = test_df["bank_account_type"] == "Savings"
    other_mask = test_df["bank_account_type"] == "Other"

    y_true_s = test_df.loc[savings_mask, "y_true"].values
    y_prob_s = test_df.loc[savings_mask, "y_prob"].values
    y_true_o = test_df.loc[other_mask, "y_true"].values
    y_prob_o = test_df.loc[other_mask, "y_prob"].values

    print(f"Groups: Savings n={len(y_true_s)}, Other n={len(y_true_o)}")
    print(f"Base rates: Savings={y_true_s.mean():.1%}, Other={y_true_o.mean():.1%}")
    print()

    # Thresholds to evaluate
    thresholds = [0.53, 0.62]

    results = {
        "timestamp": datetime.now().isoformat(),
        "task": "T60",
        "title": "Full Fairness Table at Key Thresholds",
        "thresholds_evaluated": thresholds,
        "profit_model": {
            "revenue_per_performing": REVENUE_PER_PERFORMING,
            "loss_given_default": LGD
        },
        "base_rates": {
            "savings": {"n": len(y_true_s), "default_rate": round(float(y_true_s.mean()), 4)},
            "other": {"n": len(y_true_o), "default_rate": round(float(y_true_o.mean()), 4)}
        },
        "threshold_comparison": []
    }

    # Create comparison table
    print("=" * 90)
    print("FULL COMPARISON TABLE")
    print("=" * 90)
    print()
    print("| Threshold | Group   | FPR      | FNR      | Approval | Rejected | Profit |")
    print("|-----------|---------|----------|----------|----------|----------|--------|")

    for threshold in thresholds:
        # Overall metrics
        metrics_all = compute_full_metrics(y_test.values, y_prob, threshold)
        profit_all = compute_profit(y_test.values, y_prob, threshold)

        # Savings
        metrics_s = compute_full_metrics(y_true_s, y_prob_s, threshold)
        profit_s = compute_profit(y_true_s, y_prob_s, threshold)

        # Other
        metrics_o = compute_full_metrics(y_true_o, y_prob_o, threshold)
        profit_o = compute_profit(y_true_o, y_prob_o, threshold)

        # Print table rows
        print(f"| {threshold:.2f}      | Savings | {metrics_s['fpr']:.1%}    | {metrics_s['fnr']:.1%}    | {metrics_s['approval_rate']:.1%}    | {metrics_s['rejection_rate']:.1%}    | {profit_s['profit']:6.0f} |")
        print(f"| {threshold:.2f}      | Other   | {metrics_o['fpr']:.1%}    | {metrics_o['fnr']:.1%}    | {metrics_o['approval_rate']:.1%}    | {metrics_o['rejection_rate']:.1%}    | {profit_o['profit']:6.0f} |")
        print(f"| {threshold:.2f}      | OVERALL | {metrics_all['fpr']:.1%}    | {metrics_all['fnr']:.1%}    | {metrics_all['approval_rate']:.1%}    | {metrics_all['rejection_rate']:.1%}    | {profit_all['profit']:6.0f} |")
        print("|-----------|---------|----------|----------|----------|----------|--------|")

        threshold_result = {
            "threshold": threshold,
            "savings": {
                "fpr": round(metrics_s['fpr'], 4),
                "fnr": round(metrics_s['fnr'], 4),
                "approval_rate": round(metrics_s['approval_rate'], 4),
                "rejection_rate": round(metrics_s['rejection_rate'], 4),
                "profit": profit_s['profit'],
                "n_approved": profit_s['n_approved'],
                "confusion_matrix": {"tn": metrics_s['tn'], "fp": metrics_s['fp'], "fn": metrics_s['fn'], "tp": metrics_s['tp']}
            },
            "other": {
                "fpr": round(metrics_o['fpr'], 4),
                "fnr": round(metrics_o['fnr'], 4),
                "approval_rate": round(metrics_o['approval_rate'], 4),
                "rejection_rate": round(metrics_o['rejection_rate'], 4),
                "profit": profit_o['profit'],
                "n_approved": profit_o['n_approved'],
                "confusion_matrix": {"tn": metrics_o['tn'], "fp": metrics_o['fp'], "fn": metrics_o['fn'], "tp": metrics_o['tp']}
            },
            "overall": {
                "fpr": round(metrics_all['fpr'], 4),
                "fnr": round(metrics_all['fnr'], 4),
                "approval_rate": round(metrics_all['approval_rate'], 4),
                "rejection_rate": round(metrics_all['rejection_rate'], 4),
                "profit": profit_all['profit'],
                "n_approved": profit_all['n_approved']
            }
        }

        results["threshold_comparison"].append(threshold_result)

    print()

    # Key findings
    t053 = results["threshold_comparison"][0]
    t062 = results["threshold_comparison"][1]

    print("=" * 70)
    print("KEY FINDINGS")
    print("=" * 70)
    print()

    print("At threshold 0.53 (profit-optimal):")
    print(f"  Savings: FPR={t053['savings']['fpr']:.1%}, FNR={t053['savings']['fnr']:.1%}")
    print(f"  Other:   FPR={t053['other']['fpr']:.1%}, FNR={t053['other']['fnr']:.1%}")
    print(f"  FPR ratio: {t053['savings']['fpr']/t053['other']['fpr']:.2f}x")
    print()

    print("At threshold 0.62 (T50 recommended for fairness):")
    print(f"  Savings: FPR={t062['savings']['fpr']:.1%}, FNR={t062['savings']['fnr']:.1%}")
    print(f"  Other:   FPR={t062['other']['fpr']:.1%}, FNR={t062['other']['fnr']:.1%}")
    print(f"  FPR ratio: {t062['savings']['fpr']/t062['other']['fpr']:.2f}x")
    print()

    # Check for fnr_other = 1.0
    if t062['other']['fnr'] >= 0.99:
        print("*** CRITICAL: At threshold 0.62, FNR_Other = 100% ***")
        print("    Every Other defaulter is APPROVED (wrongly).")
        print("    This is a consequence of the fairness optimization.")
        print()

    # Profit trade-off
    profit_053 = t053['overall']['profit']
    profit_062 = t062['overall']['profit']
    profit_cost = profit_053 - profit_062
    profit_cost_pct = (profit_cost / profit_053) * 100 if profit_053 > 0 else 0

    print(f"Profit trade-off:")
    print(f"  At 0.53: {profit_053:.0f}")
    print(f"  At 0.62: {profit_062:.0f}")
    print(f"  Cost of fairness: {profit_cost:.0f} ({profit_cost_pct:.1f}%)")
    print()

    # FNR change
    fnr_s_change = t062['savings']['fnr'] - t053['savings']['fnr']
    fnr_o_change = t062['other']['fnr'] - t053['other']['fnr']

    print(f"FNR changes (0.53 -> 0.62):")
    print(f"  Savings: {t053['savings']['fnr']:.1%} -> {t062['savings']['fnr']:.1%} (+{fnr_s_change:.1%})")
    print(f"  Other:   {t053['other']['fnr']:.1%} -> {t062['other']['fnr']:.1%} (+{fnr_o_change:.1%})")
    print()

    # Add findings to results
    results["findings"] = {
        "fnr_other_at_062": round(t062['other']['fnr'], 4),
        "fnr_other_critical": bool(t062['other']['fnr'] >= 0.99),
        "fnr_other_explanation": "At threshold 0.62, FNR_Other = 100% means every Other defaulter is approved. This is a consequence of the fairness optimization.",
        "profit_cost": {
            "absolute": profit_cost,
            "percentage": round(profit_cost_pct, 1)
        },
        "fnr_changes": {
            "savings_053_to_062": round(fnr_s_change, 4),
            "other_053_to_062": round(fnr_o_change, 4)
        },
        "defensibility": "This trade is defensible under a financial-inclusion objective where wrongly rejecting creditworthy borrowers (high FPR) is the harm being minimized. However, the high FNR for Other borrowers increases default exposure."
    }

    # Save results
    output_path = RESULTS_DIR / "fairness_full_table_t60.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to: {output_path}")

    return results


if __name__ == "__main__":
    main()
