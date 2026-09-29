"""
T16: Privacy-Utility Exchange Rate Curve

Quantifies the cost of banding to lenders: when a lender's optimal cutoff is
quantised to the nearest permitted band, what is the excess default rate and
approval rate change?

This is THE CONTRIBUTION: answering "what does borrower privacy cost a lender,
in basis points?" - a question the literature has not posed.

Output:
- results/privacy_utility.json
- results/privacy_utility_curve.png
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
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"

RANDOM_STATE = 42
TEST_SIZE = 0.2

# Band configurations to test
BAND_CONFIGS = {
    2: [400, 700],
    3: [400, 600, 800],
    4: [400, 550, 700, 850],
    5: [300, 450, 600, 750, 900],
    8: [300, 400, 500, 600, 700, 800, 900, 950],
    10: [300, 380, 460, 540, 620, 700, 780, 860, 940, 1000],
    20: list(range(300, 1001, 35))[:20],
}


def score_to_int(prob):
    """Convert P(default) to score 0-1000."""
    # score = round(1000 * (1 - P(default)))
    return int(round(1000 * (1 - prob)))


def quantise_to_band(score, bands):
    """Quantise a score to the nearest permitted band (downward)."""
    # Find largest band <= score
    valid_bands = [b for b in bands if b <= score]
    return max(valid_bands) if valid_bands else bands[0]


def compute_metrics_at_threshold(y_true, scores, threshold):
    """Compute approval rate and default rate at a given threshold."""
    approved = scores >= threshold
    approval_rate = approved.mean()
    if approved.sum() == 0:
        default_rate = 0
    else:
        default_rate = y_true[approved].mean()
    return approval_rate, default_rate


def safe_json(val):
    """Convert numpy types for JSON serialization."""
    if isinstance(val, (np.integer, np.int64)):
        return int(val)
    elif isinstance(val, (np.floating, np.float64)):
        if np.isnan(val):
            return None
        return float(val)
    elif isinstance(val, np.ndarray):
        return [safe_json(v) for v in val]
    elif isinstance(val, dict):
        return {k: safe_json(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [safe_json(v) for v in val]
    return val


def main():
    print("=== T16: Privacy-Utility Exchange Rate Curve ===\n")

    # Load data
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)

    features = feature_info["feature_sets"]["full"]["features"]
    print(f"Dataset: {len(df)} samples, {len(features)} features")

    X = df[features].values
    y = df["target"].values

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )

    # Train model (LR per T23/T24 findings)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=RANDOM_STATE
    )
    model.fit(X_train_scaled, y_train)

    # Get probabilities and convert to scores
    y_prob = model.predict_proba(X_test_scaled)[:, 1]
    scores = np.array([score_to_int(p) for p in y_prob])

    print(f"Score range: [{scores.min()}, {scores.max()}]")
    print(f"Score mean: {scores.mean():.1f}")
    print(f"Test default rate: {y_test.mean():.3f}")

    # Find optimal threshold (unrestricted)
    # Minimize default rate subject to approval rate >= 20%
    MIN_APPROVAL_RATE = 0.20

    best_threshold = None
    best_default_rate = 1.0

    for threshold in range(300, 900):
        approval_rate, default_rate = compute_metrics_at_threshold(y_test, scores, threshold)
        if approval_rate >= MIN_APPROVAL_RATE and default_rate < best_default_rate:
            best_default_rate = default_rate
            best_threshold = threshold

    print(f"\nOptimal unrestricted threshold: {best_threshold}")
    opt_approval, opt_default = compute_metrics_at_threshold(y_test, scores, best_threshold)
    print(f"  Approval rate: {100*opt_approval:.1f}%")
    print(f"  Default rate: {100*opt_default:.1f}%")

    # Results structure
    results = {
        "timestamp": datetime.now().isoformat(),
        "model": "LogisticRegression",
        "test_size": len(y_test),
        "score_range": [int(scores.min()), int(scores.max())],
        "score_mean": float(scores.mean()),
        "baseline_default_rate": float(y_test.mean()),
        "optimal_unrestricted": {
            "threshold": best_threshold,
            "approval_rate": float(opt_approval),
            "default_rate": float(opt_default)
        },
        "band_analysis": {},
        "privacy_utility_curve": []
    }

    print("\n" + "=" * 70)
    print("BANDING ANALYSIS")
    print("=" * 70)

    print("\n| Bands | Bits Leaked | Quant. Threshold | Approval | Default | Excess DR (bps) |")
    print("|-------|-------------|------------------|----------|---------|-----------------|")

    for n_bands, bands in sorted(BAND_CONFIGS.items()):
        bits_leaked = np.log2(n_bands)

        # Quantise optimal threshold to nearest band
        quant_threshold = quantise_to_band(best_threshold, bands)
        quant_approval, quant_default = compute_metrics_at_threshold(y_test, scores, quant_threshold)

        # Excess default rate in basis points
        excess_dr_bps = (quant_default - opt_default) * 10000

        results["band_analysis"][n_bands] = {
            "bands": bands,
            "bits_leaked": float(bits_leaked),
            "quantised_threshold": quant_threshold,
            "approval_rate": float(quant_approval),
            "default_rate": float(quant_default),
            "excess_default_rate_bps": float(excess_dr_bps),
            "approval_change_pct": float((quant_approval - opt_approval) * 100)
        }

        results["privacy_utility_curve"].append({
            "bits_leaked": float(bits_leaked),
            "excess_default_rate_bps": float(excess_dr_bps),
            "approval_rate": float(quant_approval)
        })

        print(f"| {n_bands:5} | {bits_leaked:11.2f} | {quant_threshold:16} | "
              f"{100*quant_approval:7.1f}% | {100*quant_default:6.1f}% | {excess_dr_bps:15.1f} |")

    # Also compute unrestricted (for the curve endpoint)
    results["privacy_utility_curve"].append({
        "bits_leaked": float(np.log2(1000)),  # ~10 bits
        "excess_default_rate_bps": 0.0,
        "approval_rate": float(opt_approval)
    })

    # Create visualization
    print("\n=== Generating privacy_utility_curve.png ===")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Sort curve data
    curve_data = sorted(results["privacy_utility_curve"], key=lambda x: x["bits_leaked"])
    bits = [d["bits_leaked"] for d in curve_data]
    excess_dr = [d["excess_default_rate_bps"] for d in curve_data]
    approval = [d["approval_rate"] * 100 for d in curve_data]

    # Plot 1: Excess default rate vs bits leaked
    ax1.plot(bits, excess_dr, 'b-o', linewidth=2, markersize=8)
    ax1.set_xlabel("Information Leaked to Lender (bits)", fontsize=12)
    ax1.set_ylabel("Excess Default Rate (basis points)", fontsize=12)
    ax1.set_title("Privacy Cost to Borrower vs. Lending Cost", fontsize=14)
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=0, color='gray', linestyle='--', alpha=0.5)

    # Add annotations for key points
    for i, (b, e, a) in enumerate(zip(bits, excess_dr, approval)):
        if b < 4:  # Annotate low-band configs
            ax1.annotate(f'{int(2**b)} bands', (b, e), textcoords="offset points",
                        xytext=(5, 5), fontsize=9)

    # Plot 2: Approval rate vs bits leaked
    ax2.plot(bits, approval, 'g-s', linewidth=2, markersize=8)
    ax2.set_xlabel("Information Leaked to Lender (bits)", fontsize=12)
    ax2.set_ylabel("Approval Rate (%)", fontsize=12)
    ax2.set_title("Approval Rate by Privacy Level", fontsize=14)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "privacy_utility_curve.png", dpi=150, bbox_inches='tight')
    print(f"Saved: {RESULTS_DIR / 'privacy_utility_curve.png'}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    # Find the 4-band case (default)
    four_band = results["band_analysis"][4]
    print(f"\nWith 4 bands (default configuration):")
    print(f"  - Bits leaked: {four_band['bits_leaked']:.2f} (vs ~10 unbanded)")
    print(f"  - Privacy improvement: {10/four_band['bits_leaked']:.1f}x")
    print(f"  - Excess default rate: {four_band['excess_default_rate_bps']:.1f} bps")
    print(f"  - Approval rate change: {four_band['approval_change_pct']:+.1f}%")

    # Cost per bit of privacy
    if four_band['excess_default_rate_bps'] > 0:
        privacy_cost = (10 - four_band['bits_leaked']) / four_band['excess_default_rate_bps']
        print(f"  - Privacy bought per bps: {privacy_cost:.2f} bits")

    # Save results
    output_path = RESULTS_DIR / "privacy_utility.json"
    with open(output_path, "w") as f:
        json.dump(safe_json(results), f, indent=2)
    print(f"\nResults saved to {output_path}")

    # Update SUMMARY.md
    summary_path = RESULTS_DIR / "SUMMARY.md"
    summary_entry = f"""
### privacy_utility — {datetime.now().strftime('%Y-%m-%d')}
**What was run:** T16 Privacy-Utility Exchange Rate Curve
**Model:** LogisticRegression
**Optimal unrestricted threshold:** {best_threshold} (approval {100*opt_approval:.1f}%, default {100*opt_default:.1f}%)
**Key numbers:**
| Bands | Bits Leaked | Excess Default Rate (bps) | Approval Rate |
|-------|-------------|---------------------------|---------------|
"""
    for n_bands in sorted(BAND_CONFIGS.keys()):
        ba = results["band_analysis"][n_bands]
        summary_entry += f"| {n_bands} | {ba['bits_leaked']:.2f} | {ba['excess_default_rate_bps']:.1f} | {100*ba['approval_rate']:.1f}% |\n"

    summary_entry += f"""
**The Contribution:** With 4 bands, borrowers leak 2 bits (vs ~10 unbanded) at a cost of {four_band['excess_default_rate_bps']:.1f} bps excess default rate.
**Caveats:** Assumes lender's optimal threshold; real-world lender objectives vary.
"""

    with open(summary_path, "a") as f:
        f.write(summary_entry)

    print(f"Summary appended to {summary_path}")


if __name__ == "__main__":
    main()
