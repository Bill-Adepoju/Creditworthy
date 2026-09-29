"""
T7: SHAP Explainability
Computes global feature importance and local explanations.
Backs the regulatory-auditability argument in Chapter 2.

Per CLAUDE.md: This code gets quoted in Chapter 4.
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings("ignore")

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
import shap
import matplotlib.pyplot as plt

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"

RANDOM_STATE = 42


def load_data():
    """Load processed features."""
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)
    return df, feature_info


def main():
    print("=== T7: SHAP Explainability ===\n")

    df, feature_info = load_data()

    # Use full feature set for explainability
    feature_cols = feature_info["feature_sets"]["full"]["features"]
    X = df[feature_cols]
    y = df["target"]

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE
    )

    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train model
    model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    model.fit(X_train_scaled, y_train)

    print(f"Model: LogisticRegression")
    print(f"Features: {len(feature_cols)}")
    print(f"Training samples: {len(X_train)}")
    print(f"Test samples: {len(X_test)}")

    # SHAP explainer for linear model
    print("\nComputing SHAP values...")

    # For linear models, use LinearExplainer
    explainer = shap.LinearExplainer(model, X_train_scaled, feature_names=feature_cols)
    shap_values = explainer.shap_values(X_test_scaled)

    # Global feature importance (mean absolute SHAP value)
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    feature_importance = pd.DataFrame({
        "feature": feature_cols,
        "mean_abs_shap": mean_abs_shap
    }).sort_values("mean_abs_shap", ascending=False)

    print("\n=== Global Feature Importance (Top 15) ===")
    print(feature_importance.head(15).to_string(index=False))

    # Identify regularity vs magnitude features
    regularity_features = [
        "repay_delay_mean", "repay_delay_std", "early_repay_ratio",
        "loan_count", "relationship_tenure_days", "interval_regularity",
        "interval_mean", "term_escalation"
    ]
    magnitude_features = [
        "amount_mean", "amount_max", "amount_total", "amount_cv",
        "totaldue_mean", "term_mean"
    ]

    reg_importance = feature_importance[feature_importance["feature"].isin(regularity_features)]["mean_abs_shap"].sum()
    mag_importance = feature_importance[feature_importance["feature"].isin(magnitude_features)]["mean_abs_shap"].sum()

    print(f"\n=== Regularity vs Magnitude Importance ===")
    print(f"Total regularity features importance: {reg_importance:.4f}")
    print(f"Total magnitude features importance:  {mag_importance:.4f}")
    print(f"Ratio (regularity/magnitude): {reg_importance/mag_importance:.2f}x")

    # Local explanations for a few examples
    print("\n=== Local Explanations (3 examples) ===")

    # Find examples: one default, one non-default, one borderline
    default_idx = np.where(y_test.values == 1)[0][0]
    nondefault_idx = np.where(y_test.values == 0)[0][0]

    # Borderline: closest to 0.5 probability
    probs = model.predict_proba(X_test_scaled)[:, 1]
    borderline_idx = np.argmin(np.abs(probs - 0.5))

    local_examples = [
        ("Default case", default_idx),
        ("Non-default case", nondefault_idx),
        ("Borderline case", borderline_idx)
    ]

    local_explanations = []
    for name, idx in local_examples:
        actual = y_test.iloc[idx]
        prob = probs[idx]
        sv = shap_values[idx]

        # Top 5 features by absolute SHAP value
        top_indices = np.argsort(np.abs(sv))[-5:][::-1]
        top_features = [(feature_cols[i], sv[i]) for i in top_indices]

        print(f"\n{name}:")
        print(f"  Actual: {'Default' if actual == 1 else 'Non-default'}")
        print(f"  P(default): {prob:.3f}")
        print(f"  Top contributing features:")
        for feat, val in top_features:
            direction = "+" if val > 0 else ""
            print(f"    {feat}: {direction}{val:.4f}")

        local_explanations.append({
            "name": name,
            "actual": int(actual),
            "probability": float(prob),
            "top_features": [{"feature": f, "shap_value": float(v)} for f, v in top_features]
        })

    # Save global importance plot
    fig, ax = plt.subplots(figsize=(10, 8))
    top_features_df = feature_importance.head(15)
    colors = []
    for f in top_features_df["feature"]:
        if f in regularity_features:
            colors.append("#2E86AB")  # Blue for regularity
        elif f in magnitude_features:
            colors.append("#E94F37")  # Red for magnitude
        else:
            colors.append("#A5A5A5")  # Gray for demographic

    ax.barh(range(len(top_features_df)), top_features_df["mean_abs_shap"].values, color=colors)
    ax.set_yticks(range(len(top_features_df)))
    ax.set_yticklabels(top_features_df["feature"].values)
    ax.invert_yaxis()
    ax.set_xlabel("Mean |SHAP value|", fontsize=12)
    ax.set_title("Global Feature Importance (SHAP)\nBlue=Regularity, Red=Magnitude, Gray=Demographic", fontsize=14)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "shap_global.png", dpi=150)
    print(f"\nGlobal importance plot saved to {RESULTS_DIR / 'shap_global.png'}")

    # Save SHAP summary plot
    fig, ax = plt.subplots(figsize=(10, 8))
    shap.summary_plot(shap_values, X_test_scaled, feature_names=feature_cols,
                      show=False, max_display=15)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "shap_summary.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"SHAP summary plot saved to {RESULTS_DIR / 'shap_summary.png'}")

    # Save results
    results = {
        "timestamp": datetime.now().isoformat(),
        "model": "LogisticRegression",
        "n_features": len(feature_cols),
        "n_test_samples": len(X_test),
        "global_importance": feature_importance.to_dict(orient="records"),
        "category_importance": {
            "regularity_total": float(reg_importance),
            "magnitude_total": float(mag_importance),
            "ratio": float(reg_importance / mag_importance)
        },
        "local_explanations": local_explanations
    }

    with open(RESULTS_DIR / "shap_global.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {RESULTS_DIR / 'shap_global.json'}")

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Top 5 most important features:")
    for i, row in feature_importance.head(5).iterrows():
        print(f"  {row['feature']}: {row['mean_abs_shap']:.4f}")
    print(f"\nRegularity vs Magnitude importance ratio: {reg_importance/mag_importance:.2f}x")
    print("(Higher ratio supports the seminar's claim that regularity matters more)")

    return results


if __name__ == "__main__":
    main()
