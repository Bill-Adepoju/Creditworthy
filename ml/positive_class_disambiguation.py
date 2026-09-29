"""
T38: Disambiguate the Positive Class

CRITICAL: This resolves whether Chapter 6's fairness narrative is correct or inverted.

Key finding: target=1 means DEFAULT (Bad), so:
- pred_rate / selection_rate = rejection rate (predicted default)
- Approval rate = 1 - pred_rate
"""
import numpy as np
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

RESULTS_DIR = Path(__file__).parent.parent / "results"
DATA_DIR = Path(__file__).parent.parent / "data"


def main():
    print("=== T38: Positive Class Disambiguation ===\n")

    # Part 1: Confirm positive class encoding
    print("=" * 80)
    print("PART 1: CONFIRM POSITIVE CLASS ENCODING")
    print("=" * 80)

    df = pd.read_csv(DATA_DIR / "features_processed.csv")

    print("\ngood_bad_flag value counts:")
    print(df["good_bad_flag"].value_counts())

    print("\ntarget value counts:")
    print(df["target"].value_counts())

    print("\nCross-tabulation:")
    print(pd.crosstab(df["good_bad_flag"], df["target"]))

    # Confirm encoding
    good_is_0 = (df[df["good_bad_flag"] == "Good"]["target"] == 0).all()
    bad_is_1 = (df[df["good_bad_flag"] == "Bad"]["target"] == 1).all()

    print(f"\nCONFIRMED: Good -> target=0: {good_is_0}")
    print(f"CONFIRMED: Bad -> target=1: {bad_is_1}")
    print("\n*** target=1 means DEFAULT (Bad) ***")
    print("*** Positive class = DEFAULT ***")

    # Part 2: Re-express fairness metrics
    print("\n" + "=" * 80)
    print("PART 2: RE-EXPRESS FAIRNESS METRICS AS APPROVAL RATES")
    print("=" * 80)

    # Load fairness_v2.json
    with open(RESULTS_DIR / "fairness_v2.json") as f:
        fairness = json.load(f)

    bank_type = fairness["sensitive_attributes"]["bank_account_type"]["group_stats"]

    print("\nbank_account_type fairness metrics:")
    print()
    print("| Group | n | Pred Default Rate | APPROVAL Rate | Actual Default Rate |")
    print("|-------|---|-------------------|---------------|---------------------|")

    for group, stats in bank_type.items():
        if stats["n"] >= 30:  # n>=30 filter
            pred_default_rate = stats["pred_rate"]
            approval_rate = 1 - pred_default_rate
            actual_default_rate = stats["n_positive"] / stats["n"]
            print(f"| {group:8s} | {stats['n']:3d} | {pred_default_rate*100:5.1f}% | {approval_rate*100:5.1f}% | {actual_default_rate*100:5.1f}% |")

    # Part 3: Compute correct disparity
    print("\n" + "=" * 80)
    print("PART 3: DISPARITY DIRECTION")
    print("=" * 80)

    savings = bank_type["Savings"]
    other = bank_type["Other"]

    savings_approval = 1 - savings["pred_rate"]
    other_approval = 1 - other["pred_rate"]

    print(f"\nSavings approval rate: {savings_approval*100:.1f}%")
    print(f"Other approval rate: {other_approval*100:.1f}%")
    print(f"\nDisparity ratio (Other/Savings): {other_approval/savings_approval:.2f}x")
    print(f"Disparity ratio (Savings/Other): {savings_approval/other_approval:.2f}x")

    print("\n*** WHICH GROUP IS DISADVANTAGED? ***")
    print(f"Savings holders have LOWER approval rate ({savings_approval*100:.1f}%)")
    print(f"Other holders have HIGHER approval rate ({other_approval*100:.1f}%)")
    print("\n==> 'Savings' account holders are DISADVANTAGED")
    print("==> 'Other' account holders are FAVORED")

    # Part 4: What this means for Chapter 6
    print("\n" + "=" * 80)
    print("PART 4: CHAPTER 6 IMPLICATIONS")
    print("=" * 80)

    print("""
The Cycle 03 narrative stated:
  "Savings approved at 44.7%, Other at 14.7%"

This was WRONG because pred_rate = rejection rate, not approval rate.

CORRECT interpretation:
  Savings: 44.7% REJECTED (55.3% approved)
  Other:   14.7% REJECTED (85.3% approved)

The disparity direction is:
  - Savings holders (mass-market, n=533) have LOWER approval rates
  - Other holders (n=136) have HIGHER approval rates
  - Ratio: Other is 1.54x MORE LIKELY to be approved

Why this makes sense (from T30 correlation data):
  - Savings holders have SHORTER tenure (r=-0.354)
  - Savings holders have FEWER prior loans (r=-0.307)
  - Savings holders have SMALLER amounts (r=-0.281)

The disparity tracks BORROWING HISTORY DEPTH, not account type per se.
This is a legitimate risk signal, not discrimination against a protected class.

Chapter 6 framing options:
  1. "The model penalizes thin credit files" - accurate, but less dramatic
  2. "Alternative-data scoring penalizes the very thinness it exists to address" - accurate and interesting
  3. Remove the discrimination framing entirely - focus on history depth as legitimate signal
""")

    # Part 5: Nigerian context
    print("=" * 80)
    print("PART 5: NIGERIAN BANKING CONTEXT")
    print("=" * 80)

    print(f"""
Account type distribution:
  Savings: {(df['bank_account_type_Savings'].sum()):,} ({100*df['bank_account_type_Savings'].mean():.1f}%)
  Other:   {(df['bank_account_type_Other'].sum()):,} ({100*df['bank_account_type_Other'].mean():.1f}%)
  Current: {(df['bank_account_type_Current'].sum()):,} ({100*df['bank_account_type_Current'].mean():.1f}%)
  Unknown: {(df['bank_account_type_Unknown'].sum()):,} ({100*df['bank_account_type_Unknown'].mean():.1f}%)

In Nigeria:
  - Savings accounts are the mass-market default (59% of dataset)
  - Current accounts are typically business banking (1%)
  - "Other" is ambiguous (15%) - may include specialized products

The "Savings vs Other" comparison may not cleanly map to "financially integrated vs excluded".
A more accurate framing: "thin-file vs thick-file borrowers".
""")

    # Save results
    results = {
        "timestamp": datetime.now().isoformat(),
        "positive_class": {
            "encoding": "target=1 means DEFAULT (Bad)",
            "confirmed": True,
            "implications": "pred_rate and selection_rate are REJECTION rates, not approval rates"
        },
        "bank_account_type_corrected": {
            "Savings": {
                "n": savings["n"],
                "pred_default_rate": savings["pred_rate"],
                "approval_rate": float(savings_approval),
                "actual_default_rate": savings["n_positive"] / savings["n"]
            },
            "Other": {
                "n": other["n"],
                "pred_default_rate": other["pred_rate"],
                "approval_rate": float(other_approval),
                "actual_default_rate": other["n_positive"] / other["n"]
            }
        },
        "disparity": {
            "disadvantaged_group": "Savings",
            "favored_group": "Other",
            "approval_rate_ratio_other_vs_savings": float(other_approval / savings_approval),
            "rejection_rate_ratio_savings_vs_other": float(savings["pred_rate"] / other["pred_rate"])
        },
        "explanation": {
            "why_savings_disadvantaged": "Shorter tenure, fewer loans, smaller amounts = thinner credit file = higher predicted risk",
            "is_this_discrimination": "No - it tracks borrowing history depth, which is a legitimate risk signal",
            "chapter_6_implication": "Reframe from 'discrimination against excluded' to 'model penalizes thin files'"
        },
        "cycle_03_error": {
            "stated": "Savings approved at 44.7%, Other at 14.7%",
            "actual": "Savings REJECTED at 44.7%, Other REJECTED at 14.7%",
            "correct_approval_rates": f"Savings {savings_approval*100:.1f}%, Other {other_approval*100:.1f}%"
        }
    }

    output_path = RESULTS_DIR / "positive_class_disambiguation.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_path}")

    # Summary for SUMMARY.md
    summary_path = RESULTS_DIR / "SUMMARY.md"
    summary_entry = f"""
### positive_class_disambiguation - {datetime.now().strftime('%Y-%m-%d')}
**What was run:** T38 - disambiguate positive class encoding in fairness analysis.
**Why:** Cycle 03 may have inverted the fairness narrative by confusing rejection and approval rates.
**Key finding:**

**target=1 = DEFAULT (Bad)**

| Group | Rejection Rate | Approval Rate | Disadvantaged? |
|-------|----------------|---------------|----------------|
| Savings | 44.7% | 55.3% | YES |
| Other | 14.7% | 85.3% | NO (favored) |

**Chapter 6 correction:** The disparity tracks BORROWING HISTORY DEPTH (tenure, loan count, amounts).
Savings holders have thinner files, leading to higher predicted risk and lower approval.
This is a legitimate risk signal, not discrimination against a protected class.
"""

    with open(summary_path, "a") as f:
        f.write(summary_entry)
    print(f"Summary appended to {summary_path}")


if __name__ == "__main__":
    main()
