"""
T9: Diagnose the LogisticRegression anomaly
Proper hyperparameter tuning for tree models to determine if LR truly wins.

Key question: Did LR beat RF/XGBoost because:
(a) Tree models were misconfigured (default max_depth = unlimited → overfitting)
(b) Dataset too small for trees
(c) Signal is genuinely close to linear

Answer determines whether Chapter 3's dual-model rationale needs rewriting.
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings("ignore")

from sklearn.model_selection import (
    StratifiedKFold, RandomizedSearchCV, cross_val_score
)
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.metrics import roc_auc_score, make_scorer
from scipy.stats import randint, uniform

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"

RANDOM_STATE = 42
N_FOLDS = 5
N_ITER = 50  # RandomizedSearchCV iterations


def load_features():
    """Load processed features and feature set definitions."""
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)
    return df, feature_info


def get_cycle01_params():
    """Document the exact hyperparameters used in Cycle 01."""
    return {
        "LogisticRegression": {
            "class_weight": "balanced",
            "max_iter": 1000,
            "C": 1.0,  # default
            "penalty": "l2",  # default
            "solver": "lbfgs"  # default
        },
        "RandomForest": {
            "n_estimators": 100,
            "max_depth": None,  # UNLIMITED - this is the problem
            "min_samples_split": 2,  # default
            "min_samples_leaf": 1,  # default
            "class_weight": "balanced"
        },
        "XGBoost": {
            "n_estimators": 100,
            "max_depth": 6,  # default
            "learning_rate": 0.3,  # default
            "min_child_weight": 1,  # default
            "subsample": 1.0,  # default - no subsampling
            "colsample_bytree": 1.0,  # default - no column sampling
            "reg_alpha": 0,  # default - no L1 regularization
            "reg_lambda": 1,  # default - minimal L2
            "scale_pos_weight": 3.5
        }
    }


def get_tuning_param_distributions():
    """
    Constrained parameter distributions for small dataset (4,368 rows).
    Aggressive depth limits and regularization.
    """
    rf_params = {
        "n_estimators": [50, 100, 200, 300],
        "max_depth": [3, 4, 5, 6, 8],  # CONSTRAINED - was unlimited
        "min_samples_split": [5, 10, 20, 50],
        "min_samples_leaf": [2, 5, 10, 20],
        "max_features": ["sqrt", "log2", 0.3, 0.5]
    }

    xgb_params = {
        "n_estimators": [50, 100, 200, 300],
        "max_depth": [2, 3, 4, 5, 6],  # CONSTRAINED
        "learning_rate": [0.01, 0.05, 0.1, 0.2],
        "min_child_weight": [1, 3, 5, 10],
        "subsample": [0.6, 0.7, 0.8, 0.9, 1.0],
        "colsample_bytree": [0.6, 0.7, 0.8, 0.9, 1.0],
        "reg_alpha": [0, 0.1, 0.5, 1.0],  # L1 regularization
        "reg_lambda": [0.5, 1.0, 2.0, 5.0]  # L2 regularization
    }

    return rf_params, xgb_params


def compute_train_val_gap(model, X, y):
    """
    Compute train vs validation ROC-AUC to diagnose overfitting.
    Returns mean train AUC, mean val AUC, and the gap.
    """
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    train_aucs = []
    val_aucs = []

    for train_idx, val_idx in skf.split(X, y):
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        model_clone = model.__class__(**model.get_params())
        model_clone.fit(X_train, y_train)

        train_proba = model_clone.predict_proba(X_train)[:, 1]
        val_proba = model_clone.predict_proba(X_val)[:, 1]

        train_aucs.append(roc_auc_score(y_train, train_proba))
        val_aucs.append(roc_auc_score(y_val, val_proba))

    return {
        "train_auc_mean": np.mean(train_aucs),
        "train_auc_std": np.std(train_aucs),
        "val_auc_mean": np.mean(val_aucs),
        "val_auc_std": np.std(val_aucs),
        "overfit_gap": np.mean(train_aucs) - np.mean(val_aucs)
    }


def main():
    print("=== T9: Diagnose LogisticRegression Anomaly ===\n")

    df, feature_info = load_features()
    feature_cols = feature_info["feature_sets"]["full"]["features"]
    X = df[feature_cols].values
    y = df["target"].values

    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    print(f"Dataset: {len(df)} samples, {len(feature_cols)} features")
    print(f"Class balance: {y.mean():.2%} positive (default)\n")

    results = {
        "timestamp": datetime.now().isoformat(),
        "dataset": {
            "n_samples": len(df),
            "n_features": len(feature_cols),
            "positive_rate": float(y.mean())
        },
        "cycle01_params": get_cycle01_params(),
        "cycle01_diagnosis": {},
        "tuned_models": {},
        "comparison": {}
    }

    # ===== STEP 1: Document Cycle 01 overfitting =====
    print("=" * 60)
    print("STEP 1: Diagnose Cycle 01 overfitting")
    print("=" * 60)

    cycle01_models = {
        "LogisticRegression": LogisticRegression(
            class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE
        ),
        "RandomForest_C01": RandomForestClassifier(
            n_estimators=100, class_weight="balanced",
            random_state=RANDOM_STATE, n_jobs=1
            # NOTE: max_depth=None (unlimited) - the likely culprit
        ),
        "XGBoost_C01": XGBClassifier(
            n_estimators=100, scale_pos_weight=3.5,
            random_state=RANDOM_STATE, eval_metric="logloss", verbosity=0
        )
    }

    print(f"\n{'Model':<25} {'Train AUC':<12} {'Val AUC':<12} {'Gap':<10} {'Diagnosis'}")
    print("-" * 75)

    for name, model in cycle01_models.items():
        gap_info = compute_train_val_gap(model, X_scaled, y)
        results["cycle01_diagnosis"][name] = gap_info

        gap = gap_info["overfit_gap"]
        if gap > 0.15:
            diagnosis = "SEVERE OVERFIT"
        elif gap > 0.08:
            diagnosis = "MODERATE OVERFIT"
        elif gap > 0.03:
            diagnosis = "MILD OVERFIT"
        else:
            diagnosis = "OK"

        print(f"{name:<25} {gap_info['train_auc_mean']:.4f}       "
              f"{gap_info['val_auc_mean']:.4f}       {gap:.4f}     {diagnosis}")

    # ===== STEP 2: Hyperparameter tuning =====
    print("\n" + "=" * 60)
    print("STEP 2: RandomizedSearchCV tuning (50 iterations)")
    print("=" * 60)

    rf_params, xgb_params = get_tuning_param_distributions()
    cv = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    scorer = make_scorer(roc_auc_score, needs_proba=True)

    # Tune RandomForest
    print("\nTuning RandomForest...")
    rf_base = RandomForestClassifier(
        class_weight="balanced", random_state=RANDOM_STATE, n_jobs=1
    )
    rf_search = RandomizedSearchCV(
        rf_base, rf_params, n_iter=N_ITER, cv=cv, scoring=scorer,
        random_state=RANDOM_STATE, n_jobs=1, verbose=1
    )
    rf_search.fit(X_scaled, y)
    rf_best = rf_search.best_estimator_

    print(f"  Best params: {rf_search.best_params_}")
    print(f"  Best CV ROC-AUC: {rf_search.best_score_:.4f}")

    results["tuned_models"]["RandomForest"] = {
        "best_params": rf_search.best_params_,
        "best_cv_score": float(rf_search.best_score_)
    }

    # Tune XGBoost
    print("\nTuning XGBoost...")
    xgb_base = XGBClassifier(
        scale_pos_weight=3.5, random_state=RANDOM_STATE,
        eval_metric="logloss", verbosity=0
    )
    xgb_search = RandomizedSearchCV(
        xgb_base, xgb_params, n_iter=N_ITER, cv=cv, scoring=scorer,
        random_state=RANDOM_STATE, n_jobs=1, verbose=0
    )
    xgb_search.fit(X_scaled, y)
    xgb_best = xgb_search.best_estimator_

    print(f"  Best params: {xgb_search.best_params_}")
    print(f"  Best CV ROC-AUC: {xgb_search.best_score_:.4f}")

    results["tuned_models"]["XGBoost"] = {
        "best_params": {k: (int(v) if isinstance(v, np.integer) else
                           float(v) if isinstance(v, np.floating) else v)
                       for k, v in xgb_search.best_params_.items()},
        "best_cv_score": float(xgb_search.best_score_)
    }

    # ===== STEP 3: Compare all models post-tuning =====
    print("\n" + "=" * 60)
    print("STEP 3: Final comparison (train/val gap for tuned models)")
    print("=" * 60)

    final_models = {
        "LogisticRegression": LogisticRegression(
            class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE
        ),
        "RandomForest_Tuned": rf_best,
        "XGBoost_Tuned": xgb_best,
        "RandomForest_C01": RandomForestClassifier(
            n_estimators=100, class_weight="balanced",
            random_state=RANDOM_STATE, n_jobs=1
        ),
        "XGBoost_C01": XGBClassifier(
            n_estimators=100, scale_pos_weight=3.5,
            random_state=RANDOM_STATE, eval_metric="logloss", verbosity=0
        )
    }

    print(f"\n{'Model':<25} {'Train AUC':<12} {'Val AUC':<12} {'Gap':<10}")
    print("-" * 60)

    final_comparison = []
    for name, model in final_models.items():
        gap_info = compute_train_val_gap(model, X_scaled, y)
        results["comparison"][name] = gap_info
        final_comparison.append((name, gap_info["val_auc_mean"], gap_info))

        print(f"{name:<25} {gap_info['train_auc_mean']:.4f}       "
              f"{gap_info['val_auc_mean']:.4f}       {gap_info['overfit_gap']:.4f}")

    # Rank by validation AUC
    final_comparison.sort(key=lambda x: x[1], reverse=True)

    print("\n" + "=" * 60)
    print("FINAL RANKING (by validation ROC-AUC)")
    print("=" * 60)
    for rank, (name, val_auc, _) in enumerate(final_comparison, 1):
        marker = " <-- WINNER" if rank == 1 else ""
        print(f"  {rank}. {name}: {val_auc:.4f}{marker}")

    winner = final_comparison[0][0]
    results["winner"] = winner
    results["lr_still_wins"] = "LogisticRegression" in winner

    # ===== CONCLUSION =====
    print("\n" + "=" * 60)
    print("CONCLUSION")
    print("=" * 60)

    if results["lr_still_wins"]:
        print("\n>>> LogisticRegression STILL WINS after proper tuning.")
        print("    This is a legitimate finding, not a configuration error.")
        print("    Implication: On thin-file data at this scale (~4.4k rows),")
        print("    interpretable models are NOT a compliance tax.")
        print("    Chapter 3's dual-model rationale needs revision.")
        results["conclusion"] = (
            "LR wins after tuning. Signal is close to linear or dataset "
            "too small for trees. Chapter 3 rationale needs revision."
        )
    else:
        lr_val = [x[1] for x in final_comparison if "LogisticRegression" in x[0]][0]
        winner_val = final_comparison[0][1]
        print(f"\n>>> {winner} beats LR by {winner_val - lr_val:.4f} ROC-AUC")
        print("    Cycle 01 tree results were due to misconfiguration (overfitting).")
        print("    Proper regularization restores expected ranking.")
        results["conclusion"] = (
            f"{winner} wins after tuning. Cycle 01 issue was overfitting "
            f"due to unlimited depth/weak regularization."
        )

    # Save results
    with open(RESULTS_DIR / "model_tuning.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to {RESULTS_DIR / 'model_tuning.json'}")

    return results


if __name__ == "__main__":
    main()
