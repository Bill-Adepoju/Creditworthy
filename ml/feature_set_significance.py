"""
T34: Apply Nadeau-Bengio corrected test to feature set comparisons

The headline finding (FS_regularity vs FS_magnitude, p=0.004) was based on 5-fold CV.
This script re-runs with 5x10 repeated CV and applies Nadeau-Bengio correction.
"""
import numpy as np
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import RepeatedStratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler

RESULTS_DIR = Path(__file__).parent.parent / "results"
DATA_DIR = Path(__file__).parent.parent / "data"

# CV configuration matching model_tuning_v2.py
N_SPLITS = 5
N_REPEATS = 10
RANDOM_STATE = 42


def nadeau_bengio_corrected_ttest(scores1, scores2, n_train, n_test, n_splits, n_repeats):
    """
    Nadeau-Bengio corrected paired t-test for repeated k-fold CV.
    """
    scores1 = np.array(scores1)
    scores2 = np.array(scores2)

    n = len(scores1)
    diffs = scores1 - scores2
    mean_diff = np.mean(diffs)
    var_diff = np.var(diffs, ddof=1)

    # Nadeau-Bengio correction factor
    correction_factor = (1/n) + (n_test / n_train)
    corrected_var = var_diff * correction_factor
    corrected_se = np.sqrt(corrected_var)

    if corrected_se > 0:
        t_stat = mean_diff / corrected_se
    else:
        t_stat = 0

    df = n - 1
    p_value = 2 * stats.t.sf(abs(t_stat), df)

    # 95% CI
    t_crit = stats.t.ppf(0.975, df)
    ci_lower = mean_diff - t_crit * corrected_se
    ci_upper = mean_diff + t_crit * corrected_se

    return {
        "mean_difference": float(mean_diff),
        "t_statistic": float(t_stat),
        "p_value": float(p_value),
        "ci_95": [float(ci_lower), float(ci_upper)],
        "significant_0.05": p_value < 0.05,
        "correction_factor": float(correction_factor)
    }


def main():
    print("=== T34: Feature Set Significance with Nadeau-Bengio Correction ===\n")

    # Load data
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)

    y = df["target"].values
    n_samples = len(y)

    # Calculate train/test sizes for correction
    n_test = n_samples // N_SPLITS
    n_train = n_samples - n_test

    print(f"Dataset: {n_samples} samples")
    print(f"CV: {N_SPLITS}-fold x {N_REPEATS} repeats = {N_SPLITS * N_REPEATS} folds")
    print(f"Per fold: n_train={n_train}, n_test={n_test}")
    print(f"Correction factor: {(1/(N_SPLITS*N_REPEATS)) + (n_test/n_train):.4f}")
    print()

    # Get feature sets
    feature_sets = {
        "regularity": feature_info["feature_sets"]["regularity"]["features"],
        "magnitude": feature_info["feature_sets"]["magnitude"]["features"],
        "full": feature_info["feature_sets"]["full"]["features"]
    }

    # Run repeated CV for each feature set
    cv = RepeatedStratifiedKFold(n_splits=N_SPLITS, n_repeats=N_REPEATS, random_state=RANDOM_STATE)

    results = {
        "timestamp": datetime.now().isoformat(),
        "cv_config": {
            "n_splits": N_SPLITS,
            "n_repeats": N_REPEATS,
            "n_train": n_train,
            "n_test": n_test,
            "correction_factor": (1/(N_SPLITS*N_REPEATS)) + (n_test/n_train)
        },
        "feature_set_scores": {},
        "comparisons": {}
    }

    print("Running repeated CV for each feature set...")
    print()

    for fs_name, features in feature_sets.items():
        print(f"  {fs_name}: {len(features)} features...", end=" ")

        X = df[features].values
        scaler = StandardScaler()

        model = LogisticRegression(
            max_iter=1000,
            random_state=RANDOM_STATE,
            class_weight="balanced"
        )

        # Collect fold scores manually to ensure consistency
        fold_scores = []
        for train_idx, test_idx in cv.split(X, y):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)

            model.fit(X_train_scaled, y_train)
            proba = model.predict_proba(X_test_scaled)[:, 1]

            from sklearn.metrics import roc_auc_score
            auc = roc_auc_score(y_test, proba)
            fold_scores.append(auc)

        fold_scores = np.array(fold_scores)
        print(f"mean={fold_scores.mean():.4f}, std={fold_scores.std():.4f}")

        results["feature_set_scores"][fs_name] = {
            "n_features": len(features),
            "roc_auc_mean": float(fold_scores.mean()),
            "roc_auc_std": float(fold_scores.std()),
            "roc_auc_folds": [float(s) for s in fold_scores]
        }

    # Comparisons
    print("\n" + "=" * 80)
    print("FEATURE SET COMPARISONS")
    print("=" * 80)

    comparisons = [
        ("regularity", "magnitude"),
        ("full", "regularity"),
        ("full", "magnitude")
    ]

    for fs1, fs2 in comparisons:
        scores1 = np.array(results["feature_set_scores"][fs1]["roc_auc_folds"])
        scores2 = np.array(results["feature_set_scores"][fs2]["roc_auc_folds"])

        # Naive paired t-test
        naive_t, naive_p = stats.ttest_rel(scores1, scores2)

        # Wilcoxon
        wilcoxon_stat, wilcoxon_p = stats.wilcoxon(scores1, scores2)

        # Nadeau-Bengio corrected
        corrected = nadeau_bengio_corrected_ttest(
            scores1, scores2, n_train, n_test, N_SPLITS, N_REPEATS
        )

        results["comparisons"][f"{fs1}_vs_{fs2}"] = {
            "comparison": f"{fs1} vs {fs2}",
            "mean_difference": corrected["mean_difference"],
            "naive_paired_ttest": {
                "t_statistic": float(naive_t),
                "p_value": float(naive_p),
                "significant_0.05": naive_p < 0.05
            },
            "wilcoxon": {
                "statistic": float(wilcoxon_stat),
                "p_value": float(wilcoxon_p),
                "significant_0.05": wilcoxon_p < 0.05
            },
            "nadeau_bengio_corrected": {
                "t_statistic": corrected["t_statistic"],
                "p_value": corrected["p_value"],
                "ci_95": corrected["ci_95"],
                "significant_0.05": corrected["significant_0.05"]
            }
        }

        print(f"\n{fs1} vs {fs2}:")
        print(f"  Mean difference: {corrected['mean_difference']:+.4f}")
        print(f"  95% CI: [{corrected['ci_95'][0]:+.4f}, {corrected['ci_95'][1]:+.4f}]")
        print()
        print(f"  | Test                    | p-value | Significant |")
        print(f"  |-------------------------|---------|-------------|")
        print(f"  | Naive paired t-test     | {naive_p:.4f}  | {'yes' if naive_p < 0.05 else 'no':>11} |")
        print(f"  | Wilcoxon signed-rank    | {wilcoxon_p:.4f}  | {'yes' if wilcoxon_p < 0.05 else 'no':>11} |")
        print(f"  | Nadeau-Bengio corrected | {corrected['p_value']:.4f}  | {'yes' if corrected['significant_0.05'] else 'no':>11} |")

    # Key finding: regularity vs magnitude
    reg_vs_mag = results["comparisons"]["regularity_vs_magnitude"]
    print("\n" + "=" * 80)
    print("HEADLINE FINDING: FS_regularity vs FS_magnitude")
    print("=" * 80)

    print(f"\nOriginal (5-fold, naive t-test): p=0.004, significant")
    print(f"Corrected (50-fold, Nadeau-Bengio): p={reg_vs_mag['nadeau_bengio_corrected']['p_value']:.4f}")

    if reg_vs_mag['nadeau_bengio_corrected']['significant_0.05']:
        print("\n=> RESULT SURVIVES correction. FS_regularity significantly outperforms FS_magnitude.")
    else:
        print("\n=> RESULT DOES NOT SURVIVE correction. Difference is not statistically significant.")

    # Convert numpy types for JSON
    def convert_types(obj):
        if isinstance(obj, dict):
            return {k: convert_types(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_types(v) for v in obj]
        elif isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        elif isinstance(obj, (np.integer, int)):
            return int(obj)
        elif isinstance(obj, (np.floating, float)):
            return float(obj)
        return obj

    # Save results
    output_path = RESULTS_DIR / "feature_set_significance.json"
    with open(output_path, "w") as f:
        json.dump(convert_types(results), f, indent=2)
    print(f"\nResults saved to {output_path}")

    # Append to SUMMARY.md
    summary_entry = f"""
### feature_set_significance - {datetime.now().strftime('%Y-%m-%d')}
**What was run:** T34 - Apply Nadeau-Bengio correction to feature set comparisons.
**Why:** Original p=0.004 for regularity vs magnitude was from naive t-test on 5-fold CV.
**Key numbers:**

| Comparison | Naive p | Corrected p | Significant |
|------------|---------|-------------|-------------|
| regularity vs magnitude | {reg_vs_mag['naive_paired_ttest']['p_value']:.4f} | {reg_vs_mag['nadeau_bengio_corrected']['p_value']:.4f} | {'Yes' if reg_vs_mag['nadeau_bengio_corrected']['significant_0.05'] else 'No'} |

**Mean difference:** {reg_vs_mag['mean_difference']:+.4f} (regularity - magnitude)
**95% CI:** [{reg_vs_mag['nadeau_bengio_corrected']['ci_95'][0]:+.4f}, {reg_vs_mag['nadeau_bengio_corrected']['ci_95'][1]:+.4f}]
"""

    with open(RESULTS_DIR / "SUMMARY.md", "a", encoding="utf-8") as f:
        f.write(summary_entry)
    print(f"Summary appended to SUMMARY.md")


if __name__ == "__main__":
    main()
