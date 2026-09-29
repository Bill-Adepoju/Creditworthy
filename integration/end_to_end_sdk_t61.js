/**
 * T61: Complete Integration Flow with Proper Decomposition
 *
 * FIXES from T57:
 * 1. Properly executes repayment_record for ALL approved flows
 * 2. Separate error handling for proof vs ledger failures
 * 3. Relabels proofs_succeeded to distinguish:
 *    - proofs_generated: all successful proof generations
 *    - approved_threshold: proofs where band >= lender threshold
 *    - rejected_threshold: proofs where band < lender threshold
 * 4. Reports PER-DECISION means as headline (not batch totals)
 * 5. Excludes cold-start proof from statistics
 */

const { connect, signers } = require('@hyperledger/fabric-gateway');
const grpc = require('@grpc/grpc-js');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const snarkjs = require('snarkjs');
const circomlibjs = require('circomlibjs');

// Paths
const RESULTS_DIR = path.join(__dirname, '..', 'results');
const CIRCUITS_DIR = path.join(__dirname, '..', 'circuits');
const BUILD_DIR = path.join(CIRCUITS_DIR, 'build');
const DATA_DIR = path.join(__dirname, '..', 'data');
const CHAIN_DIR = path.join(__dirname, '..', 'chain');

// Circuit artifacts
const WASM_BANDED = path.join(BUILD_DIR, 'credit_threshold_banded_js', 'credit_threshold_banded.wasm');
const ZKEY_BANDED = path.join(BUILD_DIR, 'ctb_final.zkey');
const VKEY_BANDED = JSON.parse(fs.readFileSync(path.join(BUILD_DIR, 'ctb_verification_key.json')));

// Fabric config
const CONFIG = {
    channelName: 'creditchannel',
    chaincodeName: 'credit',
    mspId: 'CommercialBankAMSP',
    cryptoPath: path.join(CHAIN_DIR, 'config', 'crypto-config'),
    peerEndpoint: 'localhost:7051',
    peerHostAlias: 'peer0.commercialbanka.credit.ng'
};

// Threshold bands
const BANDS = [400, 550, 700, 850];
const NUM_BORROWERS = 25;
const LENDER_THRESHOLD = 550;

// Load model coefficients
const MODEL_COEFFS = JSON.parse(fs.readFileSync(path.join(RESULTS_DIR, 'lr_model_coefficients.json')));

// Timing utilities
function timeMs(start) {
    return Number(process.hrtime.bigint() - start) / 1_000_000;
}

// Gateway SDK connection
async function createGrpcConnection() {
    const tlsCertPath = path.join(
        CONFIG.cryptoPath,
        'peerOrganizations/commercialbanka.credit.ng/peers/peer0.commercialbanka.credit.ng/tls/ca.crt'
    );
    const tlsCert = fs.readFileSync(tlsCertPath);
    const credentials = grpc.credentials.createSsl(tlsCert);

    return new grpc.Client(
        CONFIG.peerEndpoint,
        credentials,
        {
            'grpc.ssl_target_name_override': CONFIG.peerHostAlias,
            'grpc.keepalive_time_ms': 120000,
            'grpc.http2.min_time_between_pings_ms': 120000,
            'grpc.keepalive_timeout_ms': 20000,
            'grpc.http2.max_pings_without_data': 0,
            'grpc.keepalive_permit_without_calls': 1,
        }
    );
}

function createIdentity() {
    const certPath = path.join(
        CONFIG.cryptoPath,
        'peerOrganizations/commercialbanka.credit.ng/users/User1@commercialbanka.credit.ng/msp/signcerts/User1@commercialbanka.credit.ng-cert.pem'
    );
    const credentials = fs.readFileSync(certPath);
    return { mspId: CONFIG.mspId, credentials };
}

function createSigner() {
    const keyPath = path.join(
        CONFIG.cryptoPath,
        'peerOrganizations/commercialbanka.credit.ng/users/User1@commercialbanka.credit.ng/msp/keystore/priv_sk'
    );
    const privateKeyPem = fs.readFileSync(keyPath);
    const privateKey = crypto.createPrivateKey(privateKeyPem);
    return signers.newPrivateKeySigner(privateKey);
}

// STAGE 1: Consent
function runConsent(borrowerId) {
    const t0 = process.hrtime.bigint();
    const consent = {
        borrower_id: borrowerId,
        timestamp: new Date().toISOString(),
        consent_given: true,
        data_categories: ['credit_history', 'loan_performance', 'identity'],
        expires: new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString()
    };
    const hash = crypto.createHash('sha256').update(JSON.stringify(consent)).digest('hex');
    return { consent, hash, latencyMs: timeMs(t0) };
}

// STAGE 2: Feature Engineering
function runFeatureEngineering(rawRecord) {
    const t0 = process.hrtime.bigint();
    const features = {
        repay_delay_mean: rawRecord.repay_delay_mean || 0,
        repay_delay_std: rawRecord.repay_delay_std || 0,
        early_repay_ratio: rawRecord.early_repay_ratio || 0,
        loan_count: rawRecord.loan_count || 1,
        relationship_tenure_days: rawRecord.relationship_tenure_days || 30,
        interval_regularity: rawRecord.interval_regularity || 0,
        interval_mean: rawRecord.interval_mean || 0,
        term_escalation: rawRecord.term_escalation || 0,
        amount_mean: rawRecord.amount_mean || 0,
        amount_max: rawRecord.amount_max || 0,
        amount_total: rawRecord.amount_total || 0,
        amount_cv: rawRecord.amount_cv || 0,
        totaldue_mean: rawRecord.totaldue_mean || 0,
        term_mean: rawRecord.term_mean || 0,
        age: rawRecord.age || 30,
        bank_account_type_Current: rawRecord.bank_account_type_Current || false,
        bank_account_type_Other: rawRecord.bank_account_type_Other || false,
        bank_account_type_Savings: rawRecord.bank_account_type_Savings || true,
        bank_account_type_Unknown: rawRecord.bank_account_type_Unknown || false,
        employment_status_Contract: rawRecord.employment_status_Contract || false,
        employment_status_Permanent: rawRecord.employment_status_Permanent || true,
        employment_status_Retired: rawRecord.employment_status_Retired || false,
        'employment_status_Self-Employed': rawRecord['employment_status_Self-Employed'] || false,
        employment_status_Student: rawRecord.employment_status_Student || false,
        employment_status_Unemployed: rawRecord.employment_status_Unemployed || false,
        employment_status_Unknown: rawRecord.employment_status_Unknown || false,
        region_lat_band_Middle: rawRecord.region_lat_band_Middle || false,
        region_lat_band_North: rawRecord.region_lat_band_North || false,
        'region_lat_band_North-Central': rawRecord['region_lat_band_North-Central'] || false,
        region_lat_band_South: rawRecord.region_lat_band_South || false,
        region_lat_band_Unknown: rawRecord.region_lat_band_Unknown || false,
        region_lat_band_nan: rawRecord.region_lat_band_nan || false
    };
    return { features, latencyMs: timeMs(t0) };
}

// STAGE 3: ML Inference (REAL)
function runMLInference(features) {
    const t0 = process.hrtime.bigint();
    const featureVector = MODEL_COEFFS.feature_names.map(name => {
        let val = features[name];
        if (val === true) val = 1;
        if (val === false) val = 0;
        if (val === undefined || val === null || isNaN(val)) val = 0;
        return val;
    });

    const scaledVector = featureVector.map((val, i) => {
        return (val - MODEL_COEFFS.scaler_mean[i]) / MODEL_COEFFS.scaler_scale[i];
    });

    let logit = MODEL_COEFFS.intercept;
    for (let i = 0; i < scaledVector.length; i++) {
        logit += MODEL_COEFFS.coefficients[i] * scaledVector[i];
    }

    const pDefault = 1 / (1 + Math.exp(-logit));
    const score = Math.round(1000 * (1 - pDefault));

    return { score, pDefault, latencyMs: timeMs(t0) };
}

// Get band threshold
function getBandForScore(score) {
    for (let i = BANDS.length - 1; i >= 0; i--) {
        if (score >= BANDS[i]) return BANDS[i];
    }
    return null;
}

function generateDID(borrowerId) {
    return `did:credit:t61_${borrowerId}_${Date.now()}`;
}

function generateSalt() {
    return Math.floor(Math.random() * (2**30));
}

function loadTestBorrowers() {
    const canonical = JSON.parse(fs.readFileSync(path.join(RESULTS_DIR, 'canonical_split.json')));
    const testIndices = canonical.indices.test;
    const featuresPath = path.join(DATA_DIR, 'features_processed.csv');
    const lines = fs.readFileSync(featuresPath, 'utf8').trim().split('\n');
    const headers = lines[0].split(',');
    const sampleIndices = testIndices.slice(0, NUM_BORROWERS);
    const borrowers = [];

    for (const idx of sampleIndices) {
        const rowIdx = idx + 1;
        if (rowIdx < lines.length) {
            const values = lines[rowIdx].split(',');
            const record = {};
            headers.forEach((h, i) => {
                let val = values[i];
                if (val === 'True') val = true;
                else if (val === 'False') val = false;
                else if (!isNaN(val) && val !== '') val = parseFloat(val);
                record[h] = val;
            });
            borrowers.push({ rawRecord: record, index: idx });
        }
    }
    return borrowers;
}

async function main() {
    console.log('='.repeat(70));
    console.log('T61: Complete Integration Flow with Proper Decomposition');
    console.log('='.repeat(70));
    console.log('');
    console.log('Configuration:');
    console.log('  - ML Model: LogisticRegression (real coefficients)');
    console.log('  - BatchTimeout: 200ms');
    console.log('  - Bands: [400, 550, 700, 850]');
    console.log('  - Lender threshold: 550');
    console.log('');

    const results = {
        timestamp: new Date().toISOString(),
        task: 'T61',
        title: 'Complete Integration Flow with Proper Decomposition',
        configuration: {
            ml_model: 'LogisticRegression (real coefficients)',
            n_features: MODEL_COEFFS.feature_names.length,
            batch_timeout: '200ms',
            bands: BANDS,
            lender_threshold: LENDER_THRESHOLD,
            num_borrowers: NUM_BORROWERS,
            warmup_runs: 5
        },
        flows: [],
        stage_latencies: {
            consent: [],
            feature_engineering: [],
            ml_inference: [],
            commitment: [],
            ledger_anchor: [],
            loan_query: [],
            proof_generation: [],
            proof_verification: [],
            repayment_record: []
        },
        summary: {}
    };

    // Counters
    let belowBandCount = 0;
    let proofsGenerated = 0;
    let approvedCount = 0;
    let rejectedThresholdCount = 0;
    let repaymentRecorded = 0;
    let coldStartProofMs = null;

    try {
        console.log('Connecting to Fabric Gateway...');
        const client = await createGrpcConnection();
        const identity = createIdentity();
        const signer = createSigner();

        const gateway = connect({
            client, identity, signer,
            evaluateOptions: () => ({ deadline: Date.now() + 30000 }),
            endorseOptions: () => ({ deadline: Date.now() + 30000 }),
            submitOptions: () => ({ deadline: Date.now() + 30000 }),
            commitStatusOptions: () => ({ deadline: Date.now() + 120000 }),
        });

        const network = gateway.getNetwork(CONFIG.channelName);
        const contract = network.getContract(CONFIG.chaincodeName);
        console.log('Connected!\n');

        console.log('Initializing Poseidon hasher...');
        const poseidon = await circomlibjs.buildPoseidon();
        console.log('Poseidon ready.\n');

        console.log('Loading test borrowers...');
        const borrowers = loadTestBorrowers();
        console.log(`Loaded ${borrowers.length} borrowers.\n`);

        // Warmup
        console.log('Running warmup (5 transactions)...');
        for (let i = 0; i < 5; i++) {
            const did = generateDID(`warmup_${i}`);
            const hash = '0x' + crypto.randomBytes(32).toString('hex');
            await contract.submitTransaction('AnchorCommitment', hash, did, 'warmup');
        }
        console.log('Warmup complete.\n');

        // Process borrowers
        for (let i = 0; i < borrowers.length; i++) {
            const borrower = borrowers[i];
            const borrowerId = borrower.rawRecord.customerid || `borrower_${i}`;
            console.log(`\nFlow ${i + 1}/${borrowers.length}: ${borrowerId.substring(0, 20)}...`);

            const flowResult = { borrower_id: borrowerId, stages: [] };

            // STAGE 1: Consent
            const consentResult = runConsent(borrowerId);
            results.stage_latencies.consent.push(consentResult.latencyMs);
            flowResult.stages.push({ name: 'consent', latency_ms: consentResult.latencyMs, status: 'complete' });

            // STAGE 2: Feature Engineering
            const feResult = runFeatureEngineering(borrower.rawRecord);
            results.stage_latencies.feature_engineering.push(feResult.latencyMs);
            flowResult.stages.push({ name: 'feature_engineering', latency_ms: feResult.latencyMs, status: 'complete' });

            // STAGE 3: ML Inference
            const mlResult = runMLInference(feResult.features);
            results.stage_latencies.ml_inference.push(mlResult.latencyMs);
            flowResult.stages.push({ name: 'ml_inference', latency_ms: mlResult.latencyMs, score: mlResult.score, status: 'complete' });

            flowResult.score = mlResult.score;
            flowResult.p_default = mlResult.pDefault;

            const bandThreshold = getBandForScore(mlResult.score);
            flowResult.band = bandThreshold;

            if (!bandThreshold) {
                console.log(`  Score ${mlResult.score} < 400: below lowest band`);
                belowBandCount++;
                flowResult.outcome = 'below_lowest_band';
                flowResult.proof_possible = false;
                results.flows.push(flowResult);
                continue;
            }

            // STAGE 4: Commitment
            let t0 = process.hrtime.bigint();
            const salt = generateSalt();
            const did = generateDID(borrowerId);
            const poseidonHash = poseidon.F.toString(poseidon([mlResult.score, salt]));
            const commitmentHex = '0x' + BigInt(poseidonHash).toString(16).padStart(64, '0');
            const commitLatency = timeMs(t0);
            results.stage_latencies.commitment.push(commitLatency);
            flowResult.stages.push({ name: 'commitment', latency_ms: commitLatency, status: 'complete' });

            // STAGE 5: Ledger anchor
            t0 = process.hrtime.bigint();
            await contract.submitTransaction('AnchorCommitment', commitmentHex, did, 'model_v1');
            const anchorLatency = timeMs(t0);
            results.stage_latencies.ledger_anchor.push(anchorLatency);
            flowResult.stages.push({ name: 'ledger_anchor', latency_ms: anchorLatency, status: 'complete' });

            // STAGE 6: Loan query
            t0 = process.hrtime.bigint();
            await contract.evaluateTransaction('GetCommitment', did);
            const queryLatency = timeMs(t0);
            results.stage_latencies.loan_query.push(queryLatency);
            flowResult.stages.push({ name: 'loan_query', latency_ms: queryLatency, status: 'complete' });

            // STAGE 7: Proof generation (separate try/catch)
            t0 = process.hrtime.bigint();
            let proof, publicSignals, proofLatency;
            try {
                const proofData = await snarkjs.groth16.fullProve(
                    { score: mlResult.score, salt, threshold: bandThreshold, commitment: poseidonHash },
                    WASM_BANDED, ZKEY_BANDED
                );
                proof = proofData.proof;
                publicSignals = proofData.publicSignals;
                proofLatency = timeMs(t0);

                // Track cold-start
                if (proofsGenerated === 0) {
                    coldStartProofMs = proofLatency;
                    console.log(`  Proof gen (COLD START, excluded from stats): ${proofLatency.toFixed(1)}ms`);
                } else {
                    results.stage_latencies.proof_generation.push(proofLatency);
                    console.log(`  Proof gen: ${proofLatency.toFixed(1)}ms`);
                }
                proofsGenerated++;
                flowResult.stages.push({ name: 'proof_generation', latency_ms: proofLatency, status: 'success', is_cold_start: proofsGenerated === 1 });

            } catch (err) {
                proofLatency = timeMs(t0);
                flowResult.stages.push({ name: 'proof_generation', latency_ms: proofLatency, status: 'failed', error: err.message });
                flowResult.outcome = 'proof_generation_failed';
                console.log(`  Proof gen FAILED: ${err.message}`);
                results.flows.push(flowResult);
                continue;
            }

            // STAGE 8: Proof verification
            t0 = process.hrtime.bigint();
            const isValid = await snarkjs.groth16.verify(VKEY_BANDED, publicSignals, proof);
            const verifyLatency = timeMs(t0);
            results.stage_latencies.proof_verification.push(verifyLatency);
            flowResult.stages.push({ name: 'proof_verification', latency_ms: verifyLatency, valid: isValid, status: 'complete' });
            console.log(`  Proof verify: ${verifyLatency.toFixed(1)}ms (valid=${isValid})`);

            flowResult.proof_valid = isValid;

            // Decision
            const approved = isValid && bandThreshold >= LENDER_THRESHOLD;
            flowResult.decision = approved ? 'APPROVED' : 'REJECTED';

            if (!approved) {
                flowResult.outcome = 'rejected_threshold';
                rejectedThresholdCount++;
                console.log(`  Decision: REJECTED (band ${bandThreshold} < threshold ${LENDER_THRESHOLD})`);
                results.flows.push(flowResult);
                continue;
            }

            approvedCount++;
            console.log(`  Decision: APPROVED`);

            // STAGE 9: Repayment record (separate try/catch for ledger operation)
            t0 = process.hrtime.bigint();
            try {
                // RecordLoanEvent(did, eventType, proofHash, thresholdUsed)
                await contract.submitTransaction('RecordLoanEvent', did, 'repayment', '0x0', String(bandThreshold));
                const repayLatency = timeMs(t0);
                results.stage_latencies.repayment_record.push(repayLatency);
                flowResult.stages.push({ name: 'repayment_record', latency_ms: repayLatency, status: 'complete' });
                flowResult.outcome = 'approved_and_recorded';
                repaymentRecorded++;
                console.log(`  Repayment recorded: ${repayLatency.toFixed(1)}ms`);
            } catch (err) {
                const repayLatency = timeMs(t0);
                flowResult.stages.push({ name: 'repayment_record', latency_ms: repayLatency, status: 'failed', error: err.message });
                flowResult.outcome = 'approved_repayment_failed';
                console.log(`  Repayment FAILED: ${err.message}`);
            }

            results.flows.push(flowResult);
        }

        gateway.close();
        client.close();

        // Calculate statistics
        const calcStats = (arr) => {
            if (!arr.length) return { n: 0, mean: 0, p50: 0, p95: 0 };
            const sorted = [...arr].sort((a, b) => a - b);
            const sum = sorted.reduce((a, b) => a + b, 0);
            return {
                n: arr.length,
                mean: sum / arr.length,
                p50: sorted[Math.floor(arr.length * 0.5)],
                p95: sorted[Math.floor(arr.length * 0.95)]
            };
        };

        // Per-decision means (the headline)
        const completedFlows = results.flows.filter(f => f.outcome !== 'below_lowest_band');
        const nCompleteFlows = completedFlows.length;

        // Component totals as per-decision averages
        const l1_stages = ['consent', 'feature_engineering', 'ml_inference', 'commitment'];
        const l2_stages = ['ledger_anchor', 'loan_query', 'repayment_record'];
        const l3_stages = ['proof_generation', 'proof_verification'];

        const meanOf = (arr) => arr.length ? arr.reduce((a,b)=>a+b,0)/arr.length : 0;

        const l1_mean = l1_stages.reduce((sum, s) => sum + meanOf(results.stage_latencies[s]), 0);
        const l2_mean = l2_stages.reduce((sum, s) => sum + meanOf(results.stage_latencies[s]), 0);
        const l3_mean = l3_stages.reduce((sum, s) => sum + meanOf(results.stage_latencies[s]), 0);
        const total_mean = l1_mean + l2_mean + l3_mean;

        results.summary = {
            flows_processed: results.flows.length,
            below_lowest_band: belowBandCount,
            proofs_generated: proofsGenerated,
            approved_threshold: approvedCount,
            rejected_threshold: rejectedThresholdCount,
            repayments_recorded: repaymentRecorded,
            cold_start_proof_ms: coldStartProofMs,
            cold_start_excluded: true,

            stage_statistics: {},

            per_decision_latency: {
                description: 'Mean latency per completed credit decision (excluding below-band flows)',
                n_decisions: nCompleteFlows,
                L1_ML_scoring_ms: l1_mean.toFixed(2),
                L2_blockchain_ms: l2_mean.toFixed(2),
                L3_ZK_proofs_ms: l3_mean.toFixed(2),
                total_ms: total_mean.toFixed(2),
                L1_pct: ((l1_mean / total_mean) * 100).toFixed(1) + '%',
                L2_pct: ((l2_mean / total_mean) * 100).toFixed(1) + '%',
                L3_pct: ((l3_mean / total_mean) * 100).toFixed(1) + '%'
            },

            key_finding: `A complete credit decision takes ${total_mean.toFixed(0)} ms on average. L2 (blockchain) is ${((l2_mean / total_mean) * 100).toFixed(0)}%, L3 (ZK) is ${((l3_mean / total_mean) * 100).toFixed(0)}%. Cryptographic privacy costs ${((l3_mean / total_mean) * 100).toFixed(0)}% of decision latency.`,

            t57_corrections: [
                'repayment_record now executes for all approved flows',
                'proofs_succeeded relabeled to proofs_generated + approved_threshold + rejected_threshold',
                'cold-start proof excluded from statistics',
                'per-decision means reported as headline (not batch totals)'
            ]
        };

        // Per-stage statistics
        for (const [stage, latencies] of Object.entries(results.stage_latencies)) {
            results.summary.stage_statistics[stage] = calcStats(latencies);
        }

        // Print summary
        console.log('\n' + '='.repeat(70));
        console.log('SUMMARY');
        console.log('='.repeat(70));
        console.log(`\nFlows: ${results.flows.length}`);
        console.log(`  Below lowest band: ${belowBandCount}`);
        console.log(`  Proofs generated: ${proofsGenerated} (cold-start excluded from stats)`);
        console.log(`  Approved (band >= ${LENDER_THRESHOLD}): ${approvedCount}`);
        console.log(`  Rejected (band < ${LENDER_THRESHOLD}): ${rejectedThresholdCount}`);
        console.log(`  Repayments recorded: ${repaymentRecorded}`);

        console.log('\nPER-DECISION LATENCY (the headline):');
        console.log(`  L1 (ML): ${l1_mean.toFixed(2)} ms (${results.summary.per_decision_latency.L1_pct})`);
        console.log(`  L2 (Blockchain): ${l2_mean.toFixed(2)} ms (${results.summary.per_decision_latency.L2_pct})`);
        console.log(`  L3 (ZK): ${l3_mean.toFixed(2)} ms (${results.summary.per_decision_latency.L3_pct})`);
        console.log(`  TOTAL: ${total_mean.toFixed(2)} ms per decision`);

        console.log(`\nKey finding: ${results.summary.key_finding}`);

    } catch (error) {
        console.error('Demo failed:', error);
        results.error = error.message;
    }

    const outPath = path.join(RESULTS_DIR, 'integration_demo_t61.json');
    fs.writeFileSync(outPath, JSON.stringify(results, null, 2));
    console.log(`\nResults saved to: ${outPath}`);
}

main().catch(console.error);
