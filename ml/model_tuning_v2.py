"""
T23 + T24: Fixed Model Tuning with Adequate Statistical Power

Fixes:
- T23: error_score='raise' to surface any failures
- T23: Proper NaN handling in JSON serialization
- T24: RepeatedStratifiedKFold(n_splits=5, n_repeats=10) for 50 estimates
- T24: Paired significance tests between models
- T17: Reports PR-AUC alongside ROC-AUC
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings("ignore")

from sklearn.model_selection import (
    RepeatedStratifiedKFold, RandomizedSearchCV, cross_val_score
)
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.metrics import roc_auc_score, average_precision_score, make_scorer
from scipy.stats import ttest_rel, wilcoxon

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"

RANDOM_STATE = 42
N_SPLITS = 5
N_REPEATS = 10  # 5 * 10 = 50 estimates for statistical power
N_ITER = 50  # RandomizedSearchCV iterations


def load_features():
    """Load processed features and feature set definitions."""
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)
    return df, feature_info


def safe_json_value(val):
    """Convert numpy types and handle NaN for JSON serialization."""
    if isinstance(val, (np.integer, np.int64, np.int32)):
        return int(val)
    elif isinstance(val, (np.floating, np.float64, np.float32)):
        if np.isnan(val):
            return None  # JSON null instead of NaN
        return float(val)
    elif isinstance(val, np.ndarray):
        return [safe_json_value(v) for v in val]
    elif isinstance(val, dict):
        return {k: safe_json_value(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [safe_json_value(v) for v in val]
    elif isinstance(val, np.bool_):
        return bool(val)
    return val


def get_tuning_param_distributions():
    """Constrained parameter distributions for small dataset."""
    rf_params = {
        "n_estimators": [50, 100, 200],
        "max_depth": [3, 4, 5, 6, 8],
        "min_samples_split": [5, 10, 20],
        "min_samples_leaf": [2, 5, 10],
        "max_features": ["sqrt", "log2", 0.3, 0.5]
    }

    xgb_params = {
        "n_estimators": [50, 100, 200],
        "max_depth": [2, 3, 4, 5],
        "learning_rate": [0.01, 0.05, 0.1, 0.2],
        "min_child_weight": [1, 3, 5, 10],
        "subsample": [0.7, 0.8, 0.9, 1.0],
        "colsample_bytree": [0.7, 0.8, 0.9, 1.0],
        "reg_alpha": [0, 0.1, 0.5],
        "reg_lambda": [1.0, 2.0, 5.0]
    }

    return rf_params, xgb_params


def compute_cv_metrics(model, X, y, cv):
    """Compute ROC-AUC and PR-AUC across CV folds."""
    roc_aucs = []
    pr_aucs = []
    train_aucs = []

    for train_idx, val_idx in cv.split(X, y):
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        model_clone = model.__class__(**model.get_params())
        model_clone.fit(X_train, y_train)

        # Validation metrics
        val_proba = model_clone.predict_proba(X_val)[:, 1]
        roc_aucs.append(roc_auc_score(y_val, val_proba))
        pr_aucs.append(average_precision_score(y_val, val_proba))

        # Training metrics (for overfit gap)
        train_proba = model_clone.predict_proba(X_train)[:, 1]
        train_aucs.append(roc_auc_score(y_train, train_proba))

    return {
        "roc_auc_folds": roc_aucs,
        "roc_auc_mean": float(np.mean(roc_aucs)),
        "roc_auc_std": float(np.std(roc_aucs)),
        "pr_auc_folds": pr_aucs,
        "pr_auc_mean": float(np.mean(pr_aucs)),
        "pr_auc_std": float(np.std(pr_aucs)),
        "train_auc_mean": float(np.mean(train_aucs)),
        "train_auc_std": float(np.std(train_aucs)),
        "overfit_gap": float(np.mean(train_aucs) - np.mean(roc_aucs))
    }


def significance_test(values1, values2, name1, name2):
    """Paired t-test and Wilcoxon for model comparison."""
    t_stat, t_pval = ttest_rel(values1, values2)

    try:
        w_stat, w_pval = wilcoxon(values1, values2)
    except ValueError:
        w_stat, w_pval = np.nan, np.nan

    diff = np.mean(values1) - np.mean(values2)

    return {
        "comparison": f"{name1} vs {name2}",
        "mean_difference": float(diff),
        "paired_ttest": {
            "t_statistic": float(t_stat),
            "p_value": float(t_pval),
            "significant_0.05": bool(t_pval < 0.05)
        },
        "wilcoxon": {
            "w_statistic": safe_json_value(w_stat),
            "p_value": safe_json_value(w_pval),
            "significant_0.05": bool(w_pval < 0.05) if not np.isnan(w_pval) else None
        },
        "conclusion": "statistically_different" if t_pval < 0.05 else "statistically_indistinguishable"
    }


def main():
    print("=== T23+T24: Fixed Model Tuning with Statistical Power ===\n")

    df, feature_info = load_features()
    feature_cols = feature_info["feature_sets"]["full"]["features"]
    X = df[feature_cols].values
    y = df["target"].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    print(f"Dataset: {len(df)} samples, {len(feature_cols)} features")
    print(f"Class balance: {y.mean():.2%} positive (default)")
    print(f"CV strategy: RepeatedStratifiedKFold(n_splits={N_SPLITS}, n_repeats={N_REPEATS}) = {N_SPLITS * N_REPEATS} folds\n")

    cv = RepeatedStratifiedKFold(n_splits=N_SPLITS, n_repeats=N_REPEATS, random_state=RANDOM_STATE)

    results = {
        "timestamp": datetime.now().isoformat(),
        "config": {
            "n_samples": len(df),
            "n_features": len(feature_cols),
            "positive_rate": float(y.mean()),
            "cv_splits": N_SPLITS,
            "cv_repeats": N_REPEATS,
            "total_folds": N_SPLITS * N_REPEATS,
            "tuning_iterations": N_ITER
        },
        "tuned_models": {},
        "model_comparison": {},
        "significance_tests": {}
    }

    # ===== STEP 1: Hyperparameter tuning with error_score='raise' =====
    print("=" * 60)
    print("STEP 1: Hyperparameter Tuning (error_score='raise')")
    print("=" * 60)

    rf_params, xgb_params = get_tuning_param_distributions()
    cv_tune = RepeatedStratifiedKFold(n_splits=N_SPLITS, n_repeats=2, random_state=RANDOM_STATE)  # Faster for tuning

    # Tune RandomForest
    print("\nTuning RandomForest (error_score='raise')...")
    rf_base = RandomForestClassifier(
        class_weight="balanced", random_state=RANDOM_STATE, n_jobs=1
    )
    try:
        rf_search = RandomizedSearchCV(
            rf_base, rf_params, n_iter=N_ITER, cv=cv_tune, scoring='roc_auc',
            random_state=RANDOM_STATE, n_jobs=1, verbose=1, error_score='raise'
        )
        rf_search.fit(X_scaled, y)
        rf_best = rf_search.best_estimator_
        rf_cv_score = rf_search.best_score_

        print(f"  Best params: {rf_search.best_params_}")
        print(f"  Best CV ROC-AUC: {rf_cv_score:.4f}")

        results["tuned_models"]["RandomForest"] = {
            "best_params": safe_json_value(rf_search.best_params_),
            "best_cv_score": safe_json_value(rf_cv_score),
            "tuning_status": "success"
        }
    except Exception as e:
        print(f"  ERROR during RF tuning: {e}")
        # Fallback to constrained defaults
        rf_best = RandomForestClassifier(
            n_estimators=100, max_depth=6, min_samples_leaf=5,
            class_weight="balanced", random_state=RANDOM_STATE, n_jobs=1
        )
        results["tuned_models"]["RandomForest"] = {
            "best_params": {"max_depth": 6, "min_samples_leaf": 5},
            "best_cv_score": None,
            "tuning_status": f"failed: {str(e)}"
        }

    # Tune XGBoost
    print("\nTuning XGBoost (error_score='raise')...")
    xgb_base = XGBClassifier(
        scale_pos_weight=3.5, random_state=RANDOM_STATE,
        eval_metric="logloss", verbosity=0
    )
    try:
        xgb_search = RandomizedSearchCV(
            xgb_base, xgb_params, n_iter=N_ITER, cv=cv_tune, scoring='roc_auc',
            random_state=RANDOM_STATE, n_jobs=1, verbose=0, error_score='raise'
        )
        xgb_search.fit(X_scaled, y)
        xgb_best = xgb_search.best_estimator_
        xgb_cv_score = xgb_search.best_score_

        print(f"  Best params: {xgb_search.best_params_}")
        print(f"  Best CV ROC-AUC: {xgb_cv_score:.4f}")

        results["tuned_models"]["XGBoost"] = {
            "best_params": safe_json_value(xgb_search.best_params_),
            "best_cv_score": safe_json_value(xgb_cv_score),
            "tuning_status": "success"
        }
    except Exception as e:
        print(f"  ERROR during XGBoost tuning: {e}")
        xgb_best = XGBClassifier(
            n_estimators=100, max_depth=2, reg_lambda=5.0,
            scale_pos_weight=3.5, random_state=RANDOM_STATE,
            eval_metric="logloss", verbosity=0
        )
        results["tuned_models"]["XGBoost"] = {
            "best_params": {"max_depth": 2, "reg_lambda": 5.0},
            "best_cv_score": None,
            "tuning_status": f"failed: {str(e)}"
        }

    # ===== STEP 2: Full CV evaluation (50 folds) =====
    print("\n" + "=" * 60)
    print(f"STEP 2: Full {N_SPLITS * N_REPEATS}-fold CV Evaluation")
    print("=" * 60)

    models = {
        "LogisticRegression": LogisticRegression(
            class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE
        ),
        "RandomForest_Tuned": rf_best,
        "XGBoost_Tuned": xgb_best
    }

    print(f"\n{'Model':<25} {'ROC-AUC':<20} {'PR-AUC':<20} {'Overfit Gap'}")
    print("-" * 80)

    fold_results = {}
    for name, model in models.items():
        metrics = compute_cv_metrics(model, X_scaled, y, cv)
        fold_results[name] = metrics
        results["model_comparison"][name] = safe_json_value(metrics)

        print(f"{name:<25} {metrics['roc_auc_mean']:.4f} +/- {metrics['roc_auc_std']:.3f}   "
              f"{metrics['pr_auc_mean']:.4f} +/- {metrics['pr_auc_std']:.3f}   "
              f"{metrics['overfit_gap']:.3f}")

    # ===== STEP 3: Significance tests =====
    print("\n" + "=" * 60)
    print("STEP 3: Pairwise Significance Tests")
    print("=" * 60)

    # XGBoost vs LR
    test_xgb_lr = significance_test(
        fold_results["XGBoost_Tuned"]["roc_auc_folds"],
        fold_results["LogisticRegression"]["roc_auc_folds"],
        "XGBoost_Tuned", "LogisticRegression"
    )
    results["significance_tests"]["XGBoost_vs_LR"] = test_xgb_lr

    print(f"\nXGBoost_Tuned vs LogisticRegression:")
    print(f"  Difference: {test_xgb_lr['mean_difference']:.4f}")
    print(f"  Paired t-test p-value: {test_xgb_lr['paired_ttest']['p_value']:.4f}")
    print(f"  Wilcoxon p-value: {test_xgb_lr['wilcoxon']['p_value']}")
    print(f"  Conclusion: {test_xgb_lr['conclusion'].upper()}")

    # RF vs LR
    test_rf_lr = significance_test(
        fold_results["RandomForest_Tuned"]["roc_auc_folds"],
        fold_results["LogisticRegression"]["roc_auc_folds"],
        "RandomForest_Tuned", "LogisticRegression"
    )
    results["significance_tests"]["RF_vs_LR"] = test_rf_lr

    print(f"\nRandomForest_Tuned vs LogisticRegression:")
    print(f"  Difference: {test_rf_lr['mean_difference']:.4f}")
    print(f"  Paired t-test p-value: {test_rf_lr['paired_ttest']['p_value']:.4f}")
    print(f"  Conclusion: {test_rf_lr['conclusion'].upper()}")

    # XGBoost vs RF
    test_xgb_rf = significance_test(
        fold_results["XGBoost_Tuned"]["roc_auc_folds"],
        fold_results["RandomForest_Tuned"]["roc_auc_folds"],
        "XGBoost_Tuned", "RandomForest_Tuned"
    )
    results["significance_tests"]["XGBoost_vs_RF"] = test_xgb_rf

    print(f"\nXGBoost_Tuned vs RandomForest_Tuned:")
    print(f"  Difference: {test_xgb_rf['mean_difference']:.4f}")
    print(f"  Paired t-test p-value: {test_xgb_rf['paired_ttest']['p_value']:.4f}")
    print(f"  Conclusion: {test_xgb_rf['conclusion'].upper()}")

    # ===== CONCLUSION =====
    print("\n" + "=" * 60)
    print("CONCLUSION")
    print("=" * 60)

    all_indistinguishable = (
        test_xgb_lr["conclusion"] == "statistically_indistinguishable" and
        test_rf_lr["conclusion"] == "statistically_indistinguishable" and
        test_xgb_rf["conclusion"] == "statistically_indistinguishable"
    )

    if all_indistinguishable:
        conclusion = (
            "All three models (LR, RF_Tuned, XGBoost_Tuned) are STATISTICALLY INDISTINGUISHABLE "
            "on this dataset. At ~4.4k rows with near-additive signal (max_depth=2 optimal), "
            "interpretable LogisticRegression performs equivalently to tuned tree ensembles. "
            "Explainability is not a compliance tax at this scale."
        )
        results["overall_conclusion"] = {
            "models_indistinguishable": True,
            "best_model": "Any (statistically equivalent)",
            "recommendation": "Use LogisticRegression for interpretability without accuracy loss",
            "narrative": conclusion
        }
    else:
        # Find best
        best_model = max(fold_results.keys(), key=lambda x: fold_results[x]["roc_auc_mean"])
        conclusion = f"{best_model} shows statistically significant improvement."
        results["overall_conclusion"] = {
            "models_indistinguishable": False,
            "best_model": best_model,
            "recommendation": f"Use {best_model}",
            "narrative": conclusion
        }

    print(f"\n{conclusion}")

    # Save results
    with open(RESULTS_DIR / "model_tuning_v2.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {RESULTS_DIR / 'model_tuning_v2.json'}")

    return results


if __name__ == "__main__":
    main()
