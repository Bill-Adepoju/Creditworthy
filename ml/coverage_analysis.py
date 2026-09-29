"""
T11: Join Coverage and Missing-History Analysis

Critical question: Is the FS_regularity > FS_magnitude finding robust,
or is it an artifact of missingness patterns?

Key analyses:
1. How many customers appear in all three tables vs only some?
2. Distribution of prior-loan counts per customer (n<2 undefined for some features)
3. How were nulls handled - imputed, dropped, flagged?
4. Re-run comparison on customers with >=3 prior loans
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings("ignore")

from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score
from scipy.stats import ttest_rel

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"

RANDOM_STATE = 42
N_FOLDS = 5


def load_raw_data():
    """Load all raw dataset tables."""
    perf = pd.read_csv(DATA_DIR / "trainperf.csv")
    prevloans = pd.read_csv(DATA_DIR / "trainprevloans.csv")
    demographics = pd.read_csv(DATA_DIR / "traindemographics.csv")
    return perf, prevloans, demographics


def load_features():
    """Load processed features and feature set definitions."""
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)
    return df, feature_info


def analyze_table_coverage(perf, prevloans, demographics):
    """Analyze how many customers appear in each table combination."""
    perf_ids = set(perf["customerid"].unique())
    prev_ids = set(prevloans["customerid"].unique())
    demo_ids = set(demographics["customerid"].unique())

    coverage = {
        "perf_total": len(perf_ids),
        "prevloans_unique_customers": len(prev_ids),
        "demographics_total": len(demo_ids),
        "all_three": len(perf_ids & prev_ids & demo_ids),
        "perf_and_prev_only": len((perf_ids & prev_ids) - demo_ids),
        "perf_and_demo_only": len((perf_ids & demo_ids) - prev_ids),
        "perf_only_no_history": len(perf_ids - prev_ids - demo_ids),
        "perf_no_prev_history": len(perf_ids - prev_ids),
    }

    return coverage


def analyze_loan_history_distribution(prevloans, perf):
    """Analyze distribution of prior loans per customer."""
    loan_counts = prevloans.groupby("customerid").size().reset_index(name="n_prior_loans")

    # Merge with perf to get all customers
    all_customers = perf[["customerid"]].drop_duplicates()
    loan_counts = all_customers.merge(loan_counts, on="customerid", how="left")
    loan_counts["n_prior_loans"] = loan_counts["n_prior_loans"].fillna(0).astype(int)

    distribution = {
        "total_customers": len(loan_counts),
        "n_with_0_prior": int((loan_counts["n_prior_loans"] == 0).sum()),
        "n_with_1_prior": int((loan_counts["n_prior_loans"] == 1).sum()),
        "n_with_2_prior": int((loan_counts["n_prior_loans"] == 2).sum()),
        "n_with_3plus_prior": int((loan_counts["n_prior_loans"] >= 3).sum()),
        "mean_prior_loans": float(loan_counts["n_prior_loans"].mean()),
        "median_prior_loans": float(loan_counts["n_prior_loans"].median()),
        "max_prior_loans": int(loan_counts["n_prior_loans"].max()),
        "pct_with_0": float((loan_counts["n_prior_loans"] == 0).mean() * 100),
        "pct_with_1": float((loan_counts["n_prior_loans"] == 1).mean() * 100),
        "pct_with_lt_2": float((loan_counts["n_prior_loans"] < 2).mean() * 100),
        "pct_with_gte_3": float((loan_counts["n_prior_loans"] >= 3).mean() * 100),
    }

    return distribution, loan_counts


def analyze_null_handling(df, feature_info):
    """Analyze how nulls were handled in feature engineering."""
    regularity_features = feature_info["feature_sets"]["regularity"]["features"]
    magnitude_features = feature_info["feature_sets"]["magnitude"]["features"]

    null_analysis = {
        "regularity_features": {},
        "magnitude_features": {},
        "total_rows": len(df)
    }

    for feat in regularity_features:
        if feat in df.columns:
            null_count = df[feat].isna().sum()
            null_analysis["regularity_features"][feat] = {
                "null_count": int(null_count),
                "null_pct": float(null_count / len(df) * 100)
            }

    for feat in magnitude_features:
        if feat in df.columns:
            null_count = df[feat].isna().sum()
            null_analysis["magnitude_features"][feat] = {
                "null_count": int(null_count),
                "null_pct": float(null_count / len(df) * 100)
            }

    return null_analysis


def compute_fold_metrics(model, X, y):
    """Compute ROC-AUC and PR-AUC across folds."""
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)

    roc_aucs = []
    pr_aucs = []

    for train_idx, val_idx in skf.split(X, y):
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        model_clone = model.__class__(**model.get_params())
        model_clone.fit(X_train, y_train)

        y_proba = model_clone.predict_proba(X_val)[:, 1]

        roc_aucs.append(roc_auc_score(y_val, y_proba))
        pr_aucs.append(average_precision_score(y_val, y_proba))

    return roc_aucs, pr_aucs


def robustness_check(df, feature_info, min_prior_loans=3):
    """
    Re-run FS_regularity vs FS_magnitude comparison on customers
    with >= min_prior_loans to test robustness.
    """
    # Filter to customers with sufficient loan history
    df_subset = df[df["loan_count"] >= min_prior_loans].copy()

    if len(df_subset) < 100:
        return {
            "error": f"Too few samples with >= {min_prior_loans} prior loans",
            "n_samples": len(df_subset)
        }

    regularity_features = feature_info["feature_sets"]["regularity"]["features"]
    magnitude_features = feature_info["feature_sets"]["magnitude"]["features"]

    # Check that features exist and handle any remaining nulls
    reg_feats = [f for f in regularity_features if f in df_subset.columns]
    mag_feats = [f for f in magnitude_features if f in df_subset.columns]

    X_reg = df_subset[reg_feats].values
    X_mag = df_subset[mag_feats].values
    y = df_subset["target"].values

    # Scale
    scaler_reg = StandardScaler()
    scaler_mag = StandardScaler()
    X_reg_scaled = scaler_reg.fit_transform(X_reg)
    X_mag_scaled = scaler_mag.fit_transform(X_mag)

    model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)

    reg_roc, reg_pr = compute_fold_metrics(model, X_reg_scaled, y)
    mag_roc, mag_pr = compute_fold_metrics(model, X_mag_scaled, y)

    # Statistical test
    t_stat, t_pval = ttest_rel(reg_roc, mag_roc)

    return {
        "min_prior_loans": min_prior_loans,
        "n_samples": len(df_subset),
        "positive_rate": float(y.mean()),
        "regularity": {
            "roc_auc_mean": float(np.mean(reg_roc)),
            "roc_auc_std": float(np.std(reg_roc)),
            "pr_auc_mean": float(np.mean(reg_pr)),
            "pr_auc_std": float(np.std(reg_pr)),
            "roc_folds": [float(x) for x in reg_roc]
        },
        "magnitude": {
            "roc_auc_mean": float(np.mean(mag_roc)),
            "roc_auc_std": float(np.std(mag_roc)),
            "pr_auc_mean": float(np.mean(mag_pr)),
            "pr_auc_std": float(np.std(mag_pr)),
            "roc_folds": [float(x) for x in mag_roc]
        },
        "statistical_test": {
            "difference_roc": float(np.mean(reg_roc) - np.mean(mag_roc)),
            "t_statistic": float(t_stat),
            "p_value": float(t_pval),
            "significant_0.05": bool(t_pval < 0.05)
        },
        "finding_holds": bool(np.mean(reg_roc) > np.mean(mag_roc) and t_pval < 0.05)
    }


def main():
    print("=== T11: Join Coverage and Missing-History Analysis ===\n")

    perf, prevloans, demographics = load_raw_data()
    df, feature_info = load_features()

    results = {
        "timestamp": datetime.now().isoformat(),
        "table_coverage": {},
        "loan_history_distribution": {},
        "null_handling": {},
        "robustness_checks": {}
    }

    # Part 1: Table coverage
    print("=" * 60)
    print("PART 1: Table Coverage Analysis")
    print("=" * 60)

    coverage = analyze_table_coverage(perf, prevloans, demographics)
    results["table_coverage"] = coverage

    print(f"\nTotal customers in perf (target set): {coverage['perf_total']}")
    print(f"Customers with loan history (prevloans): {coverage['prevloans_unique_customers']}")
    print(f"Customers in all three tables: {coverage['all_three']}")
    print(f"Customers with NO prior loan history: {coverage['perf_no_prev_history']}")

    # Part 2: Prior loan distribution
    print("\n" + "=" * 60)
    print("PART 2: Prior Loan Distribution")
    print("=" * 60)

    distribution, loan_counts = analyze_loan_history_distribution(prevloans, perf)
    results["loan_history_distribution"] = distribution

    print(f"\nPrior loan count distribution:")
    print(f"  0 prior loans: {distribution['n_with_0_prior']} ({distribution['pct_with_0']:.1f}%)")
    print(f"  1 prior loan:  {distribution['n_with_1_prior']} ({distribution['pct_with_1']:.1f}%)")
    print(f"  2 prior loans: {distribution['n_with_2_prior']}")
    print(f"  3+ prior loans: {distribution['n_with_3plus_prior']} ({distribution['pct_with_gte_3']:.1f}%)")
    print(f"\nMean: {distribution['mean_prior_loans']:.2f}, Median: {distribution['median_prior_loans']:.0f}")
    print(f"Max: {distribution['max_prior_loans']}")

    print(f"\nCRITICAL: {distribution['pct_with_lt_2']:.1f}% of customers have <2 prior loans")
    print("  -> repay_delay_std and interval_regularity UNDEFINED for these customers")

    # Part 3: Null handling analysis
    print("\n" + "=" * 60)
    print("PART 3: Null Handling in Feature Engineering")
    print("=" * 60)

    null_analysis = analyze_null_handling(df, feature_info)
    results["null_handling"] = null_analysis

    print(f"\nRegularity features with nulls after processing:")
    nulls_found = False
    for feat, info in null_analysis["regularity_features"].items():
        if info["null_count"] > 0:
            print(f"  {feat}: {info['null_count']} nulls ({info['null_pct']:.1f}%)")
            nulls_found = True
    if not nulls_found:
        print("  None - all nulls were handled (imputed or dropped)")

    print(f"\nMagnitude features with nulls after processing:")
    nulls_found = False
    for feat, info in null_analysis["magnitude_features"].items():
        if info["null_count"] > 0:
            print(f"  {feat}: {info['null_count']} nulls ({info['null_pct']:.1f}%)")
            nulls_found = True
    if not nulls_found:
        print("  None - all nulls were handled (imputed or dropped)")

    # Check how features.py handled nulls - look at processed data
    print("\nInvestigating imputation method used:")
    # We can infer from the fact that there are no nulls but ~21% had no history
    no_history_pct = distribution["pct_with_0"]
    print(f"  {no_history_pct:.1f}% had 0 prior loans but {null_analysis['total_rows']} rows exist")
    if no_history_pct > 0 and all(v["null_count"] == 0 for v in null_analysis["regularity_features"].values()):
        print("  -> Regularity features were IMPUTED for customers with no history")
        results["imputation_method"] = "imputed (likely with 0 or median)"

    # Part 4: Robustness check
    print("\n" + "=" * 60)
    print("PART 4: Robustness Check (>= 3 prior loans)")
    print("=" * 60)

    # Add loan_count to df if not present (need to compute from prevloans)
    if "loan_count" not in df.columns:
        loan_count_map = prevloans.groupby("customerid").size()
        df["loan_count"] = df["customerid"].map(loan_count_map).fillna(0).astype(int)

    for min_loans in [1, 2, 3, 5]:
        subset = df[df["loan_count"] >= min_loans]
        print(f"\n>= {min_loans} prior loans: {len(subset)} customers ({len(subset)/len(df)*100:.1f}%)")

    # Run robustness test with >= 3 prior loans
    print("\n--- Robustness Test: Customers with >= 3 prior loans ---")
    robustness = robustness_check(df, feature_info, min_prior_loans=3)
    results["robustness_checks"]["gte_3_loans"] = robustness

    if "error" not in robustness:
        print(f"\nN = {robustness['n_samples']} customers")
        print(f"Default rate: {robustness['positive_rate']:.1%}")
        print(f"\nFS_regularity ROC-AUC: {robustness['regularity']['roc_auc_mean']:.4f} +/- {robustness['regularity']['roc_auc_std']:.3f}")
        print(f"FS_magnitude ROC-AUC:  {robustness['magnitude']['roc_auc_mean']:.4f} +/- {robustness['magnitude']['roc_auc_std']:.3f}")
        print(f"\nDifference: {robustness['statistical_test']['difference_roc']:.4f}")
        print(f"p-value: {robustness['statistical_test']['p_value']:.4f}")

        if robustness["finding_holds"]:
            print("\n>>> FINDING HOLDS: Regularity beats magnitude even on rich-history subset")
            print("    The effect is NOT driven by missingness patterns.")
        else:
            print("\n>>> WARNING: Finding does NOT hold on rich-history subset")
            print("    The effect MAY be driven by missingness patterns!")

    # Also test with >= 2 loans (minimum for variance features)
    print("\n--- Robustness Test: Customers with >= 2 prior loans ---")
    robustness2 = robustness_check(df, feature_info, min_prior_loans=2)
    results["robustness_checks"]["gte_2_loans"] = robustness2

    if "error" not in robustness2:
        print(f"\nN = {robustness2['n_samples']} customers")
        print(f"Difference: {robustness2['statistical_test']['difference_roc']:.4f}")
        print(f"p-value: {robustness2['statistical_test']['p_value']:.4f}")
        print(f"Finding holds: {robustness2['finding_holds']}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(f"\n1. {distribution['pct_with_0']:.1f}% of customers have NO prior loan history")
    print(f"   These customers have imputed regularity features (likely 0 or median)")
    print(f"\n2. {distribution['pct_with_lt_2']:.1f}% have <2 prior loans")
    print(f"   Variance-based features (repay_delay_std, etc.) undefined for these")
    print(f"\n3. Robustness test on >= 3 prior loans:")
    if "error" not in robustness:
        if robustness["finding_holds"]:
            print(f"   ROBUST - Finding holds (p={robustness['statistical_test']['p_value']:.4f})")
        else:
            print(f"   NOT ROBUST - Finding may be artifact")

    results["conclusion"] = {
        "pct_no_history": distribution["pct_with_0"],
        "pct_insufficient_history": distribution["pct_with_lt_2"],
        "imputation_used": True,
        "finding_robust_gte3": robustness.get("finding_holds", None) if "error" not in robustness else None,
        "finding_robust_gte2": robustness2.get("finding_holds", None) if "error" not in robustness2 else None
    }

    # Save results
    with open(RESULTS_DIR / "coverage_analysis.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {RESULTS_DIR / 'coverage_analysis.json'}")

    return results


if __name__ == "__main__":
    main()
