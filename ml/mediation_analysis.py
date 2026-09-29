"""
T30: Mediation Check on bank_account_type

The 3.0x disparity in bank_account_type (Savings 44.7% vs Other 14.7%)
is the dissertation's most striking fairness finding. Before recommending
a remedy, we must determine if it's causal or confounded.

This script:
1. Correlates bank_account_type with other features
2. Refits WITHOUT bank_account_type and measures disparity in outcomes
3. Reports which features mediate the disparity
"""
import numpy as np
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from scipy import stats

RESULTS_DIR = Path(__file__).parent.parent / "results"
DATA_DIR = Path(__file__).parent.parent / "data"


def load_data():
    """Load features and demographics."""
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    demo = pd.read_csv(DATA_DIR / "traindemographics.csv")
    return df, demo


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


def compute_disparity(y_true, y_pred_proba, group_labels, pos_group, neg_group):
    """Compute selection disparity between two groups."""
    pos_mask = group_labels == pos_group
    neg_mask = group_labels == neg_group

    if pos_mask.sum() < 30 or neg_mask.sum() < 30:
        return None, None, None

    # Use a fixed threshold at median probability
    threshold = np.median(y_pred_proba)

    # Selection rates
    pos_rate = (y_pred_proba[pos_mask] >= threshold).mean()
    neg_rate = (y_pred_proba[neg_mask] >= threshold).mean()

    ratio = pos_rate / neg_rate if neg_rate > 0 else float('inf')

    return pos_rate, neg_rate, ratio


def main():
    print("=== T30: Mediation Check on bank_account_type ===\n")

    # Load data
    df, demo = load_data()

    print(f"Dataset: {len(df)} samples")

    # Extract bank_account_type
    bank_type = extract_bank_account_type(df)
    df["bank_account_type"] = bank_type

    # Check distribution
    print("\nbank_account_type distribution:")
    type_counts = bank_type.value_counts()
    for t, c in type_counts.items():
        print(f"  {t}: {c} ({100*c/len(df):.1f}%)")

    # Target and features
    target_col = "target"
    exclude_cols = ["customerid", "good_bad_flag", target_col, "bank_account_type"]
    feature_cols = [c for c in df.columns if c not in exclude_cols]

    X = df[feature_cols].copy()
    y = df[target_col].copy()
    bank_type_series = df["bank_account_type"].copy()

    # Fill NaN
    for col in X.columns:
        if X[col].dtype in ["float64", "int64", "bool"]:
            X[col] = X[col].fillna(X[col].median())

    # Convert bool to int
    for col in X.select_dtypes(include=["bool"]).columns:
        X[col] = X[col].astype(int)

    # Split
    X_train, X_test, y_train, y_test, bank_train, bank_test = train_test_split(
        X, y, bank_type_series, test_size=0.2, random_state=42, stratify=y
    )

    results = {
        "timestamp": datetime.now().isoformat(),
        "n_samples": len(df),
        "bank_type_distribution": type_counts.to_dict(),
        "correlation_analysis": {},
        "model_with_bank_type": {},
        "model_without_bank_type": {},
        "mediation_analysis": {},
        "conclusion": {}
    }

    # Part 1: Correlation analysis
    print("\n" + "=" * 80)
    print("PART 1: CORRELATION ANALYSIS")
    print("=" * 80)

    # Numeric features to correlate with bank_account_type
    numeric_features = [
        "relationship_tenure_days",
        "loan_count",
        "amount_mean",
        "amount_total",
        "age"
    ]

    correlations = {}
    print("\nCorrelation of bank_account_type with other features:")
    print(f"(Using point-biserial for Savings vs non-Savings)")
    print()

    # Create binary: Savings vs Others
    is_savings = (bank_type == "Savings").astype(int)

    for feat in numeric_features:
        if feat in df.columns:
            valid = df[feat].notna() & is_savings.notna()
            r, p = stats.pointbiserialr(is_savings[valid], df[feat][valid])
            correlations[feat] = {"r": float(r), "p": float(p)}
            sig = "*" if p < 0.05 else ""
            print(f"  {feat}: r={r:.3f}, p={p:.4f} {sig}")

    results["correlation_analysis"]["savings_vs_others"] = correlations

    # Part 2: Model WITH bank_account_type
    print("\n" + "=" * 80)
    print("PART 2: MODEL WITH bank_account_type")
    print("=" * 80)

    model_with = LogisticRegression(max_iter=2000, random_state=42, class_weight="balanced")
    model_with.fit(X_train, y_train)
    proba_with = model_with.predict_proba(X_test)[:, 1]

    # Compute disparity
    savings_rate_with, other_rate_with, ratio_with = compute_disparity(
        y_test.values, proba_with, bank_test.values, "Savings", "Other"
    )

    print(f"\nSelection rates (with bank_account_type features):")
    print(f"  Savings: {100*savings_rate_with:.1f}%")
    print(f"  Other:   {100*other_rate_with:.1f}%")
    print(f"  Ratio:   {ratio_with:.2f}x")

    results["model_with_bank_type"] = {
        "savings_selection_rate": float(savings_rate_with),
        "other_selection_rate": float(other_rate_with),
        "ratio": float(ratio_with)
    }

    # Part 3: Model WITHOUT bank_account_type
    print("\n" + "=" * 80)
    print("PART 3: MODEL WITHOUT bank_account_type")
    print("=" * 80)

    # Remove bank_account_type columns
    bank_cols = [c for c in X_train.columns if "bank_account_type" in c]
    X_train_no_bank = X_train.drop(columns=bank_cols)
    X_test_no_bank = X_test.drop(columns=bank_cols)

    print(f"Removed {len(bank_cols)} bank_account_type columns")

    model_without = LogisticRegression(max_iter=2000, random_state=42, class_weight="balanced")
    model_without.fit(X_train_no_bank, y_train)
    proba_without = model_without.predict_proba(X_test_no_bank)[:, 1]

    # Compute disparity
    savings_rate_without, other_rate_without, ratio_without = compute_disparity(
        y_test.values, proba_without, bank_test.values, "Savings", "Other"
    )

    print(f"\nSelection rates (without bank_account_type features):")
    print(f"  Savings: {100*savings_rate_without:.1f}%")
    print(f"  Other:   {100*other_rate_without:.1f}%")
    print(f"  Ratio:   {ratio_without:.2f}x")

    results["model_without_bank_type"] = {
        "savings_selection_rate": float(savings_rate_without),
        "other_selection_rate": float(other_rate_without),
        "ratio": float(ratio_without)
    }

    # Part 4: Mediation analysis
    print("\n" + "=" * 80)
    print("PART 4: MEDIATION ANALYSIS")
    print("=" * 80)

    disparity_with = ratio_with
    disparity_without = ratio_without

    disparity_change = (disparity_with - disparity_without) / disparity_with * 100

    print(f"\nDisparity ratio with bank_type:    {disparity_with:.2f}x")
    print(f"Disparity ratio without bank_type: {disparity_without:.2f}x")
    print(f"Change: {disparity_change:+.1f}%")

    if abs(disparity_change) < 20:
        mediation_conclusion = "confounded"
        explanation = (
            "Removing bank_account_type barely affects the disparity. "
            "The 3.0x gap is carried by correlated features (tenure, loan history, etc.), "
            "not by the account type label itself. Dropping the feature will NOT fix the disparity."
        )
    else:
        mediation_conclusion = "partially_causal"
        explanation = (
            f"Removing bank_account_type changes the disparity by {abs(disparity_change):.0f}%. "
            "The feature contributes directly to the prediction, but some disparity remains. "
            "A hybrid approach (fairness constraint + feature removal) may be needed."
        )

    print(f"\nConclusion: {mediation_conclusion.upper()}")
    print(f"\n{explanation}")

    results["mediation_analysis"] = {
        "disparity_with_feature": float(disparity_with),
        "disparity_without_feature": float(disparity_without),
        "change_percent": float(disparity_change),
        "conclusion": mediation_conclusion,
        "explanation": explanation
    }

    # Part 5: Which features mediate most strongly?
    print("\n" + "=" * 80)
    print("PART 5: FEATURE IMPORTANCE FOR DISPARITY")
    print("=" * 80)

    # Get feature importance from model
    feature_importance = dict(zip(X_train_no_bank.columns, model_without.coef_[0]))

    # Sort by absolute importance
    sorted_features = sorted(feature_importance.items(), key=lambda x: abs(x[1]), reverse=True)

    print("\nTop 10 features by coefficient magnitude (excluding bank_account_type):")
    for i, (feat, coef) in enumerate(sorted_features[:10], 1):
        print(f"  {i:2d}. {feat}: {coef:+.4f}")

    results["mediation_analysis"]["top_features"] = [
        {"feature": feat, "coefficient": float(coef)}
        for feat, coef in sorted_features[:10]
    ]

    # Overall conclusion
    results["conclusion"] = {
        "is_causal": mediation_conclusion == "partially_causal",
        "recommendation": (
            "The disparity is structural (confounded) - dropping bank_account_type alone "
            "will not eliminate the 3.0x gap. Chapter 6 should recommend either: "
            "(1) fairness constraints during training, or (2) post-hoc calibration by group."
        ) if mediation_conclusion == "confounded" else (
            "The feature contributes directly to disparity. Consider removing it and "
            "applying fairness constraints to residual correlated features."
        ),
        "chapter_6_framing": (
            "The disparity is carried by correlated features and cannot be engineered away "
            "by simple feature removal. This is a structural limitation of the data."
        ) if mediation_conclusion == "confounded" else (
            "A combination of feature removal and fairness constraints can reduce the disparity."
        )
    }

    print("\n" + "=" * 80)
    print("CHAPTER 6 RECOMMENDATION")
    print("=" * 80)
    print(f"\n{results['conclusion']['recommendation']}")

    # Save results
    output_path = RESULTS_DIR / "mediation_analysis.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_path}")

    # Append to SUMMARY.md
    summary_path = RESULTS_DIR / "SUMMARY.md"
    summary_entry = f"""
### mediation_analysis - {datetime.now().strftime('%Y-%m-%d')}
**What was run:** T30 mediation check on bank_account_type disparity.
**Why:** Determine if 3.0x disparity is causal or confounded before recommending remedies.
**Key numbers:**

| Model | Savings Rate | Other Rate | Ratio |
|-------|--------------|------------|-------|
| With bank_type | {100*savings_rate_with:.1f}% | {100*other_rate_with:.1f}% | {ratio_with:.2f}x |
| Without bank_type | {100*savings_rate_without:.1f}% | {100*other_rate_without:.1f}% | {ratio_without:.2f}x |

Disparity change: {disparity_change:+.1f}%

**Conclusion:** {mediation_conclusion.upper()}. {explanation}
"""

    with open(summary_path, "a") as f:
        f.write(summary_entry)
    print(f"Summary appended to {summary_path}")


if __name__ == "__main__":
    main()
