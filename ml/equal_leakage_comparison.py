"""
T36: Compare placements at equal measured leakage

Problem: Comparing at equal B is not apples-to-apples because equidistant and quantile
placements sit at different points on the privacy axis. Equidistant appears more private
partly because it wastes bands on empty regions (e.g., top band with n=1).

Solution: Plot both placements with x = measured bits leaked, y = profit loss.
Find which placement dominates at each privacy level.
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
MIN_BAND_POP = 5  # Minimum population for "effective" band


def load_data():
    """Load privacy utility and entropy results."""
    with open(RESULTS_DIR / "privacy_utility_v2.json") as f:
        privacy_utility = json.load(f)

    with open(RESULTS_DIR / "adversary_entropy.json") as f:
        entropy = json.load(f)

    return privacy_utility, entropy


def count_effective_bands(band_details, min_pop=MIN_BAND_POP):
    """Count bands with meaningful population."""
    return sum(1 for b in band_details if b["count"] >= min_pop)


def main():
    print("=== T36: Equal Leakage Comparison ===\n")

    privacy_utility, entropy = load_data()

    results = {
        "timestamp": datetime.now().isoformat(),
        "min_band_population": MIN_BAND_POP,
        "profit_model": PROFIT_MODEL,
        "equidistant_points": [],
        "quantile_points": [],
        "degenerate_band_analysis": {},
        "comparison": {}
    }

    # Analyze degenerate bands (bands with very few borrowers)
    print("=== Degenerate Band Analysis ===")
    print("Bands with < 5 borrowers are 'degenerate' - squandered resolution\n")

    for B_str in entropy["equidistant_analysis"]:
        B = int(B_str)
        equi_data = entropy["equidistant_analysis"][B_str]
        quant_data = entropy["quantile_analysis"][B_str]

        equi_effective = count_effective_bands(equi_data["band_details"])
        quant_effective = count_effective_bands(quant_data["band_details"])

        equi_degenerate = [b for b in equi_data["band_details"] if b["count"] < MIN_BAND_POP]
        quant_degenerate = [b for b in quant_data["band_details"] if b["count"] < MIN_BAND_POP]

        results["degenerate_band_analysis"][B_str] = {
            "equidistant": {
                "stated_bands": B,
                "effective_bands": equi_effective,
                "degenerate_bands": len(equi_degenerate),
                "degenerate_details": [{"band": b["band"], "count": b["count"]} for b in equi_degenerate]
            },
            "quantile": {
                "stated_bands": B,
                "effective_bands": quant_effective,
                "degenerate_bands": len(quant_degenerate),
                "degenerate_details": [{"band": b["band"], "count": b["count"]} for b in quant_degenerate]
            }
        }

        print(f"B={B:2d}: Equidist effective={equi_effective}/{B} (degenerate: {len(equi_degenerate)}), "
              f"Quantile effective={quant_effective}/{B} (degenerate: {len(quant_degenerate)})")

    print()

    # Build privacy-utility points for both placements
    print("=== Privacy-Utility Points ===")
    print("x = measured information leakage (bits)")
    print("y = profit loss\n")

    for B_str in privacy_utility["equidistant_bands"]:
        B = int(B_str)

        # Equidistant
        equi_profit = privacy_utility["equidistant_bands"][B_str]
        equi_entropy = entropy["equidistant_analysis"][B_str]

        equi_point = {
            "B": B,
            "stated_bits": equi_profit["stated_bits"],
            "measured_leakage": equi_entropy["information_leakage_bits"],
            "profit_loss": equi_profit["profit_loss"],
            "profit_loss_pct": equi_profit["profit_loss_pct"],
            "effective_bands": count_effective_bands(equi_entropy["band_details"])
        }
        results["equidistant_points"].append(equi_point)

        # Quantile
        quant_profit = privacy_utility["quantile_bands"][B_str]
        quant_entropy = entropy["quantile_analysis"][B_str]

        quant_point = {
            "B": B,
            "stated_bits": quant_profit["stated_bits"],
            "measured_leakage": quant_entropy["information_leakage_bits"],
            "profit_loss": quant_profit["profit_loss"],
            "profit_loss_pct": quant_profit["profit_loss_pct"],
            "effective_bands": count_effective_bands(quant_entropy["band_details"])
        }
        results["quantile_points"].append(quant_point)

    # Print comparison table
    print(f"| B  | Equidist Leak | Equidist Loss | Quantile Leak | Quantile Loss | Winner at equal B |")
    print(f"|----|---------------|---------------|---------------|---------------|-------------------|")

    for equi, quant in zip(results["equidistant_points"], results["quantile_points"]):
        equi_leak = equi["measured_leakage"]
        quant_leak = quant["measured_leakage"]
        equi_loss = equi["profit_loss"]
        quant_loss = quant["profit_loss"]

        # At equal B, which is better?
        if equi_loss < quant_loss:
            winner = "Equidist"
        elif quant_loss < equi_loss:
            winner = "Quantile"
        else:
            winner = "Tie"

        print(f"| {equi['B']:2d} | {equi_leak:13.2f} | {equi_loss:13.1f} | {quant_leak:13.2f} | {quant_loss:13.1f} | {winner:17s} |")

    print()

    # Find Pareto frontier (non-dominated points)
    print("=== Pareto Analysis ===")
    print("A point is Pareto-optimal if no other point has both lower leakage AND lower loss\n")

    all_points = []
    for p in results["equidistant_points"]:
        all_points.append({"type": "equidistant", **p})
    for p in results["quantile_points"]:
        all_points.append({"type": "quantile", **p})

    # Find Pareto frontier
    pareto_frontier = []
    for point in all_points:
        dominated = False
        for other in all_points:
            if (other["measured_leakage"] <= point["measured_leakage"] and
                other["profit_loss"] < point["profit_loss"]) or \
               (other["measured_leakage"] < point["measured_leakage"] and
                other["profit_loss"] <= point["profit_loss"]):
                dominated = True
                break
        if not dominated:
            pareto_frontier.append(point)

    # Sort by leakage
    pareto_frontier.sort(key=lambda x: x["measured_leakage"])

    print("Pareto-optimal points (neither dominates the other):")
    print(f"| Type | B | Leakage | Loss |")
    print(f"|------|---|---------|------|")
    for p in pareto_frontier:
        print(f"| {p['type']:10s} | {p['B']:2d} | {p['measured_leakage']:7.2f} | {p['profit_loss']:4.0f} |")

    results["comparison"]["pareto_frontier"] = pareto_frontier

    # Count which placement dominates
    equi_pareto = sum(1 for p in pareto_frontier if p["type"] == "equidistant")
    quant_pareto = sum(1 for p in pareto_frontier if p["type"] == "quantile")

    print(f"\nPareto frontier composition: {equi_pareto} equidistant, {quant_pareto} quantile")

    # Find crossover (if any)
    print("\n=== Crossover Analysis ===")

    # For each leakage level, find which placement is better
    leakage_levels = sorted(set([p["measured_leakage"] for p in all_points]))

    # Interpolate to find crossover
    equi_sorted = sorted(results["equidistant_points"], key=lambda x: x["measured_leakage"])
    quant_sorted = sorted(results["quantile_points"], key=lambda x: x["measured_leakage"])

    # Check at common leakage levels
    crossover_found = False
    last_winner = None

    for leak in np.arange(0.5, 4.5, 0.25):
        # Find nearest equidistant and quantile points
        equi_nearby = min(equi_sorted, key=lambda x: abs(x["measured_leakage"] - leak))
        quant_nearby = min(quant_sorted, key=lambda x: abs(x["measured_leakage"] - leak))

        # Only compare if both are reasonably close
        if abs(equi_nearby["measured_leakage"] - leak) < 0.5 and \
           abs(quant_nearby["measured_leakage"] - leak) < 0.5:
            if equi_nearby["profit_loss"] < quant_nearby["profit_loss"]:
                winner = "equidistant"
            elif quant_nearby["profit_loss"] < equi_nearby["profit_loss"]:
                winner = "quantile"
            else:
                winner = "tie"

            if last_winner is not None and winner != last_winner and winner != "tie" and last_winner != "tie":
                crossover_found = True
                print(f"Crossover detected near leakage={leak:.2f} bits: {last_winner} -> {winner}")

            last_winner = winner

    if not crossover_found:
        # Check overall dominance
        equi_wins = sum(1 for e, q in zip(equi_sorted, quant_sorted)
                       if e["profit_loss"] < q["profit_loss"])
        quant_wins = sum(1 for e, q in zip(equi_sorted, quant_sorted)
                        if q["profit_loss"] < e["profit_loss"])

        if quant_wins > equi_wins:
            print("No crossover found - Quantile generally dominates on utility")
            results["comparison"]["crossover"] = None
            results["comparison"]["dominant_placement"] = "quantile"
        elif equi_wins > quant_wins:
            print("No crossover found - Equidistant generally dominates on utility")
            results["comparison"]["crossover"] = None
            results["comparison"]["dominant_placement"] = "equidistant"
        else:
            print("No clear dominance - performance is mixed")
            results["comparison"]["crossover"] = None
            results["comparison"]["dominant_placement"] = "mixed"

    print()

    # Key finding
    print("=" * 80)
    print("KEY FINDING")
    print("=" * 80)

    # At equal measured leakage, which is better?
    # Find pairs with similar leakage
    similar_leak_comparison = []
    for equi in equi_sorted:
        for quant in quant_sorted:
            leak_diff = abs(equi["measured_leakage"] - quant["measured_leakage"])
            if leak_diff < 0.3:  # Similar leakage
                similar_leak_comparison.append({
                    "equi_B": equi["B"],
                    "quant_B": quant["B"],
                    "avg_leakage": (equi["measured_leakage"] + quant["measured_leakage"]) / 2,
                    "equi_loss": equi["profit_loss"],
                    "quant_loss": quant["profit_loss"],
                    "winner": "equidistant" if equi["profit_loss"] < quant["profit_loss"] else "quantile"
                })

    if similar_leak_comparison:
        equi_wins_at_equal_leak = sum(1 for c in similar_leak_comparison if c["winner"] == "equidistant")
        quant_wins_at_equal_leak = sum(1 for c in similar_leak_comparison if c["winner"] == "quantile")

        print(f"\nAt similar measured leakage levels:")
        print(f"  Equidistant wins: {equi_wins_at_equal_leak} times")
        print(f"  Quantile wins: {quant_wins_at_equal_leak} times")

        if quant_wins_at_equal_leak > equi_wins_at_equal_leak:
            print("\n=> QUANTILE IS GENERALLY BETTER at equal privacy levels")
            print("   The earlier finding (quantile leaks 37% more) was at equal B,")
            print("   but quantile's extra leakage buys disproportionately more utility.")
            results["comparison"]["conclusion"] = "quantile_better_at_equal_leakage"
        else:
            print("\n=> EQUIDISTANT IS GENERALLY BETTER at equal privacy levels")
            results["comparison"]["conclusion"] = "equidistant_better_at_equal_leakage"

    results["comparison"]["similar_leakage_comparisons"] = similar_leak_comparison

    # Create visualization
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Plot 1: Raw comparison (measured leakage vs profit loss)
    ax1 = axes[0]
    equi_leak = [p["measured_leakage"] for p in results["equidistant_points"]]
    equi_loss = [p["profit_loss"] for p in results["equidistant_points"]]
    quant_leak = [p["measured_leakage"] for p in results["quantile_points"]]
    quant_loss = [p["profit_loss"] for p in results["quantile_points"]]

    ax1.scatter(equi_leak, equi_loss, c='blue', s=100, label='Equidistant', alpha=0.7)
    ax1.scatter(quant_leak, quant_loss, c='green', s=100, marker='s', label='Quantile', alpha=0.7)

    # Add B labels
    for p in results["equidistant_points"]:
        ax1.annotate(f'B={p["B"]}', (p["measured_leakage"], p["profit_loss"]),
                    textcoords="offset points", xytext=(5, 5), fontsize=8, color='blue')
    for p in results["quantile_points"]:
        ax1.annotate(f'B={p["B"]}', (p["measured_leakage"], p["profit_loss"]),
                    textcoords="offset points", xytext=(5, -10), fontsize=8, color='green')

    ax1.set_xlabel('Measured Information Leakage (bits)')
    ax1.set_ylabel('Profit Loss')
    ax1.set_title('T36: Privacy-Utility at Measured Leakage')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=0, color='k', linestyle='--', alpha=0.3)

    # Plot 2: Stated bits vs measured leakage (showing degenerate bands)
    ax2 = axes[1]
    equi_stated = [p["stated_bits"] for p in results["equidistant_points"]]
    quant_stated = [p["stated_bits"] for p in results["quantile_points"]]

    ax2.scatter(equi_stated, equi_leak, c='blue', s=100, label='Equidistant', alpha=0.7)
    ax2.scatter(quant_stated, quant_leak, c='green', s=100, marker='s', label='Quantile', alpha=0.7)

    # Add diagonal (perfect = stated equals measured)
    max_bits = max(max(equi_stated), max(quant_stated))
    ax2.plot([0, max_bits], [0, max_bits], 'r--', label='log2(B) bound', alpha=0.5)

    ax2.set_xlabel('Stated Bits (log2 B)')
    ax2.set_ylabel('Measured Information Leakage (bits)')
    ax2.set_title('Stated vs Measured Privacy')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "equal_leakage_comparison.png", dpi=150, bbox_inches='tight')
    print(f"\nPlot saved to {RESULTS_DIR / 'equal_leakage_comparison.png'}")

    # Save results
    output_path = RESULTS_DIR / "equal_leakage_comparison.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {output_path}")

    # Append to SUMMARY.md
    conclusion = results["comparison"].get("conclusion", "mixed")
    summary_entry = f"""
### equal_leakage_comparison - {datetime.now().strftime('%Y-%m-%d')}
**What was run:** T36 - Compare equidistant vs quantile at equal measured leakage.
**Why:** Earlier comparison at equal B was misleading because placements leak different amounts.
**Key numbers:**

| Placement | Pareto Points | Degenerate Bands (B=4) |
|-----------|---------------|------------------------|
| Equidistant | {equi_pareto} | {results['degenerate_band_analysis']['4']['equidistant']['degenerate_bands']} |
| Quantile | {quant_pareto} | {results['degenerate_band_analysis']['4']['quantile']['degenerate_bands']} |

**At similar leakage levels:** Equidist wins {equi_wins_at_equal_leak}x, Quantile wins {quant_wins_at_equal_leak}x
**Conclusion:** {conclusion}
"""

    with open(RESULTS_DIR / "SUMMARY.md", "a", encoding="utf-8") as f:
        f.write(summary_entry)
    print(f"Summary appended to SUMMARY.md")


if __name__ == "__main__":
    main()
