"""
T29: Adversary's True Posterior Entropy

The log2(B) privacy bound assumes scores are uniform within each band.
In reality, scores cluster non-uniformly, so the adversary's true
posterior may have lower entropy than log2(B) claims.

This script computes the actual information leakage using the
empirical score distribution.
"""
import numpy as np
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from collections import Counter

RESULTS_DIR = Path(__file__).parent.parent / "results"
DATA_DIR = Path(__file__).parent.parent / "data"


def load_scores():
    """Load test scores matching privacy_utility_v2.py exactly."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler

    # Load data - match privacy_utility_v2.py
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)

    features = feature_info["feature_sets"]["full"]["features"]
    X = df[features].values
    y = df["target"].values

    # Train/test split - same params as privacy_utility_v2.py
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Scale features - match privacy_utility_v2.py
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train LR - match privacy_utility_v2.py
    model = LogisticRegression(
        max_iter=1000,
        random_state=42,
        class_weight="balanced"
    )
    model.fit(X_train_scaled, y_train)

    # Get scores - same formula: round(1000 * (1 - P(default)))
    proba = model.predict_proba(X_test_scaled)[:, 1]  # P(default)
    scores = np.round(1000 * (1 - proba)).astype(int)
    scores = np.clip(scores, 0, 1000)

    return scores, y_test


def compute_band_assignment(scores, bands):
    """Assign each score to its band (floor-based for consistency with ZK)."""
    bands = sorted(bands)
    assignments = np.zeros(len(scores), dtype=int)

    for i, score in enumerate(scores):
        # Find the band this score satisfies (highest band <= score)
        for j, band in enumerate(bands):
            if score >= band:
                assignments[i] = j

    return assignments


def compute_posterior_entropy(scores, bands):
    """
    Compute the adversary's posterior entropy after observing a band.

    For each band, compute the entropy of the conditional score distribution.
    Then weight by the probability of each band to get expected posterior entropy.

    Returns:
    --------
    dict with prior_entropy, posterior_entropy, information_leakage, log2_B_bound
    """
    bands = sorted(bands)
    n = len(scores)

    # Prior entropy (uniform over observed scores)
    score_counts = Counter(scores)
    unique_scores = len(score_counts)

    # Prior is uniform over unique scores
    prior_entropy = np.log2(unique_scores)

    # Actually compute entropy of empirical distribution
    probs = np.array(list(score_counts.values())) / n
    prior_entropy_empirical = -np.sum(probs * np.log2(probs))

    # Assign scores to bands
    assignments = compute_band_assignment(scores, bands)

    # Compute posterior entropy for each band
    band_entropies = []
    band_probs = []
    band_details = []

    for b in range(len(bands)):
        # Scores in this band
        mask = assignments == b
        band_scores = scores[mask]

        if len(band_scores) == 0:
            continue

        band_prob = len(band_scores) / n
        band_probs.append(band_prob)

        # Entropy within this band
        band_counts = Counter(band_scores)
        band_probs_inner = np.array(list(band_counts.values())) / len(band_scores)
        band_entropy = -np.sum(band_probs_inner * np.log2(band_probs_inner))
        band_entropies.append(band_entropy)

        band_details.append({
            "band": bands[b],
            "count": len(band_scores),
            "probability": band_prob,
            "unique_scores": len(band_counts),
            "entropy": band_entropy,
            "min_score": int(min(band_scores)),
            "max_score": int(max(band_scores))
        })

    # Expected posterior entropy (weighted by band probability)
    expected_posterior = sum(p * e for p, e in zip(band_probs, band_entropies))

    # Information leakage = prior - posterior
    information_leakage = prior_entropy_empirical - expected_posterior

    # Theoretical log2(B) bound (uniform assumption)
    effective_bands = sum(1 for d in band_details if d["count"] > 0)
    log2_B = np.log2(effective_bands) if effective_bands > 1 else 0

    return {
        "prior_entropy_bits": float(prior_entropy_empirical),
        "expected_posterior_entropy_bits": float(expected_posterior),
        "information_leakage_bits": float(information_leakage),
        "log2_B_bound": float(log2_B),
        "leakage_exceeds_bound": information_leakage > log2_B,
        "effective_bands": effective_bands,
        "band_details": band_details
    }


def create_equidistant_bands(min_score, max_score, B):
    """Create B equidistant bands across the score range."""
    return [int(min_score + i * (max_score - min_score) / (B - 1)) for i in range(B)]


def create_quantile_bands(scores, B):
    """Create B bands at quantiles of the score distribution."""
    quantiles = np.linspace(0, 100, B)
    bands = np.percentile(scores, quantiles).astype(int)
    return sorted(set(bands))  # Remove duplicates


def main():
    print("=== T29: Adversary's True Posterior Entropy ===\n")

    # Load scores
    scores, y_test = load_scores()

    print(f"Test set: {len(scores)} samples")
    print(f"Score range: [{scores.min()}, {scores.max()}]")
    print(f"Unique scores: {len(set(scores))}")
    print()

    results = {
        "timestamp": datetime.now().isoformat(),
        "n_samples": len(scores),
        "score_range": [int(scores.min()), int(scores.max())],
        "unique_scores": len(set(scores)),
        "equidistant_analysis": {},
        "quantile_analysis": {},
        "summary": {}
    }

    B_values = [2, 3, 4, 5, 6, 8, 10, 15, 20]

    print("=" * 80)
    print("EQUIDISTANT BANDS")
    print("=" * 80)
    print()
    print("| B | log2(B) | True Leakage | Exceeds Bound | Residual Ent. |")
    print("|---|---------|--------------|---------------|---------------|")

    for B in B_values:
        bands = create_equidistant_bands(scores.min(), scores.max(), B)
        analysis = compute_posterior_entropy(scores, bands)
        results["equidistant_analysis"][str(B)] = {
            "bands": bands,
            **analysis
        }

        exceeds = "YES" if analysis["leakage_exceeds_bound"] else "no"
        print(f"| {B:2d} | {analysis['log2_B_bound']:.2f}    | {analysis['information_leakage_bits']:.2f}         | {exceeds:>13} | {analysis['expected_posterior_entropy_bits']:.2f}          |")

    print()
    print("=" * 80)
    print("QUANTILE BANDS")
    print("=" * 80)
    print()
    print("| B | log2(B) | True Leakage | Exceeds Bound | Residual Ent. |")
    print("|---|---------|--------------|---------------|---------------|")

    for B in B_values:
        bands = create_quantile_bands(scores, B)
        actual_B = len(bands)
        analysis = compute_posterior_entropy(scores, bands)
        results["quantile_analysis"][str(B)] = {
            "requested_B": B,
            "actual_B": actual_B,
            "bands": [int(b) for b in bands],
            **analysis
        }

        exceeds = "YES" if analysis["leakage_exceeds_bound"] else "no"
        print(f"| {B:2d} | {analysis['log2_B_bound']:.2f}    | {analysis['information_leakage_bits']:.2f}         | {exceeds:>13} | {analysis['expected_posterior_entropy_bits']:.2f}          |")

    # Summary
    print()
    print("=" * 80)
    print("ANALYSIS")
    print("=" * 80)

    # Check if leakage ever exceeds the bound
    equid_exceeds = [
        (B, r["information_leakage_bits"], r["log2_B_bound"])
        for B, r in results["equidistant_analysis"].items()
        if r["leakage_exceeds_bound"]
    ]

    quant_exceeds = [
        (B, r["information_leakage_bits"], r["log2_B_bound"])
        for B, r in results["quantile_analysis"].items()
        if r["leakage_exceeds_bound"]
    ]

    if equid_exceeds or quant_exceeds:
        print("\nWARNING: True leakage EXCEEDS log2(B) bound in some cases!")
        for B, leak, bound in equid_exceeds:
            print(f"  Equidistant B={B}: leakage {leak:.2f} > bound {bound:.2f}")
        for B, leak, bound in quant_exceeds:
            print(f"  Quantile B={B}: leakage {leak:.2f} > bound {bound:.2f}")
        results["summary"]["bound_violated"] = True
        results["summary"]["violation_cases"] = {
            "equidistant": equid_exceeds,
            "quantile": quant_exceeds
        }
    else:
        print("\nlog2(B) bound holds for all tested configurations.")
        print("True leakage is LESS than the theoretical bound because:")
        print("  - Bands with fewer unique scores have lower entropy")
        print("  - The bound assumes worst-case (uniform) distribution")
        results["summary"]["bound_violated"] = False

    # Compare equidistant vs quantile at B=4
    eq_4 = results["equidistant_analysis"]["4"]
    qu_4 = results["quantile_analysis"]["4"]

    print()
    print("Comparison at B=4:")
    print(f"  Equidistant: leakage {eq_4['information_leakage_bits']:.2f} bits, residual {eq_4['expected_posterior_entropy_bits']:.2f} bits")
    print(f"  Quantile:    leakage {qu_4['information_leakage_bits']:.2f} bits, residual {qu_4['expected_posterior_entropy_bits']:.2f} bits")

    if qu_4['expected_posterior_entropy_bits'] > eq_4['expected_posterior_entropy_bits']:
        print("  -> Quantile provides MORE residual uncertainty (better privacy)")
        results["summary"]["quantile_better_privacy"] = True
    else:
        print("  -> Equidistant provides more residual uncertainty")
        results["summary"]["quantile_better_privacy"] = False

    results["summary"]["conclusion"] = (
        "The log2(B) bound is conservative - true leakage is typically less "
        "because within-band score distributions are not uniform. The bound "
        "remains valid as an upper limit on information leakage."
    )

    # Convert numpy types for JSON serialization
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
    output_path = RESULTS_DIR / "adversary_entropy.json"
    with open(output_path, "w") as f:
        json.dump(convert_types(results), f, indent=2)
    print(f"\nResults saved to {output_path}")

    # Append to SUMMARY.md
    summary_path = RESULTS_DIR / "SUMMARY.md"
    summary_entry = f"""
### adversary_entropy - {datetime.now().strftime('%Y-%m-%d')}
**What was run:** T29 adversary's true posterior entropy analysis.
**Why:** Check if log2(B) overstates privacy by assuming uniform distribution within bands.
**Key numbers:**

| B | Placement | log2(B) | True Leakage | Exceeds? |
|---|-----------|---------|--------------|----------|
| 4 | Equidistant | {eq_4['log2_B_bound']:.2f} | {eq_4['information_leakage_bits']:.2f} | {'Yes' if eq_4['leakage_exceeds_bound'] else 'No'} |
| 4 | Quantile | {qu_4['log2_B_bound']:.2f} | {qu_4['information_leakage_bits']:.2f} | {'Yes' if qu_4['leakage_exceeds_bound'] else 'No'} |

**Conclusion:** log2(B) bound is conservative - true leakage typically less than the bound because within-band distributions are non-uniform. The bound remains valid as an upper limit.
"""

    with open(summary_path, "a") as f:
        f.write(summary_entry)
    print(f"Summary appended to {summary_path}")


if __name__ == "__main__":
    main()
