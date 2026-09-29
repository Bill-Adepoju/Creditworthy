"""
T41: Re-express fairness with corrected direction

Now that positive = default is confirmed, regenerate fairness outputs as a lender would read them.

Key changes:
1. Report APPROVAL rates, not selection rates
2. Make FPR the headline metric (creditworthy borrowers wrongly rejected)
3. Account for differing base rates by group
4. Report FPR, FNR, TPR, approval rate per subgroup (n >= 30)
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

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"

RANDOM_STATE = 42
MIN_SUBGROUP_SIZE = 30


def load_data():
    """Load processed features."""
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)
    return df, feature_info


def compute_group_metrics(y_true, y_pred, group_name):
    """
    Compute fairness metrics for a group.

    IMPORTANT: positive class = default (target=1)

    Metrics computed:
    - Approval rate: 1 - prediction rate (pred=0 means approved)
    - Actual default rate: proportion who actually defaulted
    - FPR: False Positive Rate = FP / (FP + TN) = wrongly predicted defaults among non-defaulters
          In lending context: creditworthy borrowers wrongly REJECTED
    - FNR: False Negative Rate = FN / (FN + TP) = missed defaults among actual defaulters
    - TPR: True Positive Rate = TP / (TP + FN) = correctly identified defaults
    """
    n = len(y_true)

    # Confusion matrix: [[TN, FP], [FN, TP]]
    # TN = actual=0, pred=0 (non-defaulter correctly approved)
    # FP = actual=0, pred=1 (non-defaulter wrongly rejected)
    # FN = actual=1, pred=0 (defaulter wrongly approved)
    # TP = actual=1, pred=1 (defaulter correctly rejected)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()

    # Actual default rate
    actual_default_rate = y_true.sum() / n if n > 0 else 0

    # Approval rate (pred=0 means approved, pred=1 means rejected)
    approval_rate = (y_pred == 0).sum() / n if n > 0 else 0

    # FPR: Among non-defaulters (actual=0), what fraction was wrongly rejected (pred=1)?
    # This is the key fairness metric: creditworthy people wrongly denied
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0

    # FNR: Among defaulters (actual=1), what fraction was wrongly approved (pred=0)?
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0

    # TPR: Among defaulters (actual=1), what fraction was correctly rejected (pred=1)?
    tpr = tp / (fn + tp) if (fn + tp) > 0 else 0

    # TNR: Among non-defaulters (actual=0), what fraction was correctly approved (pred=0)?
    tnr = tn / (fp + tn) if (fp + tn) > 0 else 0

    return {
        "group": group_name,
        "n": n,
        "actual_default_rate": round(actual_default_rate, 4),
        "approval_rate": round(approval_rate, 4),
        "rejection_rate": round(1 - approval_rate, 4),
        "fpr_creditworthy_rejected": round(fpr, 4),
        "fnr_defaulters_approved": round(fnr, 4),
        "tpr_defaulters_caught": round(tpr, 4),
        "tnr_creditworthy_approved": round(tnr, 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}
    }


def main():
    print("=" * 60)
    print("T41: Fairness Re-expression with Corrected Direction")
    print("=" * 60)
    print()
    print("POSITIVE CLASS = DEFAULT (target=1)")
    print("FPR = creditworthy borrowers wrongly REJECTED")
    print()

    df, feature_info = load_data()

    # Use full feature set
    feature_cols = feature_info["feature_sets"]["full"]["features"]
    X = df[feature_cols]
    y = df["target"]

    # Train/test split (same as other analyses)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE
    )

    # Scale and train model
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    model.fit(X_train_scaled, y_train)

    y_pred = model.predict(X_test_scaled)

    # Get test set indices for demographic lookup
    test_indices = X_test.index

    # Load demographics
    demo_df = pd.read_csv(DATA_DIR / "traindemographics.csv")

    # Create test dataframe with demographics
    test_df = pd.DataFrame({
        "y_true": y_test.values,
        "y_pred": y_pred,
        "customerid": df.loc[test_indices, "customerid"].values
    })

    # Merge demographics
    test_df = test_df.merge(demo_df, on="customerid", how="left")

    # Define sensitive attributes
    sensitive_attrs = {
        "bank_account_type": test_df["bank_account_type"].fillna("Unknown"),
        "employment_status_clients": test_df["employment_status_clients"].fillna("Unknown")
    }

    # Also compute age bands from birthdate if available
    if "birthdate" in demo_df.columns:
        # This was already computed in features, get from original df
        pass

    results = {
        "timestamp": datetime.now().isoformat(),
        "task": "T41",
        "positive_class": "DEFAULT (target=1)",
        "key_metric": "FPR = creditworthy borrowers wrongly rejected",
        "model": "LogisticRegression (class_weight=balanced)",
        "test_set_size": len(test_df),
        "overall_default_rate": round(y_test.mean(), 4),
        "subgroup_analysis": {}
    }

    print(f"Test set size: {len(test_df)}")
    print(f"Overall default rate: {y_test.mean():.1%}")
    print()

    # Analyze each sensitive attribute
    for attr_name, attr_values in sensitive_attrs.items():
        print(f"\n{'='*60}")
        print(f"Attribute: {attr_name}")
        print(f"{'='*60}")

        test_df[f"_{attr_name}"] = attr_values.values

        groups = attr_values.unique()
        attr_results = []

        print(f"\n| Group | N | Default | Approval | FPR (wrongly rejected) | FNR |")
        print(f"|-------|---|---------|----------|------------------------|-----|")

        for group in sorted(groups, key=lambda x: str(x)):
            mask = attr_values == group
            if mask.sum() < MIN_SUBGROUP_SIZE:
                continue

            metrics = compute_group_metrics(
                test_df.loc[mask, "y_true"].values,
                test_df.loc[mask, "y_pred"].values,
                str(group)
            )
            attr_results.append(metrics)

            print(f"| {group:15} | {metrics['n']:3} | {metrics['actual_default_rate']:.1%} | "
                  f"{metrics['approval_rate']:.1%} | {metrics['fpr_creditworthy_rejected']:.1%} | "
                  f"{metrics['fnr_defaulters_approved']:.1%} |")

        # Compute disparity
        if len(attr_results) >= 2:
            # Find highest and lowest FPR groups
            sorted_by_fpr = sorted(attr_results, key=lambda x: x["fpr_creditworthy_rejected"])
            lowest_fpr = sorted_by_fpr[0]
            highest_fpr = sorted_by_fpr[-1]

            fpr_ratio = (highest_fpr["fpr_creditworthy_rejected"] /
                        lowest_fpr["fpr_creditworthy_rejected"]
                        if lowest_fpr["fpr_creditworthy_rejected"] > 0 else float('inf'))

            fpr_diff = highest_fpr["fpr_creditworthy_rejected"] - lowest_fpr["fpr_creditworthy_rejected"]

            disparity = {
                "highest_fpr_group": highest_fpr["group"],
                "highest_fpr_value": highest_fpr["fpr_creditworthy_rejected"],
                "lowest_fpr_group": lowest_fpr["group"],
                "lowest_fpr_value": lowest_fpr["fpr_creditworthy_rejected"],
                "fpr_ratio": round(fpr_ratio, 2),
                "fpr_difference": round(fpr_diff, 4),
                "interpretation": f"{highest_fpr['group']} borrowers who would repay are rejected at "
                                 f"{fpr_ratio:.1f}x the rate of {lowest_fpr['group']} borrowers"
            }

            print(f"\nDisparity: {highest_fpr['group']} has {fpr_ratio:.1f}x higher FPR than {lowest_fpr['group']}")
            print(f"  {highest_fpr['group']}: {highest_fpr['fpr_creditworthy_rejected']:.1%} creditworthy rejected")
            print(f"  {lowest_fpr['group']}: {lowest_fpr['fpr_creditworthy_rejected']:.1%} creditworthy rejected")

            # Note about base rate differences
            dr_high = highest_fpr["actual_default_rate"]
            dr_low = lowest_fpr["actual_default_rate"]
            print(f"\nBase rate context:")
            print(f"  {highest_fpr['group']} actual default rate: {dr_high:.1%}")
            print(f"  {lowest_fpr['group']} actual default rate: {dr_low:.1%}")
            if dr_high > dr_low:
                print(f"  {highest_fpr['group']} has {dr_high/dr_low:.1f}x higher default rate")
                print(f"  Some FPR disparity may be justified by genuine risk differences")
        else:
            disparity = None

        results["subgroup_analysis"][attr_name] = {
            "groups": attr_results,
            "disparity": disparity,
            "min_subgroup_size": MIN_SUBGROUP_SIZE
        }

    # Summary for bank_account_type specifically (key finding)
    if "bank_account_type" in results["subgroup_analysis"]:
        ba_analysis = results["subgroup_analysis"]["bank_account_type"]
        savings = next((g for g in ba_analysis["groups"] if g["group"] == "Savings"), None)
        other = next((g for g in ba_analysis["groups"] if g["group"] == "Other"), None)

        if savings and other:
            results["headline_finding"] = {
                "attribute": "bank_account_type",
                "disadvantaged_group": "Savings",
                "savings_fpr": savings["fpr_creditworthy_rejected"],
                "other_fpr": other["fpr_creditworthy_rejected"],
                "fpr_ratio": round(savings["fpr_creditworthy_rejected"] / other["fpr_creditworthy_rejected"], 2) if other["fpr_creditworthy_rejected"] > 0 else None,
                "savings_default_rate": savings["actual_default_rate"],
                "other_default_rate": other["actual_default_rate"],
                "interpretation": (
                    f"Savings holders who would repay are rejected at "
                    f"{savings['fpr_creditworthy_rejected']:.1%} vs {other['fpr_creditworthy_rejected']:.1%} for Other holders. "
                    f"This {savings['fpr_creditworthy_rejected']/other['fpr_creditworthy_rejected']:.1f}x disparity persists even though "
                    f"Savings holders have genuinely higher default rates ({savings['actual_default_rate']:.1%} vs {other['actual_default_rate']:.1%})."
                )
            }

            print("\n" + "="*60)
            print("HEADLINE FINDING (bank_account_type)")
            print("="*60)
            print(f"Savings FPR: {savings['fpr_creditworthy_rejected']:.1%} (creditworthy rejected)")
            print(f"Other FPR: {other['fpr_creditworthy_rejected']:.1%} (creditworthy rejected)")
            if other["fpr_creditworthy_rejected"] > 0:
                print(f"Ratio: {savings['fpr_creditworthy_rejected']/other['fpr_creditworthy_rejected']:.1f}x")
            print(f"\nBase rate context:")
            print(f"  Savings default rate: {savings['actual_default_rate']:.1%}")
            print(f"  Other default rate: {other['actual_default_rate']:.1%}")

    # Save results
    output_path = RESULTS_DIR / "fairness_corrected.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n\nResults saved to: {output_path}")
    return results


if __name__ == "__main__":
    main()
