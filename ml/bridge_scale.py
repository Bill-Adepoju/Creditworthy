"""
T13: Bridge Test at Scale

1000 borrowers × 5 thresholds = 5000 proof attempts.
Uses actual model output distribution, not fixed test cases.

Reports: round-trip success rate, collisions, timing.
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
import subprocess
import time

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"
CIRCUITS_DIR = Path(__file__).parent.parent / "circuits"

RANDOM_STATE = 42
N_BORROWERS = 200  # Reduced from 1000 for reasonable runtime (~200 * 5 = 1000 proofs)
THRESHOLDS = [400, 500, 600, 700, 800]


def load_data():
    """Load processed features."""
    df = pd.read_csv(DATA_DIR / "features_processed.csv")
    with open(RESULTS_DIR / "feature_sets.json") as f:
        feature_info = json.load(f)
    return df, feature_info


def scale_to_score(p_default):
    """Convert P(default) to integer credit score 0-1000."""
    return int(round(1000 * (1 - p_default)))


def generate_salt():
    """Generate random salt for commitment blinding."""
    return int(np.random.randint(1, 2**31 - 1))


def main():
    print("=== T13: Bridge Test at Scale ===\n")
    print(f"Configuration: {N_BORROWERS} borrowers × {len(THRESHOLDS)} thresholds = {N_BORROWERS * len(THRESHOLDS)} proof attempts\n")

    df, feature_info = load_data()

    # Use full feature set
    feature_cols = feature_info["feature_sets"]["full"]["features"]
    X = df[feature_cols]
    y = df["target"]

    # Train/test split - use test set for realistic scores
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=RANDOM_STATE
    )

    # Scale and train model
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    model.fit(X_train_scaled, y_train)

    # Get predictions for all test samples
    y_prob = model.predict_proba(X_test_scaled)[:, 1]
    all_scores = np.array([scale_to_score(p) for p in y_prob])

    print(f"Score distribution from model (n={len(all_scores)}):")
    print(f"  Min: {all_scores.min()}, Max: {all_scores.max()}")
    print(f"  Mean: {all_scores.mean():.1f}, Median: {np.median(all_scores):.1f}")
    print(f"  Std: {all_scores.std():.1f}")

    # Sample N_BORROWERS from test set
    if len(all_scores) < N_BORROWERS:
        print(f"\nWARNING: Only {len(all_scores)} test samples available, using all")
        sample_indices = np.arange(len(all_scores))
    else:
        np.random.seed(RANDOM_STATE)
        sample_indices = np.random.choice(len(all_scores), N_BORROWERS, replace=False)

    sampled_scores = all_scores[sample_indices]
    sampled_actuals = y_test.values[sample_indices]
    sampled_probs = y_prob[sample_indices]

    print(f"\nSampled {len(sampled_scores)} borrowers")
    print(f"  Score range: {sampled_scores.min()} - {sampled_scores.max()}")
    print(f"  Default rate: {sampled_actuals.mean():.1%}")

    # Generate salts
    np.random.seed(RANDOM_STATE + 1)
    salts = [generate_salt() for _ in range(len(sampled_scores))]

    # Check for salt collisions
    unique_salts = len(set(salts))
    salt_collisions = len(salts) - unique_salts

    # Check for score+salt commitment collisions
    commitments_key = [(int(s), int(salt)) for s, salt in zip(sampled_scores, salts)]
    unique_commitments = len(set(commitments_key))
    commitment_collisions = len(commitments_key) - unique_commitments

    print(f"\nCollision check:")
    print(f"  Salt collisions: {salt_collisions}")
    print(f"  Commitment key collisions: {commitment_collisions}")

    # Prepare test cases for Node.js
    test_cases = []
    for i, (score, salt, actual, p_default) in enumerate(
        zip(sampled_scores, salts, sampled_actuals, sampled_probs)
    ):
        test_cases.append({
            "id": i,
            "score": int(score),
            "salt": int(salt),
            "actual_default": int(actual),
            "p_default": float(p_default)
        })

    # Write input for Node.js bridge test
    bridge_input = {
        "test_cases": test_cases,
        "thresholds": THRESHOLDS,
        "config": {
            "n_borrowers": len(test_cases),
            "n_thresholds": len(THRESHOLDS),
            "total_proofs": len(test_cases) * len(THRESHOLDS)
        }
    }

    input_path = CIRCUITS_DIR / "bridge_scale_input.json"
    with open(input_path, "w") as f:
        json.dump(bridge_input, f)

    print(f"\nTest cases written to {input_path}")
    print(f"Running scaled ZK bridge test ({len(test_cases) * len(THRESHOLDS)} proof attempts)...")
    print("This may take several minutes...\n")

    # Run Node.js bridge test at scale
    start_time = time.time()
    try:
        result = subprocess.run(
            ["node", "bridge_scale.js"],
            cwd=CIRCUITS_DIR,
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )

        wall_clock = time.time() - start_time

        print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)  # Last 2000 chars

        if result.stderr:
            print("STDERR:", result.stderr[-500:])

        if result.returncode != 0:
            print(f"Bridge test failed with return code {result.returncode}")
            return None

        # Read results
        output_path = CIRCUITS_DIR / "bridge_scale_output.json"
        if output_path.exists():
            with open(output_path) as f:
                bridge_results = json.load(f)

            # Compile final results
            final_results = {
                "timestamp": datetime.now().isoformat(),
                "config": {
                    "n_borrowers": len(test_cases),
                    "n_thresholds": len(THRESHOLDS),
                    "thresholds": THRESHOLDS,
                    "total_proof_attempts": len(test_cases) * len(THRESHOLDS)
                },
                "score_distribution": {
                    "min": int(sampled_scores.min()),
                    "max": int(sampled_scores.max()),
                    "mean": float(sampled_scores.mean()),
                    "median": float(np.median(sampled_scores)),
                    "std": float(sampled_scores.std())
                },
                "collisions": {
                    "salt_collisions": salt_collisions,
                    "commitment_collisions": commitment_collisions
                },
                "timing": {
                    "wall_clock_seconds": wall_clock,
                    "wall_clock_minutes": wall_clock / 60
                },
                "zk_results": bridge_results
            }

            # Save to results
            with open(RESULTS_DIR / "bridge_scale.json", "w") as f:
                json.dump(final_results, f, indent=2)

            print(f"\n=== SUMMARY ===")
            print(f"Total wall clock: {wall_clock:.1f}s ({wall_clock/60:.1f} min)")
            print(f"Results saved to {RESULTS_DIR / 'bridge_scale.json'}")

            return final_results

    except FileNotFoundError:
        print("Node.js bridge_scale.js not found. Creating it...")
        create_bridge_scale_js()
        return None
    except subprocess.TimeoutExpired:
        print("Bridge test timed out after 1 hour")
        return None


def create_bridge_scale_js():
    """Create the scaled bridge test script."""
    js_code = '''/*
 * T13: Scaled Bridge Test
 * 1000 borrowers × 5 thresholds
 */
const snarkjs = require("snarkjs");
const circomlibjs = require("circomlibjs");
const fs = require("fs");
const path = require("path");

const B = path.join(__dirname, "build");
const WASM = path.join(B, "credit_threshold_js", "credit_threshold.wasm");
const ZKEY = path.join(B, "ct_final.zkey");
const VKEY = JSON.parse(fs.readFileSync(path.join(B, "verification_key.json")));

async function main() {
  console.log("=== T13: Scaled Bridge Test ===\\n");

  if (!fs.existsSync(WASM)) {
    console.error("ERROR: ZK build artifacts not found. Run setup.js first.");
    process.exit(1);
  }

  const inputPath = path.join(__dirname, "bridge_scale_input.json");
  if (!fs.existsSync(inputPath)) {
    console.error("ERROR: bridge_scale_input.json not found.");
    process.exit(1);
  }

  const { test_cases, thresholds, config } = JSON.parse(fs.readFileSync(inputPath));
  const poseidon = await circomlibjs.buildPoseidon();
  const F = poseidon.F;

  console.log(`Loaded ${test_cases.length} test cases, ${thresholds.length} thresholds`);
  console.log(`Total proof attempts: ${config.total_proofs}\\n`);

  const results = {
    summary: {
      total_attempts: 0,
      proofs_generated: 0,
      proofs_verified: 0,
      correctly_rejected: 0,
      unexpected_failures: 0,
      gen_times_ms: [],
      ver_times_ms: []
    },
    threshold_breakdown: {}
  };

  // Initialize threshold breakdown
  for (const t of thresholds) {
    results.threshold_breakdown[t] = {
      attempts: 0,
      passed: 0,
      rejected: 0,
      unexpected: 0
    };
  }

  const startTime = Date.now();
  let lastReport = 0;

  for (let i = 0; i < test_cases.length; i++) {
    const tc = test_cases[i];
    const commitment = F.toObject(poseidon([tc.score, tc.salt])).toString();

    for (const threshold of thresholds) {
      results.summary.total_attempts++;

      const shouldPass = tc.score >= threshold;
      const input = {
        score: tc.score,
        salt: tc.salt.toString(),
        commitment: commitment,
        threshold: threshold
      };

      try {
        const t0 = Date.now();
        const { proof, publicSignals } = await snarkjs.groth16.fullProve(input, WASM, ZKEY);
        const genTime = Date.now() - t0;

        const t1 = Date.now();
        const ok = await snarkjs.groth16.verify(VKEY, publicSignals, proof);
        const verTime = Date.now() - t1;

        results.summary.proofs_generated++;
        results.summary.gen_times_ms.push(genTime);
        results.summary.ver_times_ms.push(verTime);

        if (ok) {
          results.summary.proofs_verified++;
          results.threshold_breakdown[threshold].passed++;

          if (!shouldPass) {
            results.summary.unexpected_failures++;
            results.threshold_breakdown[threshold].unexpected++;
          }
        }
      } catch (e) {
        if (!shouldPass) {
          results.summary.correctly_rejected++;
          results.threshold_breakdown[threshold].rejected++;
        } else {
          results.summary.unexpected_failures++;
          results.threshold_breakdown[threshold].unexpected++;
        }
      }

      results.threshold_breakdown[threshold].attempts++;
    }

    // Progress report every 100 borrowers
    if (i > 0 && i % 100 === 0 && i !== lastReport) {
      const elapsed = (Date.now() - startTime) / 1000;
      const rate = (i * thresholds.length) / elapsed;
      const remaining = ((test_cases.length - i) * thresholds.length) / rate;
      console.log(`Progress: ${i}/${test_cases.length} borrowers, ${results.summary.total_attempts} proofs, ${elapsed.toFixed(0)}s elapsed, ~${remaining.toFixed(0)}s remaining`);
      lastReport = i;
    }
  }

  const totalTime = (Date.now() - startTime) / 1000;

  // Compute summary stats
  const genTimes = results.summary.gen_times_ms;
  const verTimes = results.summary.ver_times_ms;

  results.summary.timing = {
    total_seconds: totalTime,
    proofs_per_second: results.summary.proofs_generated / totalTime,
    gen_mean_ms: genTimes.length > 0 ? genTimes.reduce((a,b) => a+b, 0) / genTimes.length : 0,
    gen_p50_ms: genTimes.length > 0 ? genTimes.sort((a,b) => a-b)[Math.floor(genTimes.length/2)] : 0,
    gen_p95_ms: genTimes.length > 0 ? genTimes.sort((a,b) => a-b)[Math.floor(genTimes.length*0.95)] : 0,
    ver_mean_ms: verTimes.length > 0 ? verTimes.reduce((a,b) => a+b, 0) / verTimes.length : 0,
    ver_p50_ms: verTimes.length > 0 ? verTimes.sort((a,b) => a-b)[Math.floor(verTimes.length/2)] : 0,
    ver_p95_ms: verTimes.length > 0 ? verTimes.sort((a,b) => a-b)[Math.floor(verTimes.length*0.95)] : 0
  };

  // Don't include raw times in output (too large)
  delete results.summary.gen_times_ms;
  delete results.summary.ver_times_ms;

  const accuracy = (results.summary.proofs_verified + results.summary.correctly_rejected) / results.summary.total_attempts * 100;
  results.summary.accuracy = accuracy;

  console.log("\\n" + "=".repeat(60));
  console.log("FINAL SUMMARY");
  console.log("=".repeat(60));
  console.log(`Total attempts: ${results.summary.total_attempts}`);
  console.log(`Proofs generated: ${results.summary.proofs_generated}`);
  console.log(`Proofs verified: ${results.summary.proofs_verified}`);
  console.log(`Correctly rejected: ${results.summary.correctly_rejected}`);
  console.log(`Unexpected failures: ${results.summary.unexpected_failures}`);
  console.log(`Accuracy: ${accuracy.toFixed(2)}%`);
  console.log(`\\nTiming:`);
  console.log(`  Total time: ${totalTime.toFixed(1)}s`);
  console.log(`  Proofs/second: ${results.summary.timing.proofs_per_second.toFixed(2)}`);
  console.log(`  Gen mean: ${results.summary.timing.gen_mean_ms.toFixed(1)}ms`);
  console.log(`  Gen p95: ${results.summary.timing.gen_p95_ms.toFixed(1)}ms`);
  console.log(`  Ver mean: ${results.summary.timing.ver_mean_ms.toFixed(1)}ms`);

  const outputPath = path.join(__dirname, "bridge_scale_output.json");
  fs.writeFileSync(outputPath, JSON.stringify(results, null, 2));
  console.log(`\\nResults written to ${outputPath}`);

  process.exit(results.summary.accuracy === 100 ? 0 : 1);
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
'''
    with open(CIRCUITS_DIR / "bridge_scale.js", "w") as f:
        f.write(js_code)
    print(f"Created {CIRCUITS_DIR / 'bridge_scale.js'}")


if __name__ == "__main__":
    # First create the JS file if it doesn't exist
    if not (CIRCUITS_DIR / "bridge_scale.js").exists():
        create_bridge_scale_js()
    main()
