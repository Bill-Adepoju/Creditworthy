"""
T49: Sub-Lowest-Band Borrower Analysis

Analyzes borrowers whose scores fall below the lowest threshold band.
Documents the design consequence: a borrower below the lowest band cannot
generate ANY proof, so the lender cannot distinguish "below lowest band"
from "refused to prove". This is a 1-bit information leak unavoidable in
threshold schemes.

Key finding: This is CORRECT circuit behavior, not a failure.
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


def main():
    print("=" * 60)
    print("T49: Sub-Lowest-Band Borrower Analysis")
    print("=" * 60)
    print()

    # Load data
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)

    feature_cols = feature_info["feature_sets"]["full"]["features"]
    X = df[feature_cols]
    y = df["target"]

    # Use canonical split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE
    )

    # Train model
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

    # Count borrowers in each band category
    lowest_band = BANDS[0]
    sub_lowest = (scores < lowest_band).sum()
    total = len(scores)

    print(f"Borrowers below lowest band ({lowest_band}):")
    print(f"  Count: {sub_lowest}")
    print(f"  Percentage: {sub_lowest / total * 100:.1f}%")
    print()

    # Distribution of sub-lowest-band borrowers
    sub_lowest_scores = scores[scores < lowest_band]
    print(f"Score distribution for sub-lowest-band borrowers:")
    print(f"  Min: {sub_lowest_scores.min() if len(sub_lowest_scores) > 0 else 'N/A'}")
    print(f"  Max: {sub_lowest_scores.max() if len(sub_lowest_scores) > 0 else 'N/A'}")
    print(f"  Mean: {sub_lowest_scores.mean():.0f}" if len(sub_lowest_scores) > 0 else "  N/A")
    print()

    # Default rate among sub-lowest-band borrowers
    y_test_array = y_test.values
    sub_lowest_mask = scores < lowest_band
    sub_lowest_default_rate = y_test_array[sub_lowest_mask].mean() if sub_lowest_mask.sum() > 0 else 0

    print(f"Actual default rate among sub-lowest-band borrowers: {sub_lowest_default_rate:.1%}")
    print()

    # Band distribution
    print("Full band distribution:")
    band_counts = {f"<{BANDS[0]}": 0}
    for i, band in enumerate(BANDS):
        if i == len(BANDS) - 1:
            band_counts[f">={band}"] = 0
        else:
            band_counts[f"{band}-{BANDS[i+1]}"] = 0

    for score in scores:
        if score < BANDS[0]:
            band_counts[f"<{BANDS[0]}"] += 1
        elif score >= BANDS[-1]:
            band_counts[f">={BANDS[-1]}"] += 1
        else:
            for i in range(len(BANDS) - 1):
                if BANDS[i] <= score < BANDS[i+1]:
                    band_counts[f"{BANDS[i]}-{BANDS[i+1]}"] += 1
                    break

    print("| Band Range | Count | Percentage |")
    print("|------------|-------|------------|")
    for band_range, count in band_counts.items():
        pct = count / total * 100
        print(f"| {band_range:<10} | {count:>5} | {pct:>10.1f}% |")

    print()

    # Information leak analysis
    print("=" * 60)
    print("INFORMATION LEAK ANALYSIS")
    print("=" * 60)
    print()
    print("Design consequence of threshold-banding:")
    print()
    print("1. A borrower below the lowest band cannot generate ANY valid proof.")
    print("2. The lender cannot distinguish:")
    print("   a) 'Score is below lowest band' from")
    print("   b) 'Borrower refused to prove'")
    print()
    print("This is a 1-bit information leak:")
    print("   - If proof is submitted: score >= lowest_band")
    print("   - If no proof: unknown (could be either case)")
    print()
    print("This leak is unavoidable in any threshold scheme:")
    print("   - The proof demonstrates score >= some_threshold")
    print("   - If no valid threshold exists, no proof is possible")
    print("   - Binary outcome (proof/no-proof) leaks 1 bit")
    print()

    # Compile results
    results = {
        "timestamp": datetime.now().isoformat(),
        "task": "T49",
        "title": "Sub-Lowest-Band Borrower Analysis",
        "bands": BANDS,
        "lowest_band": lowest_band,
        "random_state": RANDOM_STATE,

        "test_set": {
            "total": int(total),
            "score_min": int(scores.min()),
            "score_max": int(scores.max())
        },

        "sub_lowest_band": {
            "count": int(sub_lowest),
            "percentage": round(sub_lowest / total * 100, 1),
            "score_min": int(sub_lowest_scores.min()) if len(sub_lowest_scores) > 0 else None,
            "score_max": int(sub_lowest_scores.max()) if len(sub_lowest_scores) > 0 else None,
            "actual_default_rate": round(float(sub_lowest_default_rate), 4)
        },

        "band_distribution": {k: int(v) for k, v in band_counts.items()},

        "information_leak": {
            "bits_leaked": 1,
            "description": (
                "A borrower below the lowest band cannot generate ANY proof. "
                "The lender cannot distinguish 'below lowest band' from 'refused to prove'. "
                "This is a 1-bit information leak unavoidable in threshold schemes."
            ),
            "implications": [
                "If proof is submitted: score >= lowest_band is revealed",
                "If no proof: ambiguous (below band OR refusal)",
                "Binary outcome (proof/no-proof) inherently leaks 1 bit"
            ],
            "chapter_3_note": (
                "This should be stated in the threat model: a borrower below the lowest band "
                "cannot generate any proof, revealing at minimum that their score does not meet "
                "even the lowest threshold. This 1-bit leak is inherent to the threshold scheme."
            )
        },

        "handling_recommendation": {
            "circuit_behavior": "CORRECT - assertion fails because no band is satisfiable",
            "demo_behavior": "Should treat as EXPECTED OUTCOME, not exception",
            "api_response": "Return 'no_valid_band' status instead of error",
            "lender_interpretation": (
                "Lender sees: 'borrower did not submit proof'. "
                "Could mean: (a) score below all bands, or (b) borrower declined. "
                "Risk-averse lenders may treat absence of proof as rejection."
            )
        }
    }

    output_path = RESULTS_DIR / "sub_band_analysis.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to: {output_path}")

    # Summary for HANDOVER
    print("\n" + "=" * 60)
    print("SUMMARY FOR CHAPTER 3 THREAT MODEL")
    print("=" * 60)
    print()
    print(f"Sub-lowest-band borrowers: {sub_lowest} ({sub_lowest/total*100:.1f}% of test set)")
    print(f"Actual default rate: {sub_lowest_default_rate:.1%}")
    print()
    print("The 1-bit leak is UNAVOIDABLE:")
    print("  - Proof submitted -> score >= lowest_band")
    print("  - No proof -> indistinguishable (below band OR refusal)")
    print()
    print("Recommendation: Document in threat model, not as a bug.")

    return results


if __name__ == "__main__":
    main()
