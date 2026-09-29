"""
T5: Model training and evaluation
Trains and evaluates models on each feature set to test the seminar's claim:
does FS_regularity beat FS_magnitude?

Models: Logistic Regression, Random Forest, XGBoost, Soft-Voting Ensemble
Imbalance handling: Class weighting AND SMOTE (reported separately)
Evaluation: Stratified 5-fold CV with precision, recall, F1, ROC-AUC, PR-AUC
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
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from xgboost import XGBClassifier
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score,
    confusion_matrix
)
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline

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


def get_models(use_class_weight=True):
    """
    Return dict of model instances.
    If use_class_weight=True, models use balanced class weights.
    """
    if use_class_weight:
        lr = LogisticRegression(
            class_weight="balanced",
            max_iter=1000,
            random_state=RANDOM_STATE
        )
        rf = RandomForestClassifier(
            n_estimators=100,
            class_weight="balanced",
            random_state=RANDOM_STATE,
            n_jobs=-1
        )
        xgb = XGBClassifier(
            n_estimators=100,
            scale_pos_weight=3.5,  # Approximate ratio of Good/Bad
            random_state=RANDOM_STATE,
            eval_metric="logloss",
            verbosity=0
        )
    else:
        lr = LogisticRegression(
            max_iter=1000,
            random_state=RANDOM_STATE
        )
        rf = RandomForestClassifier(
            n_estimators=100,
            random_state=RANDOM_STATE,
            n_jobs=-1
        )
        xgb = XGBClassifier(
            n_estimators=100,
            random_state=RANDOM_STATE,
            eval_metric="logloss",
            verbosity=0
        )

    return {
        "LogisticRegression": lr,
        "RandomForest": rf,
        "XGBoost": xgb
    }


def evaluate_fold(y_true, y_pred, y_prob):
    """Compute all metrics for a single fold."""
    return {
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_true, y_prob),
        "pr_auc": average_precision_score(y_true, y_prob),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist()
    }


def train_evaluate_cv(X, y, model, use_smote=False):
    """
    Train and evaluate model using stratified k-fold CV.
    Returns aggregated metrics.
    """
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    fold_results = []

    for fold_idx, (train_idx, val_idx) in enumerate(skf.split(X, y)):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_val_scaled = scaler.transform(X_val)

        if use_smote:
            smote = SMOTE(random_state=RANDOM_STATE)
            X_train_scaled, y_train = smote.fit_resample(X_train_scaled, y_train)

        # Clone model for this fold
        model_clone = model.__class__(**model.get_params())
        model_clone.fit(X_train_scaled, y_train)

        y_pred = model_clone.predict(X_val_scaled)
        y_prob = model_clone.predict_proba(X_val_scaled)[:, 1]

        fold_results.append(evaluate_fold(y_val, y_pred, y_prob))

    # Aggregate metrics
    metrics = ["precision", "recall", "f1", "roc_auc", "pr_auc"]
    aggregated = {}
    for m in metrics:
        values = [r[m] for r in fold_results]
        aggregated[m] = {
            "mean": np.mean(values),
            "std": np.std(values),
            "values": values
        }

    # Sum confusion matrices
    cm_sum = np.sum([np.array(r["confusion_matrix"]) for r in fold_results], axis=0)
    aggregated["confusion_matrix"] = cm_sum.tolist()

    return aggregated


def train_ensemble(X, y, use_smote=False, use_class_weight=True):
    """
    Train soft-voting ensemble and evaluate.
    """
    models = get_models(use_class_weight)
    estimators = [
        ("lr", models["LogisticRegression"]),
        ("rf", models["RandomForest"]),
        ("xgb", models["XGBoost"])
    ]

    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    fold_results = []

    for fold_idx, (train_idx, val_idx) in enumerate(skf.split(X, y)):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_val_scaled = scaler.transform(X_val)

        if use_smote:
            smote = SMOTE(random_state=RANDOM_STATE)
            X_train_scaled, y_train_resampled = smote.fit_resample(X_train_scaled, y_train)
        else:
            y_train_resampled = y_train

        # Fresh models for each fold
        fresh_estimators = [
            ("lr", LogisticRegression(
                class_weight="balanced" if use_class_weight else None,
                max_iter=1000, random_state=RANDOM_STATE)),
            ("rf", RandomForestClassifier(
                n_estimators=100,
                class_weight="balanced" if use_class_weight else None,
                random_state=RANDOM_STATE, n_jobs=-1)),
            ("xgb", XGBClassifier(
                n_estimators=100,
                scale_pos_weight=3.5 if use_class_weight else 1,
                random_state=RANDOM_STATE, eval_metric="logloss", verbosity=0))
        ]

        ensemble = VotingClassifier(estimators=fresh_estimators, voting="soft")
        ensemble.fit(X_train_scaled, y_train_resampled)

        y_pred = ensemble.predict(X_val_scaled)
        y_prob = ensemble.predict_proba(X_val_scaled)[:, 1]

        fold_results.append(evaluate_fold(y_val, y_pred, y_prob))

    # Aggregate
    metrics = ["precision", "recall", "f1", "roc_auc", "pr_auc"]
    aggregated = {}
    for m in metrics:
        values = [r[m] for r in fold_results]
        aggregated[m] = {
            "mean": np.mean(values),
            "std": np.std(values),
            "values": values
        }
    cm_sum = np.sum([np.array(r["confusion_matrix"]) for r in fold_results], axis=0)
    aggregated["confusion_matrix"] = cm_sum.tolist()

    return aggregated


def main():
    print("=== T5: Model Training and Evaluation ===\n")
    print(f"Random state: {RANDOM_STATE}")
    print(f"CV folds: {N_FOLDS}\n")

    df, feature_info = load_features()
    y = df["target"]

    results = {
        "timestamp": datetime.now().isoformat(),
        "random_state": RANDOM_STATE,
        "n_folds": N_FOLDS,
        "n_samples": len(df),
        "class_distribution": {
            "good": int((y == 0).sum()),
            "bad": int((y == 1).sum()),
            "default_rate": float(y.mean())
        },
        "feature_sets": {},
        "library_versions": {
            "sklearn": __import__("sklearn").__version__,
            "xgboost": __import__("xgboost").__version__,
            "imblearn": __import__("imblearn").__version__
        }
    }

    feature_sets = feature_info["feature_sets"]
    imbalance_methods = ["class_weight", "smote"]

    for fs_name, fs_info in feature_sets.items():
        print(f"\n{'='*50}")
        print(f"FEATURE SET: {fs_name.upper()} ({fs_info['n_features']} features)")
        print(f"{'='*50}")

        X = df[fs_info["features"]]
        results["feature_sets"][fs_name] = {"n_features": fs_info["n_features"], "methods": {}}

        for method in imbalance_methods:
            print(f"\n--- Imbalance handling: {method} ---")
            use_smote = (method == "smote")
            use_class_weight = (method == "class_weight")

            method_results = {}

            # Individual models
            models = get_models(use_class_weight)
            for model_name, model in models.items():
                print(f"  Training {model_name}...", end=" ")
                model_results = train_evaluate_cv(X, y, model, use_smote=use_smote)
                method_results[model_name] = model_results
                print(f"ROC-AUC: {model_results['roc_auc']['mean']:.4f} (+/- {model_results['roc_auc']['std']:.4f})")

            # Ensemble
            print(f"  Training Ensemble...", end=" ")
            ensemble_results = train_ensemble(X, y, use_smote=use_smote, use_class_weight=use_class_weight)
            method_results["Ensemble"] = ensemble_results
            print(f"ROC-AUC: {ensemble_results['roc_auc']['mean']:.4f} (+/- {ensemble_results['roc_auc']['std']:.4f})")

            results["feature_sets"][fs_name]["methods"][method] = method_results

    # Save results
    RESULTS_DIR.mkdir(exist_ok=True)
    with open(RESULTS_DIR / "model_performance.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n\nResults saved to {RESULTS_DIR / 'model_performance.json'}")

    # Print summary comparison
    print("\n" + "="*70)
    print("SUMMARY: Best ROC-AUC per feature set (class_weight method)")
    print("="*70)
    print(f"{'Feature Set':<15} {'Best Model':<20} {'ROC-AUC':<15} {'PR-AUC':<15}")
    print("-"*70)

    for fs_name in feature_sets:
        method_results = results["feature_sets"][fs_name]["methods"]["class_weight"]
        best_model = max(method_results.keys(), key=lambda m: method_results[m]["roc_auc"]["mean"])
        best_roc = method_results[best_model]["roc_auc"]["mean"]
        best_pr = method_results[best_model]["pr_auc"]["mean"]
        print(f"{fs_name:<15} {best_model:<20} {best_roc:.4f}          {best_pr:.4f}")

    # The key question: does regularity beat magnitude?
    print("\n" + "="*70)
    print("KEY FINDING: Does FS_regularity beat FS_magnitude?")
    print("="*70)

    reg_best = max(
        results["feature_sets"]["regularity"]["methods"]["class_weight"].items(),
        key=lambda x: x[1]["roc_auc"]["mean"]
    )
    mag_best = max(
        results["feature_sets"]["magnitude"]["methods"]["class_weight"].items(),
        key=lambda x: x[1]["roc_auc"]["mean"]
    )

    print(f"FS_regularity best: {reg_best[0]} with ROC-AUC {reg_best[1]['roc_auc']['mean']:.4f}")
    print(f"FS_magnitude best:  {mag_best[0]} with ROC-AUC {mag_best[1]['roc_auc']['mean']:.4f}")

    diff = reg_best[1]["roc_auc"]["mean"] - mag_best[1]["roc_auc"]["mean"]
    if diff > 0:
        print(f"\n>>> RESULT: FS_regularity beats FS_magnitude by {diff:.4f} ROC-AUC")
    elif diff < 0:
        print(f"\n>>> RESULT: FS_magnitude beats FS_regularity by {-diff:.4f} ROC-AUC")
    else:
        print(f"\n>>> RESULT: FS_regularity and FS_magnitude are tied")

    return results


if __name__ == "__main__":
    main()
