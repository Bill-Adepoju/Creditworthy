"""
T8: Score → Commitment Bridge
Proves that L1 (ML scoring) and L3 (ZK verification) actually connect.

Takes the model's P(default), scales to integer score 0-1000,
and prepares data for ZK commitment verification.
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
import subprocess

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"
CIRCUITS_DIR = Path(__file__).parent.parent / "circuits"

RANDOM_STATE = 42


def load_data():
    """Load processed features."""
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)
    return df, feature_info


def scale_to_score(p_default):
    """
    Convert P(default) to integer credit score.
    Per CLAUDE.md: score = round(1000 * (1 - P(default)))
    Range: 0 (certain default) to 1000 (no default risk)
    """
    return int(round(1000 * (1 - p_default)))


def generate_salt():
    """Generate a random salt for commitment blinding."""
    # Use a large random integer (fits in circuit's field)
    return int(np.random.randint(1, 2**31 - 1))


def main():
    print("=== T8: Score to Commitment Bridge ===\n")

    df, feature_info = load_data()

    # Use full feature set
    feature_cols = feature_info["feature_sets"]["full"]["features"]
    X = df[feature_cols]
    y = df["target"]

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE
    )

    # Scale and train model
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    model.fit(X_train_scaled, y_train)

    # Get predictions
    y_prob = model.predict_proba(X_test_scaled)[:, 1]  # P(default)

    # Convert to credit scores
    scores = [scale_to_score(p) for p in y_prob]

    print(f"Score distribution:")
    print(f"  Min: {min(scores)}")
    print(f"  Max: {max(scores)}")
    print(f"  Mean: {np.mean(scores):.1f}")
    print(f"  Median: {np.median(scores):.1f}")

    # Generate salts and prepare test cases
    np.random.seed(RANDOM_STATE)
    test_cases = []

    # Select diverse examples
    # 1. Low score (high risk)
    # 2. Medium score
    # 3. High score (low risk)
    # 4. Borderline at common threshold (e.g., 600)

    score_arr = np.array(scores)
    indices = [
        np.argmin(score_arr),  # Lowest score
        np.argmax(score_arr),  # Highest score
        np.argmin(np.abs(score_arr - 500)),  # Closest to 500
        np.argmin(np.abs(score_arr - 600)),  # Closest to 600 threshold
        np.argmin(np.abs(score_arr - 700)),  # Closest to 700 threshold
    ]

    for idx in indices:
        score = scores[idx]
        salt = generate_salt()
        actual = int(y_test.iloc[idx])
        p_default = float(y_prob[idx])

        test_cases.append({
            "score": score,
            "salt": salt,
            "p_default": p_default,
            "actual_default": actual
        })

    print(f"\n{len(test_cases)} test cases prepared for ZK verification:")
    for i, tc in enumerate(test_cases):
        status = "Default" if tc["actual_default"] else "Non-default"
        print(f"  {i+1}. Score={tc['score']}, P(default)={tc['p_default']:.3f}, Actual={status}")

    # Write test cases for Node.js bridge test
    bridge_input = {
        "test_cases": test_cases,
        "thresholds": [500, 600, 700, 800]  # Common thresholds to test
    }

    with open(CIRCUITS_DIR / "bridge_test_input.json", "w") as f:
        json.dump(bridge_input, f, indent=2)

    print(f"\nTest cases written to {CIRCUITS_DIR / 'bridge_test_input.json'}")
    print("Running ZK bridge test...")

    # Run the Node.js bridge test
    try:
        result = subprocess.run(
            ["node", "bridge_test.js"],
            cwd=CIRCUITS_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        if result.returncode != 0:
            print(f"Bridge test failed with return code {result.returncode}")
        else:
            print("Bridge test completed successfully!")

            # Read results
            with open(CIRCUITS_DIR / "bridge_test_output.json") as f:
                bridge_results = json.load(f)

            # Save to results
            final_results = {
                "timestamp": datetime.now().isoformat(),
                "model": "LogisticRegression",
                "score_stats": {
                    "min": int(min(scores)),
                    "max": int(max(scores)),
                    "mean": float(np.mean(scores)),
                    "median": float(np.median(scores))
                },
                "test_cases": test_cases,
                "zk_verification": bridge_results
            }

            with open(RESULTS_DIR / "bridge_test.json", "w") as f:
                json.dump(final_results, f, indent=2)

            print(f"\nFinal results saved to {RESULTS_DIR / 'bridge_test.json'}")

    except FileNotFoundError:
        print("Node.js bridge test script not found. Creating it...")
        # Will be created separately
        return None
    except subprocess.TimeoutExpired:
        print("Bridge test timed out")
        return None

    return final_results


if __name__ == "__main__":
    main()
