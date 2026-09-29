"""
T35: Non-monotonic curve analysis + nested (dyadic) band comparison

Problem: Equidistant bands show non-monotonic profit loss because band sets are not nested.
Adding bands can move ALL boundaries away from the optimal threshold.

Solution: Add dyadic refinement (each B doubles the previous set) to guarantee monotonicity.
Compare nested vs non-nested to isolate effect of band count from band position.
"""
import numpy as np
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt

RESULTS_DIR = Path(__file__).parent.parent / "results"
DATA_DIR = Path(__file__).parent.parent / "data"

RANDOM_STATE = 42
PROFIT_MODEL = {"revenue_per_performing": 1.0, "loss_given_default": 3.0}


def load_data_and_model():
    """Load data and train model (same as privacy_utility_v2.py)."""
    df = pd.read_csv(DATA_DIR / "features_processed.csv")

    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)

    features = feature_info["feature_sets"]["full"]["features"]
    X = df[features].values
    y = df["target"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(max_iter=1000, random_state=RANDOM_STATE, class_weight="balanced")
    model.fit(X_train_scaled, y_train)

    proba = model.predict_proba(X_test_scaled)[:, 1]
    scores = np.round(1000 * (1 - proba)).astype(int)
    scores = np.clip(scores, 0, 1000)

    return scores, y_test


def compute_profit(y_true, approved_mask, profit_model):
    """Compute profit for a given approval decision."""
    n_approved = approved_mask.sum()
    if n_approved == 0:
        return 0

    n_defaults = (y_true[approved_mask] == 1).sum()
    n_performing = n_approved - n_defaults

    profit = (n_performing * profit_model["revenue_per_performing"] -
              n_defaults * profit_model["loss_given_default"])
    return profit


def find_unrestricted_optimum(scores, y_test, profit_model):
    """Find the optimal threshold without band constraints."""
    best_profit = -np.inf
    best_threshold = 0
    best_stats = {}

    for threshold in range(int(scores.min()), int(scores.max()) + 1):
        approved = scores >= threshold
        profit = compute_profit(y_test, approved, profit_model)

        if profit > best_profit:
            best_profit = profit
            best_threshold = threshold
            n_approved = approved.sum()
            n_defaults = (y_test[approved] == 1).sum() if n_approved > 0 else 0
            best_stats = {
                "threshold": int(best_threshold),
                "n_approved": int(n_approved),
                "approval_rate": float(n_approved / len(scores)),
                "default_rate": float(n_defaults / n_approved) if n_approved > 0 else 0,
                "profit": float(best_profit)
            }

    return best_stats


def analyze_bands(scores, y_test, bands, profit_model, unrestricted_profit):
    """Analyze a band configuration."""
    best_profit = -np.inf
    best_band = None
    best_stats = {}

    for band in bands:
        approved = scores >= band
        profit = compute_profit(y_test, approved, profit_model)

        if profit > best_profit:
            best_profit = profit
            best_band = band
            n_approved = approved.sum()
            n_defaults = (y_test[approved] == 1).sum() if n_approved > 0 else 0
            best_stats = {
                "best_band": int(best_band),
                "threshold": int(best_band),
                "n_approved": int(n_approved),
                "approval_rate": float(n_approved / len(scores)),
                "default_rate": float(n_defaults / n_approved) if n_approved > 0 else 0,
                "profit": float(best_profit)
            }

    profit_loss = unrestricted_profit - best_profit
    profit_loss_pct = (profit_loss / unrestricted_profit * 100) if unrestricted_profit > 0 else 0

    return {
        "bands": [int(b) for b in bands],
        "n_bands": len(bands),
        "bits": float(np.log2(len(bands))),
        "constrained_optimum": best_stats,
        "profit_loss": float(profit_loss),
        "profit_loss_pct": float(profit_loss_pct)
    }


def generate_equidistant_bands(score_min, score_max, n_bands):
    """Generate equidistant bands (non-nested)."""
    return np.linspace(score_min, score_max, n_bands).astype(int)


def generate_dyadic_bands(score_min, score_max, level):
    """
    Generate dyadic (nested) bands.
    Level 0: [min, max] (2 bands)
    Level 1: [min, mid, max] (3 bands)
    Level 2: [min, q1, mid, q3, max] (5 bands)
    Level k: 2^k + 1 bands

    Each level includes all bands from previous levels (nested).
    """
    n_intervals = 2 ** level
    bands = np.linspace(score_min, score_max, n_intervals + 1).astype(int)
    return np.unique(bands)  # Remove duplicates from rounding


def main():
    print("=== T35: Nested Bands Analysis ===\n")

    # Load data
    scores, y_test = load_data_and_model()
    score_min, score_max = int(scores.min()), int(scores.max())

    print(f"Score range: [{score_min}, {score_max}]")
    print(f"Test size: {len(scores)}")
    print(f"Default rate: {y_test.mean():.2%}")
    print()

    # Find unrestricted optimum
    unrestricted = find_unrestricted_optimum(scores, y_test, PROFIT_MODEL)
    print(f"Unrestricted optimum: threshold={unrestricted['threshold']}, profit={unrestricted['profit']}")
    print()

    results = {
        "timestamp": datetime.now().isoformat(),
        "score_range": [score_min, score_max],
        "test_size": len(scores),
        "profit_model": PROFIT_MODEL,
        "unrestricted_optimum": unrestricted,
        "equidistant_analysis": {},
        "dyadic_analysis": {},
        "comparison": {}
    }

    # Analyze equidistant bands (non-nested)
    print("=== Equidistant Bands (Non-Nested) ===")
    equidist_configs = [2, 3, 4, 5, 6, 8, 10, 15, 20]

    for n in equidist_configs:
        bands = generate_equidistant_bands(score_min, score_max, n)
        analysis = analyze_bands(scores, y_test, bands, PROFIT_MODEL, unrestricted["profit"])
        results["equidistant_analysis"][str(n)] = analysis
        print(f"  B={n:2d}: bands={len(bands)}, bits={analysis['bits']:.2f}, "
              f"profit_loss={analysis['profit_loss']:6.1f} ({analysis['profit_loss_pct']:.1f}%)")

    print()

    # Analyze dyadic bands (nested)
    print("=== Dyadic Bands (Nested) ===")
    print("Each level includes all bands from previous levels.")

    dyadic_levels = [0, 1, 2, 3, 4, 5]  # 2, 3, 5, 9, 17, 33 bands

    for level in dyadic_levels:
        bands = generate_dyadic_bands(score_min, score_max, level)
        analysis = analyze_bands(scores, y_test, bands, PROFIT_MODEL, unrestricted["profit"])
        results["dyadic_analysis"][str(level)] = analysis
        print(f"  Level {level}: bands={len(bands):2d}, bits={analysis['bits']:.2f}, "
              f"profit_loss={analysis['profit_loss']:6.1f} ({analysis['profit_loss_pct']:.1f}%)")

    print()

    # Check monotonicity
    print("=== Monotonicity Check ===")

    # Equidistant
    equi_losses = [results["equidistant_analysis"][str(n)]["profit_loss"] for n in equidist_configs]
    equi_bits = [results["equidistant_analysis"][str(n)]["bits"] for n in equidist_configs]
    equi_monotonic = all(equi_losses[i] >= equi_losses[i+1] for i in range(len(equi_losses)-1))
    print(f"Equidistant monotonic (cost decreases with B): {equi_monotonic}")

    # Find non-monotonic pairs
    if not equi_monotonic:
        print("  Non-monotonic pairs:")
        for i in range(len(equidist_configs)-1):
            if equi_losses[i] < equi_losses[i+1]:
                print(f"    B={equidist_configs[i]} (loss={equi_losses[i]:.1f}) -> "
                      f"B={equidist_configs[i+1]} (loss={equi_losses[i+1]:.1f}) INCREASES")

    # Dyadic
    dyadic_losses = [results["dyadic_analysis"][str(l)]["profit_loss"] for l in dyadic_levels]
    dyadic_bits = [results["dyadic_analysis"][str(l)]["bits"] for l in dyadic_levels]
    dyadic_monotonic = all(dyadic_losses[i] >= dyadic_losses[i+1] for i in range(len(dyadic_losses)-1))
    print(f"Dyadic monotonic (cost decreases with level): {dyadic_monotonic}")

    results["comparison"]["equidistant_monotonic"] = equi_monotonic
    results["comparison"]["dyadic_monotonic"] = dyadic_monotonic

    print()

    # Build envelope (best achievable at each privacy level)
    print("=== Privacy-Utility Envelope ===")
    print("Best achievable profit loss at each bits level across all placements:")

    all_points = []

    # Collect all configurations
    for n, analysis in results["equidistant_analysis"].items():
        all_points.append({
            "type": "equidistant",
            "config": n,
            "bits": analysis["bits"],
            "profit_loss": analysis["profit_loss"],
            "profit_loss_pct": analysis["profit_loss_pct"]
        })

    for level, analysis in results["dyadic_analysis"].items():
        all_points.append({
            "type": "dyadic",
            "config": f"level_{level}",
            "bits": analysis["bits"],
            "profit_loss": analysis["profit_loss"],
            "profit_loss_pct": analysis["profit_loss_pct"]
        })

    # Sort by bits
    all_points.sort(key=lambda x: x["bits"])

    # Build envelope (minimum profit loss at each bits level)
    envelope = []
    seen_bits = set()
    for point in all_points:
        bits_rounded = round(point["bits"], 2)
        if bits_rounded not in seen_bits:
            # Find minimum at this bits level
            same_bits = [p for p in all_points if round(p["bits"], 2) == bits_rounded]
            best = min(same_bits, key=lambda x: x["profit_loss"])
            envelope.append(best)
            seen_bits.add(bits_rounded)

    envelope.sort(key=lambda x: x["bits"])

    print(f"| Bits | Best Loss | Winner |")
    print(f"|------|-----------|--------|")
    for e in envelope:
        print(f"| {e['bits']:.2f} | {e['profit_loss']:7.1f} | {e['type']} ({e['config']}) |")

    results["comparison"]["envelope"] = envelope

    # Create visualization
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Plot 1: Profit loss vs B (showing non-monotonicity)
    ax1 = axes[0]
    ax1.plot(equidist_configs, equi_losses, 'b-o', label='Equidistant', linewidth=2)
    dyadic_n_bands = [results["dyadic_analysis"][str(l)]["n_bands"] for l in dyadic_levels]
    ax1.plot(dyadic_n_bands, dyadic_losses, 'g-s', label='Dyadic (nested)', linewidth=2)
    ax1.set_xlabel('Number of Bands')
    ax1.set_ylabel('Profit Loss')
    ax1.set_title('T35: Non-Monotonicity in Equidistant Bands')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=0, color='k', linestyle='--', alpha=0.3)

    # Highlight non-monotonic regions
    for i in range(len(equidist_configs)-1):
        if equi_losses[i] < equi_losses[i+1]:
            ax1.annotate('', xy=(equidist_configs[i+1], equi_losses[i+1]),
                        xytext=(equidist_configs[i], equi_losses[i]),
                        arrowprops=dict(arrowstyle='->', color='red', lw=2))

    # Plot 2: Privacy-utility tradeoff (bits vs profit loss)
    ax2 = axes[1]
    ax2.scatter(equi_bits, equi_losses, c='blue', s=100, label='Equidistant', alpha=0.7)
    ax2.scatter(dyadic_bits, dyadic_losses, c='green', s=100, marker='s', label='Dyadic', alpha=0.7)

    # Draw envelope
    env_bits = [e["bits"] for e in envelope]
    env_losses = [e["profit_loss"] for e in envelope]
    ax2.plot(env_bits, env_losses, 'r--', linewidth=2, label='Envelope (best achievable)')

    ax2.set_xlabel('Information Leaked (bits)')
    ax2.set_ylabel('Profit Loss')
    ax2.set_title('Privacy-Utility Envelope')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=0, color='k', linestyle='--', alpha=0.3)

    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "nested_bands_analysis.png", dpi=150, bbox_inches='tight')
    print(f"\nPlot saved to {RESULTS_DIR / 'nested_bands_analysis.png'}")

    # Key finding
    print("\n" + "=" * 80)
    print("KEY FINDING")
    print("=" * 80)

    if not equi_monotonic and dyadic_monotonic:
        print("\nEquidistant bands are NON-MONOTONIC: adding bands can INCREASE cost")
        print("because band positions shift arbitrarily with B.")
        print("\nDyadic bands are MONOTONIC: each level refines the previous,")
        print("so adding bands never moves existing boundaries.")
        print("\nThis explains the puzzle in HANDOVER.md: B=4 costs more than B=3")
        print("because B=3 happens to have a band near the optimal threshold (484)")
        print("while B=4's nearest bands (328, 639) are both far from it.")

        results["key_finding"] = {
            "equidistant_non_monotonic": True,
            "dyadic_monotonic": True,
            "explanation": "Equidistant band boundaries depend on B, so adding bands can shift "
                          "all boundaries away from the optimal threshold. Dyadic (nested) bands "
                          "guarantee that each refinement only adds new boundaries, never removes "
                          "existing ones, ensuring monotonic improvement.",
            "chapter_5_implication": "Report non-monotonicity as a finding: under equidistant "
                                    "placement, cost depends on whether a band happens to fall "
                                    "near the lender's optimum, which is essentially arbitrary. "
                                    "This is a strong argument for adaptive placement."
        }

    # Save results
    output_path = RESULTS_DIR / "nested_bands_analysis.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_path}")

    # Append to SUMMARY.md
    summary_entry = f"""
### nested_bands_analysis - {datetime.now().strftime('%Y-%m-%d')}
**What was run:** T35 - Analyze non-monotonicity in equidistant bands + compare to nested dyadic bands.
**Why:** Equidistant profit curve is non-monotonic because band sets are not nested.
**Key numbers:**

| Band Type | Monotonic? | Explanation |
|-----------|------------|-------------|
| Equidistant | {'No' if not equi_monotonic else 'Yes'} | Band positions shift with B |
| Dyadic (nested) | {'Yes' if dyadic_monotonic else 'No'} | Each level refines previous |

**Non-monotonic example (equidistant):**
- B=3: profit_loss={results['equidistant_analysis']['3']['profit_loss']:.1f} (band at 484 near optimum 470)
- B=4: profit_loss={results['equidistant_analysis']['4']['profit_loss']:.1f} (bands at 328, 639 far from optimum)

**Chapter 5 implication:** Non-monotonicity is a finding, not a bug. Cost depends on whether a band happens to fall near the lender's optimum. This argues for adaptive placement.
"""

    with open(RESULTS_DIR / "SUMMARY.md", "a", encoding="utf-8") as f:
        f.write(summary_entry)
    print(f"Summary appended to SUMMARY.md")


if __name__ == "__main__":
    main()
