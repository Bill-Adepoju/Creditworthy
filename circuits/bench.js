/*
 * End-to-end benchmark of the ZK threshold-verification layer.
 *
 * Simulates the flow from Figure 4.1 of the seminar:
 *   ML layer   -> computes score, commits Poseidon(score, salt)
 *   Ledger     -> anchors commitment (here: held in a JS object)
 *   Borrower   -> generates zk-SNARK proof that score >= threshold
 *   Lender     -> verifies proof, learns ONLY the boolean
 */
const snarkjs = require("snarkjs");
const circomlibjs = require("circomlibjs");
const fs = require("fs");
const path = require("path");
const os = require("os");

const B = path.join(__dirname, "build");
const WASM = path.join(B, "credit_threshold_js", "credit_threshold.wasm");
const ZKEY = path.join(B, "ct_final.zkey");
const VKEY_PATH = path.join(B, "verification_key.json");

const now = () => Number(process.hrtime.bigint()) / 1e6; // ms

async function main() {
  // Check build artifacts exist
  if (!fs.existsSync(WASM)) {
    console.error("ERROR: Build artifacts not found. Run setup first.");
    console.error("Expected:", WASM);
    process.exit(1);
  }

  const VKEY = JSON.parse(fs.readFileSync(VKEY_PATH));
  const poseidon = await circomlibjs.buildPoseidon();
  const F = poseidon.F;

  // ---------- ML LAYER: score computed off-chain ----------
  // Score scaled to 0..1000 (16-bit range in circuit)
  const score = 742;
  const salt = 987654321987n; // per-borrower blinding factor
  const commitment = F.toObject(poseidon([score, salt])).toString();

  console.log("=== SIMULATED CREDIT PIPELINE ===");
  console.log("Borrower true score (PRIVATE)   :", score);
  console.log("Commitment anchored on ledger   :", commitment.slice(0, 24) + "...");

  // ---------- LEDGER LAYER: only the commitment is stored ----------
  const ledger = { did: "did:credit:ng:0xA71f", commitment, ts: Date.now() };

  // ---------- BORROWER: prove eligibility at lender's threshold ----------
  const thresholds = [600, 700, 742];
  const results = [];

  for (const threshold of thresholds) {
    const input = { score, salt: salt.toString(), commitment: ledger.commitment, threshold };

    const t0 = now();
    const { proof, publicSignals } = await snarkjs.groth16.fullProve(input, WASM, ZKEY);
    const t1 = now();
    const ok = await snarkjs.groth16.verify(VKEY, publicSignals, proof);
    const t2 = now();

    const proofBytes = Buffer.byteLength(JSON.stringify(proof), "utf8");
    results.push({ threshold, gen: t1 - t0, ver: t2 - t1, bytes: proofBytes, ok });

    console.log(
      `\nthreshold=${threshold}  verified=${ok}` +
      `\n  proof gen   : ${(t1 - t0).toFixed(1)} ms` +
      `\n  verify      : ${(t2 - t1).toFixed(1)} ms` +
      `\n  proof size  : ${proofBytes} bytes` +
      `\n  lender sees : ${JSON.stringify(publicSignals)}  <-- [eligible, commitment, threshold]`
    );
  }

  // ---------- NEGATIVE CASE: ineligible borrower cannot prove ----------
  console.log("\n=== INELIGIBILITY TEST (score 742 vs threshold 800) ===");
  let ineligibilityPass = false;
  try {
    await snarkjs.groth16.fullProve(
      { score, salt: salt.toString(), commitment: ledger.commitment, threshold: 800 },
      WASM, ZKEY
    );
    console.log("FAIL: proof was generated for an ineligible borrower");
  } catch (e) {
    console.log("PASS: proof generation rejected (constraint ge.out === 1 unsatisfiable)");
    ineligibilityPass = true;
  }

  // ---------- FORGERY TEST: wrong score against real commitment ----------
  console.log("\n=== COMMITMENT-BINDING TEST (claim score 950) ===");
  let forgeryPass = false;
  try {
    await snarkjs.groth16.fullProve(
      { score: 950, salt: salt.toString(), commitment: ledger.commitment, threshold: 800 },
      WASM, ZKEY
    );
    console.log("FAIL: forged score accepted");
  } catch (e) {
    console.log("PASS: forged score rejected (Poseidon binding violated)");
    forgeryPass = true;
  }

  // ---------- THROUGHPUT ----------
  console.log("\n=== SUSTAINED THROUGHPUT (20 sequential verifications) ===");
  const inp = { score, salt: salt.toString(), commitment: ledger.commitment, threshold: 600 };
  const gens = [], vers = [];
  for (let i = 0; i < 20; i++) {
    const a = now();
    const { proof, publicSignals } = await snarkjs.groth16.fullProve(inp, WASM, ZKEY);
    const b = now();
    await snarkjs.groth16.verify(VKEY, publicSignals, proof);
    gens.push(b - a);
    vers.push(now() - b);
  }
  const mean = a => a.reduce((x, y) => x + y, 0) / a.length;
  const p95 = a => [...a].sort((x, y) => x - y)[Math.floor(a.length * 0.95)];

  console.log(`  proof gen  mean ${mean(gens).toFixed(1)} ms | p95 ${p95(gens).toFixed(1)} ms`);
  console.log(`  verify     mean ${mean(vers).toFixed(1)} ms | p95 ${p95(vers).toFixed(1)} ms`);
  console.log(`  verifier throughput ~ ${(1000 / mean(vers)).toFixed(0)} proofs/sec/core`);

  // ---------- HARDWARE INFO ----------
  const cpus = os.cpus();
  const hw = {
    cpu: cpus[0]?.model || "unknown",
    cores: cpus.length,
    ram_gb: Math.round(os.totalmem() / (1024 ** 3)),
    platform: os.platform(),
    node_version: process.version
  };
  console.log("\n=== HARDWARE ===");
  console.log(`  CPU     : ${hw.cpu}`);
  console.log(`  Cores   : ${hw.cores}`);
  console.log(`  RAM     : ${hw.ram_gb} GB`);
  console.log(`  Node    : ${hw.node_version}`);

  // ---------- WRITE RESULTS ----------
  const benchResults = {
    timestamp: new Date().toISOString(),
    hardware: hw,
    sanity_checks: {
      ineligibility_rejected: ineligibilityPass,
      forgery_rejected: forgeryPass
    },
    thresholds: results,
    throughput: {
      proof_gen_mean_ms: mean(gens),
      proof_gen_p95_ms: p95(gens),
      verify_mean_ms: mean(vers),
      verify_p95_ms: p95(vers),
      verifier_throughput_per_core: Math.round(1000 / mean(vers))
    },
    library_versions: {
      snarkjs: JSON.parse(fs.readFileSync(require.resolve("snarkjs").replace(/[/\\]build[/\\].*$/, "/package.json"))).version,
      circomlibjs: JSON.parse(fs.readFileSync(path.join(__dirname, "..", "node_modules", "circomlibjs", "package.json"))).version,
      circomlib: JSON.parse(fs.readFileSync(path.join(__dirname, "..", "node_modules", "circomlib", "package.json"))).version
    }
  };

  fs.writeFileSync(path.join(B, "bench_results.json"), JSON.stringify(benchResults, null, 2));
  console.log(`\nResults written to ${path.join(B, "bench_results.json")}`);

  // Also write to /results for the research side
  const resultsDir = path.join(__dirname, "..", "results");
  if (!fs.existsSync(resultsDir)) fs.mkdirSync(resultsDir, { recursive: true });
  fs.writeFileSync(path.join(resultsDir, "zk_baseline.json"), JSON.stringify(benchResults, null, 2));
  console.log(`Results also written to ${path.join(resultsDir, "zk_baseline.json")}`);

  // Check all sanity tests passed
  if (!ineligibilityPass || !forgeryPass) {
    console.error("\n!!! CORRECTNESS REGRESSION: sanity checks failed !!!");
    process.exit(1);
  }

  process.exit(0);
}

main().catch(e => { console.error(e); process.exit(1); });
