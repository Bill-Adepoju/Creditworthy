"""
T10: Surface PR-AUC and Fold Variance with Statistical Tests

Reports mean ± std across folds for all metrics.
Performs statistical significance tests for key comparisons:
- FS_regularity vs FS_magnitude
- FS_full vs FS_regularity
- Class weighting vs SMOTE
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
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.metrics import (
    roc_auc_score, average_precision_score,
    precision_score, recall_score, f1_score
)
from scipy.stats import wilcoxon, ttest_rel
from imblearn.over_sampling import SMOTE

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"

RANDOM_STATE = 42
N_FOLDS = 5


def load_features():
    """Load processed features and feature set definitions."""
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)
    return df, feature_info


def compute_fold_metrics(model, X, y, use_smote=False):
    """
    Compute all metrics across K folds.
    Returns dict of metric_name -> list of fold values.
    """
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)

    metrics = {
        "roc_auc": [],
        "pr_auc": [],
        "precision": [],
        "recall": [],
        "f1": []
    }

    for train_idx, val_idx in skf.split(X, y):
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        if use_smote:
            smote = SMOTE(random_state=RANDOM_STATE)
            X_train, y_train = smote.fit_resample(X_train, y_train)

        model_clone = model.__class__(**model.get_params())
        model_clone.fit(X_train, y_train)

        y_proba = model_clone.predict_proba(X_val)[:, 1]
        y_pred = model_clone.predict(X_val)

        metrics["roc_auc"].append(roc_auc_score(y_val, y_proba))
        metrics["pr_auc"].append(average_precision_score(y_val, y_proba))
        metrics["precision"].append(precision_score(y_val, y_pred, zero_division=0))
        metrics["recall"].append(recall_score(y_val, y_pred, zero_division=0))
        metrics["f1"].append(f1_score(y_val, y_pred, zero_division=0))

    return metrics


def summarize_metrics(metrics):
    """Compute mean ± std for each metric."""
    return {
        name: {
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "folds": [float(v) for v in values]
        }
        for name, values in metrics.items()
    }


def statistical_test(values1, values2, name1, name2):
    """
    Perform paired statistical tests.
    Returns dict with t-test and Wilcoxon results.
    """
    # Paired t-test
    t_stat, t_pval = ttest_rel(values1, values2)

    # Wilcoxon signed-rank test (non-parametric)
    # Note: Wilcoxon requires n >= 6 for reliable results, we have 5 folds
    # Will still compute but note the limitation
    try:
        w_stat, w_pval = wilcoxon(values1, values2)
    except ValueError:
        # Can happen if all differences are zero
        w_stat, w_pval = np.nan, np.nan

    mean_diff = np.mean(values1) - np.mean(values2)

    return {
        "comparison": f"{name1} vs {name2}",
        "mean_difference": float(mean_diff),
        "paired_ttest": {
            "t_statistic": float(t_stat),
            "p_value": float(t_pval),
            "significant_0.05": bool(t_pval < 0.05),
            "significant_0.01": bool(t_pval < 0.01)
        },
        "wilcoxon": {
            "w_statistic": float(w_stat) if not np.isnan(w_stat) else None,
            "p_value": float(w_pval) if not np.isnan(w_pval) else None,
            "significant_0.05": bool(w_pval < 0.05) if not np.isnan(w_pval) else None,
            "note": "n=5 folds is at the minimum for Wilcoxon reliability"
        }
    }


def main():
    print("=== T10: Variance Analysis and Statistical Tests ===\n")

    df, feature_info = load_features()

    results = {
        "timestamp": datetime.now().isoformat(),
        "n_folds": N_FOLDS,
        "n_samples": len(df),
        "model_feature_set_results": {},
        "statistical_tests": {},
        "imbalance_comparison": {}
    }

    # Models to test
    models = {
        "LogisticRegression": LogisticRegression(
            class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE
        ),
        "RandomForest": RandomForestClassifier(
            n_estimators=100, max_depth=8, min_samples_leaf=5,
            class_weight="balanced", random_state=RANDOM_STATE, n_jobs=1
        ),
        "XGBoost": XGBClassifier(
            n_estimators=100, max_depth=2, reg_lambda=5.0,
            scale_pos_weight=3.5, random_state=RANDOM_STATE,
            eval_metric="logloss", verbosity=0
        )
    }

    feature_sets = feature_info["feature_sets"]

    # Store fold-level results for statistical tests
    fold_results = {}

    print("=" * 70)
    print("PART 1: All models x feature sets with variance")
    print("=" * 70)

    for fs_name, fs_info in feature_sets.items():
        feature_cols = fs_info["features"]
        X = df[feature_cols].values
        y = df["target"].values

        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        print(f"\n--- Feature Set: {fs_name} ({len(feature_cols)} features) ---")
        print(f"{'Model':<20} {'ROC-AUC':<18} {'PR-AUC':<18} {'F1':<18}")
        print("-" * 70)

        fold_results[fs_name] = {}

        for model_name, model in models.items():
            metrics = compute_fold_metrics(model, X_scaled, y, use_smote=False)
            summary = summarize_metrics(metrics)

            key = f"{model_name}_{fs_name}"
            results["model_feature_set_results"][key] = summary
            fold_results[fs_name][model_name] = metrics

            roc = summary["roc_auc"]
            pr = summary["pr_auc"]
            f1 = summary["f1"]

            print(f"{model_name:<20} "
                  f"{roc['mean']:.4f} +/- {roc['std']:.3f}  "
                  f"{pr['mean']:.4f} +/- {pr['std']:.3f}  "
                  f"{f1['mean']:.4f} +/- {f1['std']:.3f}")

    # Statistical tests for key comparisons
    print("\n" + "=" * 70)
    print("PART 2: Statistical Significance Tests")
    print("=" * 70)

    # Test 1: FS_regularity vs FS_magnitude (using LR as primary model)
    print("\n--- Test 1: FS_regularity vs FS_magnitude (LogisticRegression) ---")

    reg_roc = fold_results["regularity"]["LogisticRegression"]["roc_auc"]
    mag_roc = fold_results["magnitude"]["LogisticRegression"]["roc_auc"]

    test1_roc = statistical_test(reg_roc, mag_roc, "FS_regularity", "FS_magnitude")
    results["statistical_tests"]["regularity_vs_magnitude_roc"] = test1_roc

    print(f"ROC-AUC difference: {test1_roc['mean_difference']:.4f}")
    print(f"Paired t-test p-value: {test1_roc['paired_ttest']['p_value']:.4f}")
    print(f"Significant at alpha=0.05: {test1_roc['paired_ttest']['significant_0.05']}")

    # Also test PR-AUC
    reg_pr = fold_results["regularity"]["LogisticRegression"]["pr_auc"]
    mag_pr = fold_results["magnitude"]["LogisticRegression"]["pr_auc"]

    test1_pr = statistical_test(reg_pr, mag_pr, "FS_regularity", "FS_magnitude")
    results["statistical_tests"]["regularity_vs_magnitude_pr"] = test1_pr

    print(f"\nPR-AUC difference: {test1_pr['mean_difference']:.4f}")
    print(f"Paired t-test p-value: {test1_pr['paired_ttest']['p_value']:.4f}")
    print(f"Significant at alpha=0.05: {test1_pr['paired_ttest']['significant_0.05']}")

    # Test 2: FS_full vs FS_regularity
    print("\n--- Test 2: FS_full vs FS_regularity (LogisticRegression) ---")

    full_roc = fold_results["full"]["LogisticRegression"]["roc_auc"]

    test2_roc = statistical_test(full_roc, reg_roc, "FS_full", "FS_regularity")
    results["statistical_tests"]["full_vs_regularity_roc"] = test2_roc

    print(f"ROC-AUC difference: {test2_roc['mean_difference']:.4f}")
    print(f"Paired t-test p-value: {test2_roc['paired_ttest']['p_value']:.4f}")
    print(f"Significant at alpha=0.05: {test2_roc['paired_ttest']['significant_0.05']}")

    full_pr = fold_results["full"]["LogisticRegression"]["pr_auc"]

    test2_pr = statistical_test(full_pr, reg_pr, "FS_full", "FS_regularity")
    results["statistical_tests"]["full_vs_regularity_pr"] = test2_pr

    print(f"\nPR-AUC difference: {test2_pr['mean_difference']:.4f}")
    print(f"Paired t-test p-value: {test2_pr['paired_ttest']['p_value']:.4f}")
    print(f"Significant at alpha=0.05: {test2_pr['paired_ttest']['significant_0.05']}")

    # Part 3: Class weighting vs SMOTE comparison
    print("\n" + "=" * 70)
    print("PART 3: Class Weighting vs SMOTE")
    print("=" * 70)

    # Use full feature set for this comparison
    feature_cols = feature_sets["full"]["features"]
    X = df[feature_cols].values
    y = df["target"].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    print(f"\n{'Model':<20} {'Method':<15} {'ROC-AUC':<18} {'PR-AUC':<18}")
    print("-" * 70)

    for model_name, model in models.items():
        # Class weighting (already have this)
        cw_metrics = compute_fold_metrics(model, X_scaled, y, use_smote=False)
        cw_summary = summarize_metrics(cw_metrics)

        # SMOTE - need to create model without class_weight for fair comparison
        if model_name == "LogisticRegression":
            smote_model = LogisticRegression(max_iter=1000, random_state=RANDOM_STATE)
        elif model_name == "RandomForest":
            smote_model = RandomForestClassifier(
                n_estimators=100, max_depth=8, min_samples_leaf=5,
                random_state=RANDOM_STATE, n_jobs=1
            )
        else:
            smote_model = XGBClassifier(
                n_estimators=100, max_depth=2, reg_lambda=5.0,
                random_state=RANDOM_STATE, eval_metric="logloss", verbosity=0
            )

        smote_metrics = compute_fold_metrics(smote_model, X_scaled, y, use_smote=True)
        smote_summary = summarize_metrics(smote_metrics)

        results["imbalance_comparison"][f"{model_name}_class_weight"] = cw_summary
        results["imbalance_comparison"][f"{model_name}_smote"] = smote_summary

        cw_roc = cw_summary["roc_auc"]
        smote_roc = smote_summary["roc_auc"]
        cw_pr = cw_summary["pr_auc"]
        smote_pr = smote_summary["pr_auc"]

        print(f"{model_name:<20} {'class_weight':<15} "
              f"{cw_roc['mean']:.4f} +/- {cw_roc['std']:.3f}  "
              f"{cw_pr['mean']:.4f} +/- {cw_pr['std']:.3f}")
        print(f"{'':<20} {'SMOTE':<15} "
              f"{smote_roc['mean']:.4f} +/- {smote_roc['std']:.3f}  "
              f"{smote_pr['mean']:.4f} +/- {smote_pr['std']:.3f}")

        # Statistical test between methods
        test_imb = statistical_test(
            cw_metrics["roc_auc"], smote_metrics["roc_auc"],
            "class_weight", "SMOTE"
        )
        results["statistical_tests"][f"{model_name}_cw_vs_smote"] = test_imb

    # Summary findings
    print("\n" + "=" * 70)
    print("KEY FINDINGS")
    print("=" * 70)

    # Finding 1: regularity vs magnitude
    reg_vs_mag_sig = test1_roc["paired_ttest"]["significant_0.05"]
    print(f"\n1. FS_regularity vs FS_magnitude:")
    print(f"   Difference: {test1_roc['mean_difference']:.4f} ROC-AUC ({test1_roc['mean_difference']*100:.1f} pp)")
    if reg_vs_mag_sig:
        print(f"   STATISTICALLY SIGNIFICANT (p={test1_roc['paired_ttest']['p_value']:.4f})")
    else:
        print(f"   NOT significant (p={test1_roc['paired_ttest']['p_value']:.4f})")

    # Finding 2: full vs regularity
    full_vs_reg_sig = test2_roc["paired_ttest"]["significant_0.05"]
    print(f"\n2. FS_full vs FS_regularity:")
    print(f"   Difference: {test2_roc['mean_difference']:.4f} ROC-AUC ({test2_roc['mean_difference']*100:.2f} pp)")
    if full_vs_reg_sig:
        print(f"   STATISTICALLY SIGNIFICANT (p={test2_roc['paired_ttest']['p_value']:.4f})")
    else:
        print(f"   NOT significant (p={test2_roc['paired_ttest']['p_value']:.4f})")
        print("   -> Adding magnitude features to regularity yields NO improvement")

    results["key_findings"] = {
        "regularity_beats_magnitude": {
            "significant": bool(reg_vs_mag_sig),
            "p_value": float(test1_roc["paired_ttest"]["p_value"]),
            "difference_roc": float(test1_roc["mean_difference"])
        },
        "full_beats_regularity": {
            "significant": bool(full_vs_reg_sig),
            "p_value": float(test2_roc["paired_ttest"]["p_value"]),
            "difference_roc": float(test2_roc["mean_difference"])
        },
        "magnitude_features_redundant": bool(not full_vs_reg_sig)
    }

    # Save results
    with open(RESULTS_DIR / "variance_analysis.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {RESULTS_DIR / 'variance_analysis.json'}")

    return results


if __name__ == "__main__":
    main()
