/*
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
  console.log("=== T13: Scaled Bridge Test ===\n");

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
  console.log(`Total proof attempts: ${config.total_proofs}\n`);

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

  console.log("\n" + "=".repeat(60));
  console.log("FINAL SUMMARY");
  console.log("=".repeat(60));
  console.log(`Total attempts: ${results.summary.total_attempts}`);
  console.log(`Proofs generated: ${results.summary.proofs_generated}`);
  console.log(`Proofs verified: ${results.summary.proofs_verified}`);
  console.log(`Correctly rejected: ${results.summary.correctly_rejected}`);
  console.log(`Unexpected failures: ${results.summary.unexpected_failures}`);
  console.log(`Accuracy: ${accuracy.toFixed(2)}%`);
  console.log(`\nTiming:`);
  console.log(`  Total time: ${totalTime.toFixed(1)}s`);
  console.log(`  Proofs/second: ${results.summary.timing.proofs_per_second.toFixed(2)}`);
  console.log(`  Gen mean: ${results.summary.timing.gen_mean_ms.toFixed(1)}ms`);
  console.log(`  Gen p95: ${results.summary.timing.gen_p95_ms.toFixed(1)}ms`);
  console.log(`  Ver mean: ${results.summary.timing.ver_mean_ms.toFixed(1)}ms`);

  const outputPath = path.join(__dirname, "bridge_scale_output.json");
  fs.writeFileSync(outputPath, JSON.stringify(results, null, 2));
  console.log(`\nResults written to ${outputPath}`);

  process.exit(results.summary.accuracy === 100 ? 0 : 1);
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
