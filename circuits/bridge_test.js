/*
 * T8: Score → Commitment Bridge Test
 * Proves that L1 (ML scoring) and L3 (ZK verification) actually connect.
 *
 * Takes scores from the ML model, computes Poseidon commitments,
 * and verifies they round-trip through the ZK circuit.
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
  console.log("=== T8: Score-Commitment Bridge Test ===\n");

  // Check build artifacts
  if (!fs.existsSync(WASM)) {
    console.error("ERROR: ZK build artifacts not found. Run setup.js first.");
    process.exit(1);
  }

  // Load test cases from Python
  const inputPath = path.join(__dirname, "bridge_test_input.json");
  if (!fs.existsSync(inputPath)) {
    console.error("ERROR: bridge_test_input.json not found. Run commit.py first.");
    process.exit(1);
  }

  const { test_cases, thresholds } = JSON.parse(fs.readFileSync(inputPath));
  const poseidon = await circomlibjs.buildPoseidon();
  const F = poseidon.F;

  console.log(`Loaded ${test_cases.length} test cases`);
  console.log(`Testing thresholds: ${thresholds.join(", ")}\n`);

  const results = {
    test_cases: [],
    summary: {
      total_proofs_attempted: 0,
      proofs_generated: 0,
      proofs_verified: 0,
      correctly_rejected: 0
    }
  };

  for (let i = 0; i < test_cases.length; i++) {
    const tc = test_cases[i];
    console.log(`\n--- Test Case ${i + 1}: Score=${tc.score} ---`);

    // Compute Poseidon commitment
    const commitment = F.toObject(poseidon([tc.score, tc.salt])).toString();
    console.log(`Commitment: ${commitment.slice(0, 24)}...`);

    const caseResult = {
      score: tc.score,
      salt: tc.salt,
      commitment: commitment,
      actual_default: tc.actual_default,
      threshold_tests: []
    };

    // Test each threshold
    for (const threshold of thresholds) {
      results.summary.total_proofs_attempted++;

      const shouldPass = tc.score >= threshold;
      const input = {
        score: tc.score,
        salt: tc.salt.toString(),
        commitment: commitment,
        threshold: threshold
      };

      let proofGenerated = false;
      let proofVerified = false;
      let genTime = null;
      let verTime = null;

      try {
        const t0 = Date.now();
        const { proof, publicSignals } = await snarkjs.groth16.fullProve(input, WASM, ZKEY);
        genTime = Date.now() - t0;
        proofGenerated = true;
        results.summary.proofs_generated++;

        const t1 = Date.now();
        const ok = await snarkjs.groth16.verify(VKEY, publicSignals, proof);
        verTime = Date.now() - t1;

        if (ok) {
          proofVerified = true;
          results.summary.proofs_verified++;
        }

        if (shouldPass) {
          console.log(`  threshold=${threshold}: PASS (proof verified, ${genTime}ms gen, ${verTime}ms ver)`);
        } else {
          console.log(`  threshold=${threshold}: UNEXPECTED PASS (should have been rejected)`);
        }
      } catch (e) {
        if (!shouldPass) {
          console.log(`  threshold=${threshold}: CORRECTLY REJECTED (score < threshold)`);
          results.summary.correctly_rejected++;
        } else {
          console.log(`  threshold=${threshold}: UNEXPECTED FAILURE - ${e.message}`);
        }
      }

      caseResult.threshold_tests.push({
        threshold: threshold,
        should_pass: shouldPass,
        proof_generated: proofGenerated,
        proof_verified: proofVerified,
        gen_time_ms: genTime,
        ver_time_ms: verTime,
        result: proofVerified === shouldPass ? "correct" : "unexpected"
      });
    }

    results.test_cases.push(caseResult);
  }

  // Summary
  console.log("\n" + "=".repeat(50));
  console.log("SUMMARY");
  console.log("=".repeat(50));
  console.log(`Total proof attempts: ${results.summary.total_proofs_attempted}`);
  console.log(`Proofs generated: ${results.summary.proofs_generated}`);
  console.log(`Proofs verified: ${results.summary.proofs_verified}`);
  console.log(`Correctly rejected: ${results.summary.correctly_rejected}`);

  const correctBehavior = results.summary.proofs_verified + results.summary.correctly_rejected;
  const accuracy = (correctBehavior / results.summary.total_proofs_attempted * 100).toFixed(1);
  console.log(`\nBridge accuracy: ${accuracy}%`);
  results.summary.bridge_accuracy = parseFloat(accuracy);

  // Write results
  const outputPath = path.join(__dirname, "bridge_test_output.json");
  fs.writeFileSync(outputPath, JSON.stringify(results, null, 2));
  console.log(`\nResults written to ${outputPath}`);

  // Also write to /results
  const resultsPath = path.join(__dirname, "..", "results", "bridge_test.json");
  fs.writeFileSync(resultsPath, JSON.stringify({
    timestamp: new Date().toISOString(),
    ...results
  }, null, 2));
  console.log(`Results also written to ${resultsPath}`);

  if (results.summary.bridge_accuracy === 100) {
    console.log("\n[SUCCESS] L1 (ML) and L3 (ZK) are correctly connected!");
  } else {
    console.log("\n[WARNING] Some tests did not behave as expected.");
  }

  process.exit(results.summary.bridge_accuracy === 100 ? 0 : 1);
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
