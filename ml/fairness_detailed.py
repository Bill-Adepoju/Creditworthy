"""
T12: Fairness Analysis - Subgroup Sizes, Confidence Intervals, Trade-off Curve

Requirements:
1. Report n per subgroup for all four protected attributes
2. Report confidence intervals on DPD and EOD
3. Per-subgroup threshold recalibration
4. Accuracy-fairness trade-off curve (fairness_tradeoff.png)
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings("ignore")

from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    roc_auc_score, accuracy_score, precision_score, recall_score
)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"

RANDOM_STATE = 42
N_BOOTSTRAP = 500  # For confidence intervals


def load_data():
    """Load features and demographics."""
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    demo = pd.read_csv(DATA_DIR / "traindemographics.csv")

    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)

    # Merge demographics
    df = df.merge(demo[["customerid", "bank_account_type", "employment_status_clients"]],
                  on="customerid", how="left")

    return df, feature_info


def create_sensitive_attributes(df):
    """Create age_band and region from raw data."""
    # Load raw performance data for additional fields
    perf = pd.read_csv(DATA_DIR / "trainperf.csv")
    demo = pd.read_csv(DATA_DIR / "traindemographics.csv")

    # Get birthdate for age calculation
    if "birthdate" in demo.columns:
        df = df.merge(demo[["customerid", "birthdate"]], on="customerid", how="left")
        # Calculate age (approximate)
        df["birthdate"] = pd.to_datetime(df["birthdate"], errors="coerce")
        ref_date = pd.Timestamp("2019-01-01")  # Approximate reference
        df["age"] = (ref_date - df["birthdate"]).dt.days / 365.25
        df["age_band"] = pd.cut(df["age"], bins=[0, 25, 35, 45, 55, 100],
                                labels=["18-25", "26-35", "36-45", "46-55", "55+"])
    else:
        df["age_band"] = "Unknown"

    # Region from longitude bands (if available)
    if "longitude_gps" in demo.columns:
        df_temp = df.merge(demo[["customerid", "longitude_gps"]], on="customerid", how="left")
        # Nigeria longitude bands (approximate)
        df["region"] = pd.cut(df_temp["longitude_gps"],
                             bins=[0, 5, 8, 10, 15],
                             labels=["West", "South-West", "Central", "North"])
    else:
        df["region"] = "Unknown"

    return df


def compute_fairness_metrics(y_true, y_pred, sensitive_attr):
    """
    Compute DPD and EOD for a sensitive attribute.
    """
    groups = np.unique(sensitive_attr[~pd.isna(sensitive_attr)])
    group_rates = {}

    for g in groups:
        mask = sensitive_attr == g
        if mask.sum() == 0:
            continue

        # Positive prediction rate (for DPD)
        pred_rate = y_pred[mask].mean()

        # TPR and FPR (for EOD)
        y_t = y_true[mask]
        y_p = y_pred[mask]

        tpr = (y_p[y_t == 1].sum() / (y_t == 1).sum()) if (y_t == 1).sum() > 0 else 0
        fpr = (y_p[y_t == 0].sum() / (y_t == 0).sum()) if (y_t == 0).sum() > 0 else 0

        group_rates[g] = {
            "n": int(mask.sum()),
            "pred_rate": float(pred_rate),
            "tpr": float(tpr),
            "fpr": float(fpr)
        }

    # Compute DPD (max - min positive prediction rate)
    pred_rates = [v["pred_rate"] for v in group_rates.values()]
    dpd = max(pred_rates) - min(pred_rates) if pred_rates else 0

    # Compute EOD (max difference in TPR or FPR)
    tprs = [v["tpr"] for v in group_rates.values()]
    fprs = [v["fpr"] for v in group_rates.values()]

    tpr_diff = max(tprs) - min(tprs) if tprs else 0
    fpr_diff = max(fprs) - min(fprs) if fprs else 0
    eod = max(tpr_diff, fpr_diff)

    return {
        "dpd": float(dpd),
        "eod": float(eod),
        "group_stats": group_rates
    }


def bootstrap_fairness_ci(y_true, y_pred, sensitive_attr, n_bootstrap=500, ci=0.95):
    """
    Bootstrap confidence intervals for DPD and EOD.
    """
    n = len(y_true)
    dpd_samples = []
    eod_samples = []

    np.random.seed(RANDOM_STATE)

    for _ in range(n_bootstrap):
        idx = np.random.choice(n, n, replace=True)
        metrics = compute_fairness_metrics(
            y_true[idx], y_pred[idx], sensitive_attr.iloc[idx]
        )
        dpd_samples.append(metrics["dpd"])
        eod_samples.append(metrics["eod"])

    alpha = (1 - ci) / 2
    dpd_ci = (np.percentile(dpd_samples, alpha * 100),
              np.percentile(dpd_samples, (1 - alpha) * 100))
    eod_ci = (np.percentile(eod_samples, alpha * 100),
              np.percentile(eod_samples, (1 - alpha) * 100))

    return {
        "dpd_mean": float(np.mean(dpd_samples)),
        "dpd_ci_lower": float(dpd_ci[0]),
        "dpd_ci_upper": float(dpd_ci[1]),
        "eod_mean": float(np.mean(eod_samples)),
        "eod_ci_lower": float(eod_ci[0]),
        "eod_ci_upper": float(eod_ci[1])
    }


def threshold_recalibration(y_proba, y_true, sensitive_attr, target_fpr=0.3):
    """
    Find per-group thresholds that equalize FPR across groups.
    """
    groups = np.unique(sensitive_attr[~pd.isna(sensitive_attr)])
    thresholds = {}

    for g in groups:
        mask = sensitive_attr == g
        if mask.sum() < 10:
            thresholds[str(g)] = 0.5
            continue

        y_p = y_proba[mask]
        y_t = y_true[mask]

        # Find threshold that achieves target FPR
        negatives = y_t == 0
        if negatives.sum() == 0:
            thresholds[str(g)] = 0.5
            continue

        # Sort by probability and find threshold
        sorted_idx = np.argsort(y_p[negatives])[::-1]
        sorted_probs = y_p[negatives][sorted_idx]

        target_fp = int(target_fpr * negatives.sum())
        if target_fp >= len(sorted_probs):
            threshold = sorted_probs[-1] - 0.001
        elif target_fp == 0:
            threshold = sorted_probs[0] + 0.001
        else:
            threshold = sorted_probs[target_fp]

        thresholds[str(g)] = float(threshold)

    return thresholds


def compute_accuracy_at_threshold(y_proba, y_true, threshold):
    """Compute accuracy at a given threshold."""
    y_pred = (y_proba >= threshold).astype(int)
    return accuracy_score(y_true, y_pred)


def create_tradeoff_curve(y_proba, y_true, sensitive_attr, attr_name):
    """
    Create accuracy-fairness trade-off curve by varying threshold.
    """
    thresholds = np.linspace(0.1, 0.9, 50)
    accuracies = []
    dpds = []
    eods = []

    for thresh in thresholds:
        y_pred = (y_proba >= thresh).astype(int)
        acc = accuracy_score(y_true, y_pred)
        metrics = compute_fairness_metrics(y_true, y_pred, sensitive_attr)

        accuracies.append(acc)
        dpds.append(metrics["dpd"])
        eods.append(metrics["eod"])

    return {
        "thresholds": thresholds.tolist(),
        "accuracies": accuracies,
        "dpds": dpds,
        "eods": eods
    }


def plot_tradeoff_curves(tradeoff_data, output_path):
    """Create fairness trade-off plot."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    attr_names = list(tradeoff_data.keys())

    for idx, attr in enumerate(attr_names):
        ax = axes[idx // 2, idx % 2]
        data = tradeoff_data[attr]

        ax.plot(data["accuracies"], data["dpds"], 'b-', label="DPD", linewidth=2)
        ax.plot(data["accuracies"], data["eods"], 'r--', label="EOD", linewidth=2)

        # Mark fairness threshold
        ax.axhline(y=0.1, color='g', linestyle=':', alpha=0.7, label="Fair threshold (0.1)")

        ax.set_xlabel("Accuracy")
        ax.set_ylabel("Fairness Disparity")
        ax.set_title(f"Trade-off: {attr}")
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0.4, 0.9)
        ax.set_ylim(0, 1)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()


def main():
    print("=== T12: Fairness Detailed Analysis ===\n")

    df, feature_info = load_data()
    df = create_sensitive_attributes(df)

    results = {
        "timestamp": datetime.now().isoformat(),
        "sensitive_attributes": {},
        "confidence_intervals": {},
        "threshold_recalibration": {},
        "tradeoff_curves": {}
    }

    # Prepare features and model
    feature_cols = feature_info["feature_sets"]["full"]["features"]

    # Handle any NaN values in features
    X = df[feature_cols].fillna(0).values
    y = df["target"].values

    # Train/test split
    X_train, X_test, y_train, y_test, idx_train, idx_test = train_test_split(
        X, y, np.arange(len(df)), test_size=0.2, stratify=y, random_state=RANDOM_STATE
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    model.fit(X_train_scaled, y_train)

    y_proba = model.predict_proba(X_test_scaled)[:, 1]
    y_pred = model.predict(X_test_scaled)

    # Define sensitive attributes
    sensitive_attrs = {
        "region": df.iloc[idx_test]["region"],
        "age_band": df.iloc[idx_test]["age_band"],
        "bank_account_type": df.iloc[idx_test]["bank_account_type"],
        "employment_status": df.iloc[idx_test]["employment_status_clients"]
    }

    # Fill missing values for consistent analysis
    for attr in sensitive_attrs:
        # Convert to string to handle categorical columns
        sensitive_attrs[attr] = sensitive_attrs[attr].astype(str).replace("nan", "Unknown").replace("", "Unknown")

    # Part 1: Subgroup sizes and base metrics
    print("=" * 60)
    print("PART 1: Subgroup Sizes and Fairness Metrics")
    print("=" * 60)

    for attr_name, attr_values in sensitive_attrs.items():
        print(f"\n--- {attr_name} ---")

        metrics = compute_fairness_metrics(y_test, y_pred, attr_values)
        results["sensitive_attributes"][attr_name] = metrics

        print(f"  DPD: {metrics['dpd']:.3f}, EOD: {metrics['eod']:.3f}")
        print(f"  {'Subgroup':<20} {'N':<8} {'Pred Rate':<12} {'TPR':<8} {'FPR'}")
        print("  " + "-" * 55)

        for group, stats in sorted(metrics["group_stats"].items(),
                                    key=lambda x: x[1]["n"], reverse=True):
            print(f"  {str(group):<20} {stats['n']:<8} "
                  f"{stats['pred_rate']:.3f}        "
                  f"{stats['tpr']:.3f}    {stats['fpr']:.3f}")

    # Part 2: Confidence intervals
    print("\n" + "=" * 60)
    print("PART 2: Bootstrap Confidence Intervals (95%, n=500)")
    print("=" * 60)

    print(f"\n{'Attribute':<25} {'DPD':<25} {'EOD'}")
    print("-" * 70)

    for attr_name, attr_values in sensitive_attrs.items():
        ci = bootstrap_fairness_ci(y_test, y_pred, attr_values, N_BOOTSTRAP)
        results["confidence_intervals"][attr_name] = ci

        dpd_str = f"{ci['dpd_mean']:.3f} [{ci['dpd_ci_lower']:.3f}, {ci['dpd_ci_upper']:.3f}]"
        eod_str = f"{ci['eod_mean']:.3f} [{ci['eod_ci_lower']:.3f}, {ci['eod_ci_upper']:.3f}]"
        print(f"{attr_name:<25} {dpd_str:<25} {eod_str}")

    # Part 3: Threshold recalibration
    print("\n" + "=" * 60)
    print("PART 3: Per-Subgroup Threshold Recalibration")
    print("=" * 60)

    for attr_name, attr_values in sensitive_attrs.items():
        thresholds = threshold_recalibration(y_proba, y_test, attr_values)
        results["threshold_recalibration"][attr_name] = thresholds

        print(f"\n{attr_name} (target FPR=0.3):")
        for group, thresh in thresholds.items():
            print(f"  {group}: threshold = {thresh:.3f}")

    # Part 4: Trade-off curves
    print("\n" + "=" * 60)
    print("PART 4: Accuracy-Fairness Trade-off Curves")
    print("=" * 60)

    tradeoff_data = {}
    for attr_name, attr_values in sensitive_attrs.items():
        tradeoff = create_tradeoff_curve(y_proba, y_test, attr_values, attr_name)
        tradeoff_data[attr_name] = tradeoff
        results["tradeoff_curves"][attr_name] = {
            "n_points": len(tradeoff["thresholds"]),
            "accuracy_range": [min(tradeoff["accuracies"]), max(tradeoff["accuracies"])],
            "dpd_range": [min(tradeoff["dpds"]), max(tradeoff["dpds"])],
            "eod_range": [min(tradeoff["eods"]), max(tradeoff["eods"])]
        }

    # Create plot
    plot_path = RESULTS_DIR / "fairness_tradeoff.png"
    plot_tradeoff_curves(tradeoff_data, plot_path)
    print(f"\nTrade-off curves saved to {plot_path}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print("\nSubgroups with n < 30 (unreliable estimates):")
    for attr_name, metrics in results["sensitive_attributes"].items():
        small_groups = [(g, s["n"]) for g, s in metrics["group_stats"].items() if s["n"] < 30]
        if small_groups:
            for g, n in small_groups:
                print(f"  {attr_name}/{g}: n={n}")

    print("\nAttributes NOT meeting 0.1 fairness threshold:")
    for attr_name, ci in results["confidence_intervals"].items():
        if ci["dpd_ci_lower"] > 0.1 or ci["eod_ci_lower"] > 0.1:
            print(f"  {attr_name}: DPD={ci['dpd_mean']:.3f}, EOD={ci['eod_mean']:.3f}")

    # Model performance on test set
    roc_auc = roc_auc_score(y_test, y_proba)
    accuracy = accuracy_score(y_test, y_pred)
    results["model_performance"] = {
        "roc_auc": float(roc_auc),
        "accuracy": float(accuracy),
        "test_size": len(y_test)
    }

    print(f"\nModel performance (test set): ROC-AUC={roc_auc:.4f}, Accuracy={accuracy:.4f}")

    # Save results
    with open(RESULTS_DIR / "fairness_detailed.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {RESULTS_DIR / 'fairness_detailed.json'}")

    return results


if __name__ == "__main__":
    main()
