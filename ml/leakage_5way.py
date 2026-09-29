"""
T54: Recompute Leakage Over 5-Way Partition

FIXES T49's understatement:
- T49 reported 1-bit leak (proof/no-proof signal)
- But full band membership is a 5-way partition:
  <400, 400-550, 550-700, 700-850, >=850
- True leakage is H = 1.988 bits (not 1 bit)

T29/T36 assumed 4 bands and did not treat "below lowest band" as a partition.

This analysis:
1. Computes entropy of 5-way partition
2. Distinguishes proof/no-proof (1 bit) from full band membership (~2 bits)
3. Updates the privacy-utility figures
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"

RANDOM_STATE = 42
BANDS = [400, 550, 700, 850]


def compute_entropy(probs):
    """Compute Shannon entropy H = -sum(p * log2(p))."""
    probs = np.array([p for p in probs if p > 0])
    return -np.sum(probs * np.log2(probs))


def assign_partition(score, bands):
    """Assign score to a 5-way partition."""
    if score < bands[0]:
        return f"<{bands[0]}"
    elif score >= bands[-1]:
        return f">={bands[-1]}"
    else:
        for i in range(len(bands) - 1):
            if bands[i] <= score < bands[i+1]:
                return f"{bands[i]}-{bands[i+1]}"
    return "unknown"


def main():
    print("=" * 60)
    print("T54: Recompute Leakage Over 5-Way Partition")
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

    X_train = X.loc[train_indices]
    X_test = X.loc[test_indices]
    y_train = y.loc[train_indices]
    y_test = y.loc[test_indices]

    # Scale and train
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    model.fit(X_train_scaled, y_train)

    # Get scores
    y_prob = model.predict_proba(X_test_scaled)[:, 1]
    scores = np.round(1000 * (1 - y_prob)).astype(int)

    print(f"Test set size: {len(scores)}")
    print(f"Score range: {scores.min()} - {scores.max()}")
    print(f"Bands: {BANDS}")
    print()

    # Assign partitions
    partitions = [assign_partition(s, BANDS) for s in scores]
    partition_counts = pd.Series(partitions).value_counts().sort_index()

    print("5-WAY PARTITION DISTRIBUTION:")
    print("| Partition | Count | Share |")
    print("|-----------|-------|-------|")
    total = len(partitions)
    partition_probs = {}
    for part, count in partition_counts.items():
        share = count / total
        partition_probs[part] = share
        print(f"| {part:<9} | {count:>5} | {share:>5.1%} |")

    print()

    # Compute entropy of 5-way partition
    probs_5way = list(partition_probs.values())
    H_5way = compute_entropy(probs_5way)
    print(f"Entropy of 5-way partition: H = {H_5way:.3f} bits")
    print(f"Maximum possible (uniform): H_max = log2(5) = {np.log2(5):.3f} bits")
    print()

    # Compare to 4-way (T29/T36 assumption)
    # 4-way excludes "<400" partition
    probs_4way = [partition_probs[p] for p in partition_probs if not p.startswith("<")]
    probs_4way_norm = [p / sum(probs_4way) for p in probs_4way]
    H_4way = compute_entropy(probs_4way_norm)

    print("COMPARISON TO PREVIOUS ANALYSES:")
    print(f"  T29/T36 assumed: 4 bands (excluded <400)")
    print(f"  4-way entropy (normalized): H = {H_4way:.3f} bits")
    print(f"  5-way entropy (correct): H = {H_5way:.3f} bits")
    print(f"  Understatement: {H_5way - H_4way:.3f} bits ({(H_5way - H_4way)/H_4way*100:.1f}%)")
    print()

    # Proof/no-proof signal (binary)
    can_prove_share = 1 - partition_probs.get(f"<{BANDS[0]}", 0)
    cannot_prove_share = partition_probs.get(f"<{BANDS[0]}", 0)
    H_binary = compute_entropy([can_prove_share, cannot_prove_share])

    print("DISTINGUISHING THE TWO LEAKAGE QUANTITIES:")
    print()
    print("1. PROOF/NO-PROOF SIGNAL (binary):")
    print(f"   Can prove (score >= {BANDS[0]}): {can_prove_share:.1%}")
    print(f"   Cannot prove (score < {BANDS[0]}): {cannot_prove_share:.1%}")
    print(f"   Entropy: H = {H_binary:.3f} bits")
    print()
    print("2. FULL BAND MEMBERSHIP (5-way):")
    print(f"   Entropy: H = {H_5way:.3f} bits")
    print()
    print("T49 reported '1 bit' which conflates these quantities.")
    print(f"The binary signal carries {H_binary:.3f} bits.")
    print(f"Full band membership carries {H_5way:.3f} bits.")
    print()

    # Conditional entropy: given proof/no-proof, what's the remaining uncertainty?
    # If no proof: definitely in <400 (0 bits remaining)
    # If proof: one of 4 upper partitions
    upper_probs = [partition_probs[p] / can_prove_share for p in partition_probs if not p.startswith("<")]
    H_upper = compute_entropy(upper_probs)

    print("CONDITIONAL ANALYSIS:")
    print(f"  If no proof: borrower is in <{BANDS[0]} (certain, 0 bits remaining)")
    print(f"  If proof: one of 4 upper bands (H = {H_upper:.3f} bits)")
    print(f"  Verification: H_binary + p(proof)*H_upper = {H_binary + can_prove_share*H_upper:.3f} bits")
    print(f"  Matches H_5way: {abs(H_5way - (H_binary + can_prove_share*H_upper)) < 0.01}")
    print()

    # Compile results
    results = {
        "timestamp": datetime.now().isoformat(),
        "task": "T54",
        "title": "5-Way Partition Leakage Analysis",
        "canonical_test_size": len(scores),
        "random_state": RANDOM_STATE,
        "bands": BANDS,

        "partition_distribution": {
            "partitions": {k: int(v) for k, v in dict(partition_counts).items()},
            "shares": {k: round(v, 4) for k, v in partition_probs.items()},
            "total": int(total)
        },

        "entropy_analysis": {
            "H_5way": round(H_5way, 4),
            "H_5way_max": round(np.log2(5), 4),
            "H_4way_normalized": round(H_4way, 4),
            "understatement_bits": round(H_5way - H_4way, 4),
            "understatement_pct": round((H_5way - H_4way)/H_4way*100, 1)
        },

        "two_leakage_quantities": {
            "binary_proof_signal": {
                "description": "Whether a proof is submitted (yes/no)",
                "can_prove_share": round(can_prove_share, 4),
                "cannot_prove_share": round(cannot_prove_share, 4),
                "entropy_bits": round(H_binary, 4),
                "note": "This is what T49 called '1 bit' but actual entropy depends on distribution"
            },
            "full_band_membership": {
                "description": "Which of 5 partitions the borrower falls into",
                "partitions": 5,
                "entropy_bits": round(H_5way, 4),
                "note": "Full information revealed by band-based verification"
            }
        },

        "conditional_analysis": {
            "if_no_proof": "Score < 400 (certain, 0 bits remaining)",
            "if_proof": f"One of 4 upper bands (H = {round(H_upper, 4)} bits)",
            "decomposition": f"H(5-way) = H(binary) + P(proof)*H(upper|proof) = {round(H_binary + can_prove_share*H_upper, 4)}"
        },

        "corrections_to_prior_analyses": {
            "t29_t36": "Assumed 4 bands, excluded <400 partition. Understated leakage by ~0.15 bits.",
            "t49": "Reported '1 bit' but conflated binary signal with full partition. Binary signal is ~0.78 bits; full partition is ~1.99 bits."
        },

        "chapter_5_update": (
            f"With 4 threshold bands {{400, 550, 700, 850}}, borrowers are partitioned into 5 groups "
            f"(including <400). Full band membership reveals H = {H_5way:.2f} bits of information. "
            f"The proof/no-proof binary signal alone reveals H = {H_binary:.2f} bits, dominated by "
            f"the {cannot_prove_share:.1%} of borrowers who cannot generate any proof."
        )
    }

    output_path = RESULTS_DIR / "leakage_5way.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to: {output_path}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"\nT49 reported: 1 bit")
    print(f"Actual binary signal: {H_binary:.3f} bits")
    print(f"Full 5-way partition: {H_5way:.3f} bits")
    print(f"\nT29/T36 understatement: {H_5way - H_4way:.3f} bits ({(H_5way - H_4way)/H_4way*100:.1f}%)")

    return results


if __name__ == "__main__":
    main()
