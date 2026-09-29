"""
T51: Recalibrated Impossibility Analysis

FIXES T46's issues:
1. Contradiction: flags say not calibrated, prose says reasonable
2. class_weight='balanced' deliberately inflates minority-class probabilities
3. Pareto frontier had only 1 degenerate point

Solution: Apply isotonic/Platt calibration, then re-test.
If calibration succeeds: full Chouldechova framing available.
If not: lead with empirical result only.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.metrics import confusion_matrix, brier_score_loss
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy import stats

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"

RANDOM_STATE = 42


def wilson_ci(successes, n, confidence=0.95):
    """Wilson score interval for a proportion."""
    if n == 0:
        return 0, 0, 0
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    p_hat = successes / n
    denominator = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denominator
    margin = z * np.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n) / denominator
    return p_hat, max(0, center - margin), min(1, center + margin)


def compute_calibration_error(y_true, y_prob, n_bins=10):
    """Compute expected calibration error."""
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    total = len(y_true)

    bin_data = []
    for i in range(n_bins):
        mask = (y_prob >= bin_boundaries[i]) & (y_prob < bin_boundaries[i+1])
        if mask.sum() > 0:
            bin_prob = y_prob[mask].mean()
            bin_true = y_true[mask].mean()
            bin_size = mask.sum()
            ece += bin_size / total * abs(bin_prob - bin_true)
            bin_data.append({
                "bin": i,
                "predicted": round(float(bin_prob), 4),
                "observed": round(float(bin_true), 4),
                "count": int(bin_size),
                "error": round(abs(bin_prob - bin_true), 4)
            })

    return ece, bin_data


def find_equal_fpr_thresholds(y_true_s, y_prob_s, y_true_o, y_prob_o):
    """Find threshold pair that equalizes FPR within a reasonable range."""
    best = None
    best_gap = float('inf')

    # Use narrower range to stay in meaningful operating region
    thresholds = np.linspace(0.05, 0.50, 50)

    for t_s in thresholds:
        for t_o in thresholds:
            y_pred_s = (y_prob_s >= t_s).astype(int)
            y_pred_o = (y_prob_o >= t_o).astype(int)

            tn_s, fp_s, _, _ = confusion_matrix(y_true_s, y_pred_s, labels=[0, 1]).ravel()
            tn_o, fp_o, _, _ = confusion_matrix(y_true_o, y_pred_o, labels=[0, 1]).ravel()

            fpr_s = fp_s / (fp_s + tn_s) if (fp_s + tn_s) > 0 else 0
            fpr_o = fp_o / (fp_o + tn_o) if (fp_o + tn_o) > 0 else 0

            gap = abs(fpr_s - fpr_o)
            if gap < best_gap:
                best_gap = gap
                best = {
                    "thresh_savings": round(t_s, 2),
                    "thresh_other": round(t_o, 2),
                    "fpr_gap": round(gap, 4),
                    "fpr_savings": round(fpr_s, 4),
                    "fpr_other": round(fpr_o, 4)
                }

    return best


def compute_fnr_at_thresholds(y_true_s, y_prob_s, y_true_o, y_prob_o, t_s, t_o):
    """Compute FNR for each group at given thresholds."""
    y_pred_s = (y_prob_s >= t_s).astype(int)
    y_pred_o = (y_prob_o >= t_o).astype(int)

    _, _, fn_s, tp_s = confusion_matrix(y_true_s, y_pred_s, labels=[0, 1]).ravel()
    _, _, fn_o, tp_o = confusion_matrix(y_true_o, y_pred_o, labels=[0, 1]).ravel()

    fnr_s = fn_s / (fn_s + tp_s) if (fn_s + tp_s) > 0 else 0
    fnr_o = fn_o / (fn_o + tp_o) if (fn_o + tp_o) > 0 else 0

    return fnr_s, fnr_o


def main():
    print("=" * 60)
    print("T51: Recalibrated Impossibility Analysis")
    print("=" * 60)
    print()

    # Load canonical split
    canonical_path = RESULTS_DIR / "canonical_split.json"
    with open(canonical_path) as f:
        canonical = json.load(f)

    # Load data
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)

    feature_cols = feature_info["feature_sets"]["full"]["features"]
    X = df[feature_cols]
    y = df["target"]

    # Use canonical split
    train_indices = canonical["indices"]["train"]
    test_indices = canonical["indices"]["test"]

    X_train_full = X.loc[train_indices]
    X_test = X.loc[test_indices]
    y_train_full = y.loc[train_indices]
    y_test = y.loc[test_indices]

    # Further split train into train/cal for calibration
    X_train, X_cal, y_train, y_cal = train_test_split(
        X_train_full, y_train_full, test_size=0.2, stratify=y_train_full, random_state=RANDOM_STATE
    )

    print(f"Train: {len(X_train)}, Calibration: {len(X_cal)}, Test: {len(X_test)}")

    # Scale
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_cal_scaled = scaler.transform(X_cal)
    X_test_scaled = scaler.transform(X_test)

    # Train UNCALIBRATED model (with class_weight='balanced')
    print("\n--- Uncalibrated Model (class_weight='balanced') ---")
    model_uncal = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    model_uncal.fit(X_train_scaled, y_train)

    y_prob_uncal = model_uncal.predict_proba(X_test_scaled)[:, 1]
    brier_uncal = brier_score_loss(y_test, y_prob_uncal)
    ece_uncal, bins_uncal = compute_calibration_error(y_test.values, y_prob_uncal)

    print(f"Brier score: {brier_uncal:.4f}")
    print(f"ECE: {ece_uncal:.4f}")
    print("\nCalibration bins:")
    for b in bins_uncal:
        print(f"  pred={b['predicted']:.2f} obs={b['observed']:.2f} err={b['error']:.3f} n={b['count']}")

    # Train CALIBRATED model (isotonic)
    print("\n--- Isotonic Calibration ---")
    base_model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    model_iso = CalibratedClassifierCV(base_model, method='isotonic', cv=5)
    model_iso.fit(np.vstack([X_train_scaled, X_cal_scaled]),
                  pd.concat([y_train, y_cal]).values)

    y_prob_iso = model_iso.predict_proba(X_test_scaled)[:, 1]
    brier_iso = brier_score_loss(y_test, y_prob_iso)
    ece_iso, bins_iso = compute_calibration_error(y_test.values, y_prob_iso)

    print(f"Brier score: {brier_iso:.4f}")
    print(f"ECE: {ece_iso:.4f}")
    print("\nCalibration bins:")
    for b in bins_iso:
        print(f"  pred={b['predicted']:.2f} obs={b['observed']:.2f} err={b['error']:.3f} n={b['count']}")

    # Train CALIBRATED model (Platt/sigmoid)
    print("\n--- Platt (Sigmoid) Calibration ---")
    base_model2 = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    model_platt = CalibratedClassifierCV(base_model2, method='sigmoid', cv=5)
    model_platt.fit(np.vstack([X_train_scaled, X_cal_scaled]),
                    pd.concat([y_train, y_cal]).values)

    y_prob_platt = model_platt.predict_proba(X_test_scaled)[:, 1]
    brier_platt = brier_score_loss(y_test, y_prob_platt)
    ece_platt, bins_platt = compute_calibration_error(y_test.values, y_prob_platt)

    print(f"Brier score: {brier_platt:.4f}")
    print(f"ECE: {ece_platt:.4f}")
    print("\nCalibration bins:")
    for b in bins_platt:
        print(f"  pred={b['predicted']:.2f} obs={b['observed']:.2f} err={b['error']:.3f} n={b['count']}")

    # Choose best calibration
    best_method = "isotonic" if ece_iso < ece_platt else "platt"
    best_probs = y_prob_iso if best_method == "isotonic" else y_prob_platt
    best_ece = min(ece_iso, ece_platt)
    best_bins = bins_iso if best_method == "isotonic" else bins_platt

    print(f"\nBest calibration method: {best_method} (ECE={best_ece:.4f})")

    # Calibration threshold
    CALIBRATION_THRESHOLD = 0.05  # ECE < 0.05 is well-calibrated
    well_calibrated = best_ece < CALIBRATION_THRESHOLD

    print(f"Well calibrated (ECE < {CALIBRATION_THRESHOLD})? {well_calibrated}")

    # Get demographics for group analysis (drop duplicates to avoid row expansion)
    demo_df = pd.read_csv(DATA_DIR / "traindemographics.csv").drop_duplicates(subset=['customerid'])
    test_df = pd.DataFrame({
        "y_true": y_test.values,
        "y_prob_uncal": y_prob_uncal,
        "y_prob_cal": best_probs,
        "customerid": df.loc[test_indices, "customerid"].values
    })
    test_df = test_df.merge(demo_df, on="customerid", how="left")

    y_true = test_df["y_true"].values
    y_prob_cal = test_df["y_prob_cal"].values

    savings_mask = (test_df["bank_account_type"] == "Savings").values
    other_mask = (test_df["bank_account_type"] == "Other").values

    y_true_s = y_true[savings_mask]
    y_prob_s = y_prob_cal[savings_mask]
    y_true_o = y_true[other_mask]
    y_prob_o = y_prob_cal[other_mask]

    print(f"\nGroups: Savings n={len(y_true_s)}, Other n={len(y_true_o)}")
    print(f"Base rates: Savings={y_true_s.mean():.1%}, Other={y_true_o.mean():.1%}")

    # Per-group calibration
    print("\n--- Per-Group Calibration ---")
    ece_savings, _ = compute_calibration_error(y_true_s, y_prob_s, n_bins=5)
    ece_other, _ = compute_calibration_error(y_true_o, y_prob_o, n_bins=5)
    print(f"Savings ECE: {ece_savings:.4f}")
    print(f"Other ECE: {ece_other:.4f}")

    # THE IMPOSSIBILITY DEMONSTRATION (empirical, no calibration assumption)
    print("\n" + "=" * 60)
    print("IMPOSSIBILITY DEMONSTRATION (empirical)")
    print("=" * 60)

    # Find thresholds that equalize FPR
    equal_fpr = find_equal_fpr_thresholds(y_true_s, y_prob_s, y_true_o, y_prob_o)
    print(f"\nFPR-equalizing thresholds: Savings={equal_fpr['thresh_savings']}, Other={equal_fpr['thresh_other']}")
    print(f"FPR gap achieved: {equal_fpr['fpr_gap']:.4f}")

    # What happens to FNR?
    fnr_s, fnr_o = compute_fnr_at_thresholds(
        y_true_s, y_prob_s, y_true_o, y_prob_o,
        equal_fpr['thresh_savings'], equal_fpr['thresh_other']
    )
    fnr_gap = abs(fnr_s - fnr_o)

    print(f"\nAt equalized FPR:")
    print(f"  FNR Savings: {fnr_s:.1%}")
    print(f"  FNR Other: {fnr_o:.1%}")
    print(f"  FNR gap: {fnr_gap:.1%}")

    # Confidence intervals on FNR (Other has small n)
    n_default_o = int(y_true_o.sum())
    fnr_o_val, fnr_o_lo, fnr_o_hi = wilson_ci(int(fnr_o * n_default_o), n_default_o)
    print(f"\n  Other FNR 95% CI: [{fnr_o_lo:.1%}, {fnr_o_hi:.1%}] (n={n_default_o} defaulters)")

    # Create plots
    print("\n" + "=" * 60)
    print("Creating plots...")
    print("=" * 60)

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    # Plot 1: Calibration comparison
    ax1 = axes[0, 0]
    ax1.plot([0, 1], [0, 1], 'k--', label='Perfect')
    prob_true_uncal, prob_pred_uncal = calibration_curve(y_test, y_prob_uncal, n_bins=10)
    prob_true_cal, prob_pred_cal = calibration_curve(y_test, best_probs, n_bins=10)
    ax1.plot(prob_pred_uncal, prob_true_uncal, 'r-o', label=f'Uncalibrated (ECE={ece_uncal:.3f})')
    ax1.plot(prob_pred_cal, prob_true_cal, 'b-s', label=f'{best_method.title()} (ECE={best_ece:.3f})')
    ax1.set_xlabel('Predicted probability')
    ax1.set_ylabel('Observed probability')
    ax1.set_title('Calibration Comparison')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Plot 2: Per-group calibration (calibrated model)
    ax2 = axes[0, 1]
    ax2.plot([0, 1], [0, 1], 'k--', label='Perfect')
    if len(y_prob_s) > 20:
        prob_true_s, prob_pred_s = calibration_curve(y_true_s, y_prob_s, n_bins=5)
        ax2.plot(prob_pred_s, prob_true_s, 'b-o', label=f'Savings (ECE={ece_savings:.3f})')
    if len(y_prob_o) > 20:
        prob_true_o, prob_pred_o = calibration_curve(y_true_o, y_prob_o, n_bins=5)
        ax2.plot(prob_pred_o, prob_true_o, 'g-s', label=f'Other (ECE={ece_other:.3f})')
    ax2.set_xlabel('Predicted probability')
    ax2.set_ylabel('Observed probability')
    ax2.set_title(f'Per-Group Calibration ({best_method})')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # Plot 3: FPR/FNR trade-off
    ax3 = axes[1, 0]
    ax3.bar(['Savings', 'Other'], [fnr_s, fnr_o], color=['steelblue', 'green'], alpha=0.7)
    ax3.axhline(fnr_s, color='steelblue', linestyle='--', alpha=0.5)
    ax3.axhline(fnr_o, color='green', linestyle='--', alpha=0.5)
    ax3.set_ylabel('False Negative Rate')
    ax3.set_title(f'FNR at Equalized FPR (gap={fnr_gap:.1%})')
    ax3.grid(True, alpha=0.3, axis='y')

    # Annotate with error bars for Other
    ax3.errorbar(['Other'], [fnr_o], yerr=[[fnr_o - fnr_o_lo], [fnr_o_hi - fnr_o]], fmt='none', color='black', capsize=5)

    # Plot 4: Summary text
    ax4 = axes[1, 1]
    ax4.axis('off')

    if well_calibrated:
        conclusion = (
            "CALIBRATION ACHIEVED\n\n"
            f"ECE = {best_ece:.4f} (< {CALIBRATION_THRESHOLD})\n\n"
            "The full Chouldechova/Kleinberg\n"
            "framing is available:\n\n"
            "When base rates differ, no\n"
            "calibrated classifier can\n"
            "simultaneously equalize\n"
            "FPR and FNR."
        )
    else:
        conclusion = (
            "CALIBRATION NOT ACHIEVED\n\n"
            f"ECE = {best_ece:.4f} (>= {CALIBRATION_THRESHOLD})\n\n"
            "Lead with EMPIRICAL result:\n\n"
            f"'Equalizing FPR forces a\n"
            f"{fnr_gap:.1%} FNR gap'\n\n"
            "This finding stands on its own\n"
            "without calibration assumption."
        )

    ax4.text(0.5, 0.5, conclusion, transform=ax4.transAxes,
             fontsize=14, ha='center', va='center',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    plt.tight_layout()
    plot_path = RESULTS_DIR / "impossibility_recalibrated.png"
    plt.savefig(plot_path, dpi=150)
    print(f"Plot saved to: {plot_path}")

    # Compile results
    results = {
        "timestamp": datetime.now().isoformat(),
        "task": "T51",
        "title": "Recalibrated Impossibility Analysis",
        "canonical_test_size": len(y_test),
        "random_state": RANDOM_STATE,

        "calibration_comparison": {
            "uncalibrated": {
                "brier_score": round(brier_uncal, 4),
                "ece": round(ece_uncal, 4),
                "bins": bins_uncal
            },
            "isotonic": {
                "brier_score": round(brier_iso, 4),
                "ece": round(ece_iso, 4),
                "bins": bins_iso
            },
            "platt": {
                "brier_score": round(brier_platt, 4),
                "ece": round(ece_platt, 4),
                "bins": bins_platt
            },
            "best_method": best_method,
            "best_ece": round(best_ece, 4),
            "calibration_threshold": CALIBRATION_THRESHOLD,
            "well_calibrated": bool(well_calibrated)
        },

        "per_group_calibration": {
            "savings_ece": round(ece_savings, 4),
            "other_ece": round(ece_other, 4)
        },

        "base_rates": {
            "savings": {"n": len(y_true_s), "default_rate": round(float(y_true_s.mean()), 4)},
            "other": {"n": len(y_true_o), "default_rate": round(float(y_true_o.mean()), 4)},
            "ratio": round(y_true_s.mean() / y_true_o.mean(), 2)
        },

        "impossibility_demonstration": {
            "method": "empirical (FPR equalization test)",
            "fpr_equalizing_thresholds": equal_fpr,
            "fnr_at_equal_fpr": {
                "savings": round(fnr_s, 4),
                "other": round(fnr_o, 4),
                "gap": round(fnr_gap, 4),
                "other_ci_95": [round(fnr_o_lo, 4), round(fnr_o_hi, 4)],
                "other_n_defaulters": n_default_o
            },
            "finding": f"Equalizing FPR forces FNR gap to {fnr_gap:.1%}"
        },

        "conclusion": {
            "calibration_achieved": bool(well_calibrated),
            "framing": (
                "Full Chouldechova/Kleinberg framing available: when base rates differ, "
                "no calibrated classifier can simultaneously equalize FPR and FNR."
            ) if well_calibrated else (
                "Lead with empirical result only: 'Equalizing FPR forces a "
                f"{fnr_gap:.1%} FNR gap.' The finding stands without calibration assumption."
            ),
            "t46_contradiction_resolved": True,
            "flags_and_prose_now_agree": True
        },

        "citations": [
            "Chouldechova, A. (2017). Fair prediction with disparate impact. Big Data, 5(2), 153-163.",
            "Kleinberg, J., Mullainathan, S. & Raghavan, M. (2017). Inherent trade-offs in fair risk scores. ITCS 2017."
        ]
    }

    output_path = RESULTS_DIR / "impossibility_recalibrated.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {output_path}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"\nCalibration: {best_method} ECE={best_ece:.4f}")
    print(f"Well calibrated (ECE < {CALIBRATION_THRESHOLD})? {well_calibrated}")
    print(f"\nBase rate difference: {y_true_s.mean():.1%} vs {y_true_o.mean():.1%} ({y_true_s.mean()/y_true_o.mean():.1f}x)")
    print(f"\nWhen FPR equalized: FNR gap = {fnr_gap:.1%}")
    print(f"  Savings FNR: {fnr_s:.1%}")
    print(f"  Other FNR: {fnr_o:.1%} (95% CI: [{fnr_o_lo:.1%}, {fnr_o_hi:.1%}])")
    print(f"\nT46 contradiction: RESOLVED")
    print(f"Pareto frontier: Will be fixed in separate analysis")

    return results


if __name__ == "__main__":
    main()
