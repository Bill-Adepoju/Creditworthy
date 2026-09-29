/*
 * Cross-platform setup for the ZK threshold-verification layer.
 * Compiles BOTH unbanded and banded circuits, caching the phase-1 ceremony.
 *
 * Requires: node >= 18, circom installed globally or in PATH
 *
 * On Windows: Install circom via cargo (requires Rust):
 *   cargo install --git https://github.com/iden3/circom.git
 *
 * Or download from: https://github.com/iden3/circom/releases
 */
const { execSync, spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const CIRCUITS = [
  { name: "credit_threshold", file: "credit_threshold.circom", prefix: "ct" },
  { name: "credit_threshold_banded", file: "credit_threshold_banded.circom", prefix: "ctb" }
];

const BUILD = path.join(__dirname, "build");
const CIRCOM = path.join(__dirname, "..", "bin", "circom.exe");

function run(cmd, opts = {}) {
  console.log(`> ${cmd}`);
  try {
    execSync(cmd, { stdio: "inherit", cwd: opts.cwd || __dirname, ...opts });
  } catch (e) {
    console.error(`Command failed: ${cmd}`);
    process.exit(1);
  }
}

function checkCircom() {
  // First check local binary
  if (fs.existsSync(CIRCOM)) {
    try {
      const result = spawnSync(CIRCOM, ["--version"], { encoding: "utf8" });
      if (result.status === 0) {
        console.log(`Found local circom: ${result.stdout.trim()}`);
        return CIRCOM;
      }
    } catch (e) {}
  }
  // Then check PATH
  try {
    const result = spawnSync("circom", ["--version"], { encoding: "utf8" });
    if (result.status === 0) {
      console.log(`Found circom in PATH: ${result.stdout.trim()}`);
      return "circom";
    }
  } catch (e) {}
  return null;
}

async function main() {
  console.log("=== ZK Credit Threshold Setup (Unbanded + Banded) ===\n");

  // Check circom is available
  const circomPath = checkCircom();
  if (!circomPath) {
    console.error("ERROR: circom not found");
    console.error("\nInstall circom:");
    console.error("  Option 1 (Rust): cargo install --git https://github.com/iden3/circom.git");
    console.error("  Option 2: Download from https://github.com/iden3/circom/releases");
    console.error("            and add to PATH or place in ../bin/circom.exe");
    process.exit(1);
  }

  // Ensure deps installed
  const nodeModules = path.join(__dirname, "..", "node_modules");
  if (!fs.existsSync(nodeModules)) {
    console.log("\nInstalling npm dependencies...");
    run("npm install", { cwd: path.join(__dirname, "..") });
  }

  // Create build directory (don't clean if phase1 exists)
  const phase1Cached = fs.existsSync(path.join(BUILD, "pot12_final.ptau"));
  if (!fs.existsSync(BUILD)) {
    fs.mkdirSync(BUILD, { recursive: true });
  }

  // Compile both circuits
  console.log("\n=== Compiling circuits ===");
  for (const circuit of CIRCUITS) {
    console.log(`\nCompiling ${circuit.file}...`);
    run(`"${circomPath}" ${circuit.file} --r1cs --wasm --sym -o build`);
  }

  // Powers of Tau ceremony (phase 1) - cached
  process.env.NODE_OPTIONS = "--max-old-space-size=4096";

  if (phase1Cached) {
    console.log("\n=== Powers of Tau (phase 1) - CACHED ===");
    console.log("Using existing pot12_final.ptau");
  } else {
    console.log("\n=== Powers of Tau ceremony (phase 1) ===");
    run("npx snarkjs powersoftau new bn128 12 pot12_0000.ptau", { cwd: BUILD });
    run('npx snarkjs powersoftau contribute pot12_0000.ptau pot12_0001.ptau --name="contributor1" -e="random entropy string for dissertation"', { cwd: BUILD });
    run("npx snarkjs powersoftau prepare phase2 pot12_0001.ptau pot12_final.ptau", { cwd: BUILD });
  }

  // Circuit-specific setup (phase 2) for each circuit
  const constraintCounts = {};

  for (const circuit of CIRCUITS) {
    console.log(`\n=== Circuit-specific setup for ${circuit.name} (phase 2) ===`);

    const r1cs = `${circuit.name}.r1cs`;
    const zkey0 = `${circuit.prefix}_0000.zkey`;
    const zkeyFinal = `${circuit.prefix}_final.zkey`;
    const vkey = `${circuit.prefix}_verification_key.json`;
    const sol = `${circuit.prefix}_verifier.sol`;

    run(`npx snarkjs groth16 setup ${r1cs} pot12_final.ptau ${zkey0}`, { cwd: BUILD });
    run(`npx snarkjs zkey contribute ${zkey0} ${zkeyFinal} --name="contributor1" -e="circuit specific entropy for ${circuit.name}"`, { cwd: BUILD });
    run(`npx snarkjs zkey export verificationkey ${zkeyFinal} ${vkey}`, { cwd: BUILD });
    run(`npx snarkjs zkey export solidityverifier ${zkeyFinal} ${sol}`, { cwd: BUILD });

    // Get constraint count
    console.log(`\n--- ${circuit.name} statistics ---`);
    const info = execSync(`npx snarkjs r1cs info ${r1cs}`, { cwd: BUILD, encoding: "utf8" });
    console.log(info);

    // Parse constraint count
    const match = info.match(/Constraints:\s*(\d+)/);
    if (match) {
      constraintCounts[circuit.name] = parseInt(match[1]);
    }
  }

  // Report constraint delta
  console.log("\n=== Constraint comparison ===");
  if (constraintCounts["credit_threshold"] && constraintCounts["credit_threshold_banded"]) {
    const unbanded = constraintCounts["credit_threshold"];
    const banded = constraintCounts["credit_threshold_banded"];
    const delta = banded - unbanded;
    console.log(`Unbanded circuit: ${unbanded} constraints`);
    console.log(`Banded circuit:   ${banded} constraints`);
    console.log(`Delta:            ${delta} constraints (${(delta/unbanded*100).toFixed(2)}% increase)`);

    if (delta !== 3) {
      console.log(`\nWARNING: Expected delta of 3 constraints, got ${delta}`);
      console.log("This suggests the polynomial was not factored as intended.");
    }
  }

  console.log("\n=== Setup complete ===");
  console.log("Run benchmarks: node bench.js");
  console.log("Run leakage analysis: node leakage_harness.js");
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
