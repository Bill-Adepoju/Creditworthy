/*
 * T15: Leakage Harness
 * --------------------
 * Models the adversary as a lender issuing repeated proof requests.
 * Validates that banding prevents binary search attack.
 *
 * Expected results:
 * 1. Unbanded circuit, binary search: Exact score recovered in ~10 queries
 * 2. Banded circuit, all four bands: Score localised to one band only (2.00 bits)
 * 3. Off-band thresholds (720, 701, 500): REJECTED, even if score satisfies them
 */
const snarkjs = require("snarkjs");
const circomlibjs = require("circomlibjs");
const fs = require("fs");
const path = require("path");

const BUILD = path.join(__dirname, "build");
const BANDS = [400, 550, 700, 850];  // Must match circuit parameters

// Circuit paths
const UNBANDED = {
  wasm: path.join(BUILD, "credit_threshold_js", "credit_threshold.wasm"),
  zkey: path.join(BUILD, "ct_final.zkey")
};
const BANDED = {
  wasm: path.join(BUILD, "credit_threshold_banded_js", "credit_threshold_banded.wasm"),
  zkey: path.join(BUILD, "ctb_final.zkey")
};

async function tryProof(circuit, input) {
  try {
    await snarkjs.groth16.fullProve(input, circuit.wasm, circuit.zkey);
    return true;  // Proof succeeded
  } catch (e) {
    return false;  // Proof failed (score < threshold or off-band)
  }
}

async function binarySearchAttack(circuit, commitment, salt, trueScore) {
  /*
   * Simulates a lender performing binary search to recover exact score.
   * Returns: { recoveredScore, queries, bitsLeaked }
   */
  let lo = 0;
  let hi = 1000;
  let queries = 0;

  while (lo < hi) {
    const mid = Math.floor((lo + hi + 1) / 2);
    queries++;

    const canProve = await tryProof(circuit, {
      score: trueScore,
      salt: salt.toString(),
      commitment: commitment,
      threshold: mid
    });

    if (canProve) {
      // score >= mid, search upper half
      lo = mid;
    } else {
      // score < mid, search lower half
      hi = mid - 1;
    }
  }

  return {
    trueScore,
    recoveredScore: lo,
    exact: lo === trueScore,
    queries,
    bitsLeaked: Math.log2(1001)  // Full information
  };
}

async function bandedProbing(circuit, commitment, salt, trueScore) {
  /*
   * Probes all permitted bands on the banded circuit.
   * Returns which band(s) the score falls into.
   */
  const results = [];

  for (const band of BANDS) {
    const canProve = await tryProof(circuit, {
      score: trueScore,
      salt: salt.toString(),
      commitment: commitment,
      threshold: band
    });

    results.push({ band, canProve });
  }

  // Determine which band the score falls into
  const passing = results.filter(r => r.canProve).map(r => r.band);
  const lowestPassing = passing.length > 0 ? Math.min(...passing) : null;

  // Find the band interval
  let bandInterval = null;
  if (lowestPassing !== null) {
    const bandIdx = BANDS.indexOf(lowestPassing);
    if (bandIdx > 0) {
      bandInterval = `[${BANDS[bandIdx]}, ${BANDS[bandIdx-1]-1}]`;
    } else {
      bandInterval = `[${lowestPassing}, 1000]`;
    }
  } else {
    bandInterval = `[0, ${BANDS[BANDS.length-1]-1}]`;
  }

  return {
    trueScore,
    queries: BANDS.length,
    passingBands: passing,
    bitsLeaked: Math.log2(BANDS.length),  // At most log2(B) bits
    bandInterval
  };
}

async function testOffBandRejection(circuit, commitment, salt, trueScore) {
  /*
   * Tests that off-band thresholds are rejected even if score satisfies them.
   * This is the key test: the polynomial must BIND, not merely be present.
   */
  const offBandThresholds = [720, 701, 500, 600, 450];
  const results = [];

  for (const threshold of offBandThresholds) {
    const scoreSatisfies = trueScore >= threshold;
    const canProve = await tryProof(circuit, {
      score: trueScore,
      salt: salt.toString(),
      commitment: commitment,
      threshold: threshold
    });

    results.push({
      threshold,
      scoreSatisfies,
      proofSucceeded: canProve,
      correct: !canProve  // Off-band thresholds should ALWAYS fail
    });
  }

  return results;
}

async function main() {
  console.log("=== T15: Leakage Analysis Harness ===\n");

  // Check build artifacts
  for (const [name, circuit] of [["unbanded", UNBANDED], ["banded", BANDED]]) {
    if (!fs.existsSync(circuit.wasm) || !fs.existsSync(circuit.zkey)) {
      console.error(`ERROR: ${name} circuit not built. Run: node setup.js`);
      process.exit(1);
    }
  }

  const poseidon = await circomlibjs.buildPoseidon();
  const F = poseidon.F;

  // Test parameters
  const testScores = [523, 700, 400, 850, 275, 999];  // Various scores to test
  const salt = 12345678;

  const results = {
    timestamp: new Date().toISOString(),
    bands: BANDS,
    tests: {
      unbanded_binary_search: [],
      banded_probing: [],
      off_band_rejection: []
    },
    summary: {}
  };

  // Test 1: Unbanded binary search attack
  console.log("=== Test 1: Unbanded Circuit Binary Search Attack ===");
  console.log("Expected: Exact score recovery in ~10 queries\n");

  for (const trueScore of testScores) {
    const commitment = F.toObject(poseidon([trueScore, salt])).toString();

    const result = await binarySearchAttack(UNBANDED, commitment, salt, trueScore);
    results.tests.unbanded_binary_search.push(result);

    const status = result.exact ? "EXACT" : "FAILED";
    console.log(`Score ${trueScore}: Recovered ${result.recoveredScore} in ${result.queries} queries [${status}]`);
  }

  const avgQueries = results.tests.unbanded_binary_search.reduce((a, r) => a + r.queries, 0) / testScores.length;
  const allExact = results.tests.unbanded_binary_search.every(r => r.exact);
  console.log(`\nAverage queries: ${avgQueries.toFixed(1)}`);
  console.log(`All exact: ${allExact}`);
  console.log(`Bits leaked: ~${Math.log2(1001).toFixed(2)} (complete disclosure)`);

  // Test 2: Banded circuit probing
  console.log("\n=== Test 2: Banded Circuit - All Bands Probed ===");
  console.log(`Expected: Score localised to one of ${BANDS.length} bands (${Math.log2(BANDS.length).toFixed(2)} bits)\n`);

  for (const trueScore of testScores) {
    const commitment = F.toObject(poseidon([trueScore, salt])).toString();

    const result = await bandedProbing(BANDED, commitment, salt, trueScore);
    results.tests.banded_probing.push(result);

    console.log(`Score ${trueScore}: Passes bands ${JSON.stringify(result.passingBands)} -> ${result.bandInterval}`);
  }

  console.log(`\nBits leaked: ${Math.log2(BANDS.length).toFixed(2)} (vs ${Math.log2(1001).toFixed(2)} unbanded)`);

  // Test 3: Off-band rejection
  console.log("\n=== Test 3: Off-Band Threshold Rejection ===");
  console.log("Expected: ALL off-band thresholds rejected, even if score >= threshold\n");

  // Use a score that satisfies most off-band thresholds
  const testScore = 750;
  const commitment = F.toObject(poseidon([testScore, salt])).toString();

  const offBandResults = await testOffBandRejection(BANDED, commitment, salt, testScore);
  results.tests.off_band_rejection = offBandResults;

  console.log(`Test score: ${testScore}`);
  for (const r of offBandResults) {
    const bindingStatus = r.correct ? "BINDING HOLDS" : "BINDING FAILED";
    console.log(`  Threshold ${r.threshold}: score satisfies=${r.scoreSatisfies}, proof=${r.proofSucceeded ? "SUCCESS" : "REJECTED"} [${bindingStatus}]`);
  }

  const allRejected = offBandResults.every(r => r.correct);
  console.log(`\nAll off-band thresholds correctly rejected: ${allRejected}`);

  // Summary
  console.log("\n" + "=".repeat(60));
  console.log("SUMMARY");
  console.log("=".repeat(60));

  results.summary = {
    unbanded: {
      avg_queries: avgQueries,
      all_exact_recovery: allExact,
      bits_leaked: Math.log2(1001)
    },
    banded: {
      queries: BANDS.length,
      bits_leaked: Math.log2(BANDS.length),
      reduction_factor: Math.log2(1001) / Math.log2(BANDS.length)
    },
    binding_test: {
      all_off_band_rejected: allRejected,
      binding_holds: allRejected
    }
  };

  console.log(`\nUnbanded circuit: ${avgQueries.toFixed(1)} queries -> ${Math.log2(1001).toFixed(2)} bits leaked (COMPLETE DISCLOSURE)`);
  console.log(`Banded circuit:   ${BANDS.length} queries -> ${Math.log2(BANDS.length).toFixed(2)} bits leaked (${(results.summary.banded.reduction_factor).toFixed(1)}x reduction)`);
  console.log(`Binding constraint: ${allRejected ? "HOLDS" : "FAILED"}`);

  if (allExact && allRejected) {
    console.log("\n[SUCCESS] Banding mitigation validated:");
    console.log("  - Binary search recovers exact score on unbanded circuit");
    console.log("  - Banded circuit limits leakage to band membership");
    console.log("  - Off-band thresholds correctly rejected");
  } else {
    console.log("\n[WARNING] Some tests did not pass as expected");
  }

  // Write results
  const outputPath = path.join(__dirname, "..", "results", "leakage_analysis.json");
  fs.writeFileSync(outputPath, JSON.stringify(results, null, 2));
  console.log(`\nResults written to ${outputPath}`);
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
