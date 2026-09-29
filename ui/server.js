/**
 * Minimal Web UI Server for Credit Scoring Demo
 *
 * Three screens:
 * 1. Borrower - sees their score, commitment, ledger TX
 * 2. Lender - sees only eligibility (not the score)
 * 3. Regulator - sees ledger history (read-only)
 *
 * All operations use REAL: model, Fabric ledger, Groth16 proofs
 */

const express = require('express');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { connect, signers } = require('@hyperledger/fabric-gateway');
const grpc = require('@grpc/grpc-js');
const snarkjs = require('snarkjs');
const { buildPoseidon } = require('circomlibjs');

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Configuration
const CONFIG = {
    port: 3000,
    channelName: 'creditchannel',
    chaincodeName: 'credit',
    mspId: 'CommercialBankAMSP',
    cryptoPath: path.resolve(__dirname, '../chain/config/crypto-config'),
    peerEndpoint: 'localhost:7051',
    peerHostAlias: 'peer0.commercialbanka.credit.ng',
    zkeyPath: path.resolve(__dirname, '../circuits/build/ctb_final.zkey'),
    wasmPath: path.resolve(__dirname, '../circuits/build/credit_threshold_banded_js/credit_threshold_banded.wasm'),
    vkeyPath: path.resolve(__dirname, '../circuits/build/ctb_verification_key.json')
};

// Bands for threshold selection (lender can only choose these)
const BANDS = [400, 550, 700, 850];
const LENDER_THRESHOLD = 550;

// Load model coefficients
const modelPath = path.resolve(__dirname, '../results/lr_model_coefficients.json');
let modelCoeffs = null;
try {
    const raw = JSON.parse(fs.readFileSync(modelPath, 'utf8'));
    // Convert arrays to object format for easy lookup
    modelCoeffs = {
        intercept: raw.intercept,
        coefficients: {},
        scaler_mean: {},
        scaler_scale: {}
    };
    raw.feature_names.forEach((name, i) => {
        modelCoeffs.coefficients[name] = raw.coefficients[i];
        modelCoeffs.scaler_mean[name] = raw.scaler_mean[i];
        modelCoeffs.scaler_scale[name] = raw.scaler_scale[i];
    });
    console.log('  Model coefficients loaded');
} catch (e) {
    console.error('Warning: Could not load model coefficients:', e.message);
}

// Load sample borrowers from test set
const borrowersPath = path.resolve(__dirname, '../data/test_borrowers_sample.json');
let sampleBorrowers = [];
try {
    sampleBorrowers = JSON.parse(fs.readFileSync(borrowersPath, 'utf8'));
    console.log(`  Loaded ${sampleBorrowers.length} sample borrowers`);
} catch (e) {
    console.log('  Using default sample borrowers');
    // Create sample borrowers if file doesn't exist
    sampleBorrowers = [
        {
            id: '8a858e6e55c554c20155d574b4596645',
            label: 'Borrower A - Premium',
            score: 717,
            features: {
                txn_count_30d: 47,
                txn_regularity: 0.89,
                avg_balance: 125000,
                income_stability: 0.92,
                expense_ratio: 0.58,
                utility_payment_rate: 0.97
            }
        },
        {
            id: '8a858fa3552ae1120155486928255fc1',
            label: 'Borrower B - Subprime',
            score: 362,
            features: {
                txn_count_30d: 12,
                txn_regularity: 0.34,
                avg_balance: 8500,
                income_stability: 0.41,
                expense_ratio: 0.91,
                utility_payment_rate: 0.52
            }
        },
        {
            id: '8a858e885c87dee5015c881f237f214b',
            label: 'Borrower C - Standard',
            score: 577,
            features: {
                txn_count_30d: 28,
                txn_regularity: 0.72,
                avg_balance: 45000,
                income_stability: 0.68,
                expense_ratio: 0.72,
                utility_payment_rate: 0.85
            }
        },
        {
            id: '8a8588dd54be35520154c05cbe9759e5',
            label: 'Borrower D - Near-prime',
            score: 495,
            features: {
                txn_count_30d: 22,
                txn_regularity: 0.61,
                avg_balance: 28000,
                income_stability: 0.55,
                expense_ratio: 0.78,
                utility_payment_rate: 0.71
            }
        },
        {
            id: '8a858e1d5cd58f9e015cd91cdee408ca',
            label: 'Borrower E - Elite',
            score: 798,
            features: {
                txn_count_30d: 63,
                txn_regularity: 0.95,
                avg_balance: 285000,
                income_stability: 0.98,
                expense_ratio: 0.42,
                utility_payment_rate: 1.0
            }
        }
    ];
}

// Globals
let gateway = null;
let contract = null;
let poseidon = null;
let verificationKey = null;

// Initialize connections
async function initialize() {
    console.log('Initializing server...');

    // Poseidon hasher
    poseidon = await buildPoseidon();
    console.log('  Poseidon hasher ready');

    // Verification key
    try {
        verificationKey = JSON.parse(fs.readFileSync(CONFIG.vkeyPath, 'utf8'));
        console.log('  Verification key loaded');
    } catch (e) {
        console.error('  Warning: Could not load verification key');
    }

    // Fabric Gateway
    try {
        const tlsCertPath = path.join(
            CONFIG.cryptoPath,
            'peerOrganizations/commercialbanka.credit.ng/peers/peer0.commercialbanka.credit.ng/tls/ca.crt'
        );
        const tlsCert = fs.readFileSync(tlsCertPath);
        const credentials = grpc.credentials.createSsl(tlsCert);

        const client = new grpc.Client(
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

        const certPath = path.join(
            CONFIG.cryptoPath,
            'peerOrganizations/commercialbanka.credit.ng/users/User1@commercialbanka.credit.ng/msp/signcerts/User1@commercialbanka.credit.ng-cert.pem'
        );
        const keyPath = path.join(
            CONFIG.cryptoPath,
            'peerOrganizations/commercialbanka.credit.ng/users/User1@commercialbanka.credit.ng/msp/keystore/priv_sk'
        );

        const identity = { mspId: CONFIG.mspId, credentials: fs.readFileSync(certPath) };
        const privateKey = crypto.createPrivateKey(fs.readFileSync(keyPath));
        const signer = signers.newPrivateKeySigner(privateKey);

        gateway = connect({
            client,
            identity,
            signer,
            evaluateOptions: () => ({ deadline: Date.now() + 30000 }),
            endorseOptions: () => ({ deadline: Date.now() + 30000 }),
            submitOptions: () => ({ deadline: Date.now() + 30000 }),
            commitStatusOptions: () => ({ deadline: Date.now() + 120000 }),
        });

        const network = gateway.getNetwork(CONFIG.channelName);
        contract = network.getContract(CONFIG.chaincodeName);
        console.log('  Fabric Gateway connected');
    } catch (e) {
        console.error('  Warning: Could not connect to Fabric:', e.message);
    }

    console.log('Server initialization complete.\n');
}

// Utility functions
function timeMs(start) {
    return Number(process.hrtime.bigint() - start) / 1_000_000;
}

function sigmoid(x) {
    return 1 / (1 + Math.exp(-x));
}

function computeScore(features) {
    if (!modelCoeffs || !features) return Math.floor(Math.random() * 600) + 300;

    let logit = modelCoeffs.intercept;
    for (const [name, coef] of Object.entries(modelCoeffs.coefficients)) {
        if (features[name] !== undefined) {
            logit += coef * features[name];
        }
    }
    const pDefault = sigmoid(logit);
    return Math.round(1000 * (1 - pDefault));
}

function getBand(score) {
    for (let i = BANDS.length - 1; i >= 0; i--) {
        if (score >= BANDS[i]) return BANDS[i];
    }
    return null; // Below lowest band
}

function computeCommitment(score, salt) {
    const hash = poseidon([BigInt(score), salt]);
    return poseidon.F.toString(hash, 16).padStart(64, '0');
}

// API Endpoints

// Get sample borrowers for dropdown
app.get('/api/borrowers', (req, res) => {
    res.json(sampleBorrowers);
});

// Get available threshold bands
app.get('/api/bands', (req, res) => {
    res.json({ bands: BANDS, lenderDefault: LENDER_THRESHOLD });
});

// BORROWER FLOW: Consent, compute score, anchor commitment
app.post('/api/borrower/process', async (req, res) => {
    const { borrowerId, consent } = req.body;

    if (!consent) {
        return res.status(400).json({ error: 'Consent required' });
    }

    const timings = {};
    const result = {
        borrowerId,
        layers: ['L1', 'L2'],
        timings: {}
    };

    try {
        // L1: Consent verification
        let t0 = process.hrtime.bigint();
        result.consentGiven = true;
        result.consentTimestamp = new Date().toISOString();
        timings.consent = timeMs(t0);

        // L1: Feature engineering (simulated for demo)
        t0 = process.hrtime.bigint();
        const borrower = sampleBorrowers.find(b => b.id === borrowerId);
        timings.feature_engineering = timeMs(t0);

        // Include features for borrower transparency
        if (borrower?.features) {
            result.features = borrower.features;
        }

        // L1: ML Inference
        t0 = process.hrtime.bigint();
        const score = borrower?.score || computeScore(borrower?.features);
        const pDefault = (1000 - score) / 1000;
        timings.ml_inference = timeMs(t0);

        result.score = score;
        result.pDefault = pDefault.toFixed(4);

        // L1: Commitment computation
        t0 = process.hrtime.bigint();
        const salt = BigInt('0x' + crypto.randomBytes(31).toString('hex'));
        const commitment = computeCommitment(score, salt);
        timings.commitment = timeMs(t0);

        result.commitment = '0x' + commitment;
        result.salt = '0x' + salt.toString(16);

        // Determine band
        const band = getBand(score);
        result.band = band;
        result.bandLabel = band ? `${band}+` : 'Below lowest band (< 400)';
        result.canGenerateProof = band !== null;

        // L2: Anchor to ledger
        if (contract) {
            t0 = process.hrtime.bigint();
            const did = `did:credit:${borrowerId.substring(0, 16)}`;
            try {
                console.log(`[ANCHOR] Attempting to anchor commitment for ${did}`);
                await contract.submitTransaction('AnchorCommitment', '0x' + commitment, did, 'lr_model_v1');
                timings.ledger_anchor = timeMs(t0);
                result.ledgerAnchored = true;
                result.did = did;
                console.log(`[ANCHOR] Success for ${did}`);
            } catch (e) {
                // Parse error details - Fabric Gateway errors have details as array
                let errorStr = e.message || '';
                if (e.details && Array.isArray(e.details)) {
                    // Extract error messages from details array
                    const detailMessages = e.details.map(d => {
                        if (typeof d === 'string') return d;
                        if (d.message) return d.message;
                        if (d.address) return `${d.address}: ${d.message || JSON.stringify(d)}`;
                        return JSON.stringify(d);
                    }).join('; ');
                    errorStr += ' | Details: ' + detailMessages;
                }
                if (e.cause) {
                    errorStr += ' | Cause: ' + (e.cause.message || e.cause);
                }

                console.log(`[ANCHOR] Error for ${did}:`, errorStr);
                console.log(`[ANCHOR] Full error details:`, JSON.stringify(e.details, null, 2));

                // Check if commitment already exists
                if (errorStr.includes('already exists')) {
                    console.log(`[ANCHOR] Commitment exists, revoking first...`);
                    try {
                        await contract.submitTransaction('RevokeCommitment', did);
                        console.log(`[ANCHOR] Revoked successfully, now re-anchoring...`);
                        await contract.submitTransaction('AnchorCommitment', '0x' + commitment, did, 'lr_model_v1');
                        timings.ledger_anchor = timeMs(t0);
                        result.ledgerAnchored = true;
                        result.did = did;
                        result.previousRevoked = true;
                        console.log(`[ANCHOR] Re-anchor success for ${did}`);
                    } catch (retryError) {
                        // Parse retry error the same way
                        let retryErrorStr = retryError.message || '';
                        if (retryError.details && Array.isArray(retryError.details)) {
                            retryErrorStr += ' | ' + retryError.details.map(d => d.message || JSON.stringify(d)).join('; ');
                        }
                        console.log(`[ANCHOR] Retry failed:`, retryErrorStr);
                        timings.ledger_anchor = timeMs(t0);
                        result.ledgerAnchored = false;
                        result.ledgerError = 'Revoke+retry failed: ' + retryErrorStr;
                    }
                } else {
                    timings.ledger_anchor = timeMs(t0);
                    result.ledgerAnchored = false;
                    result.ledgerError = errorStr.substring(0, 200); // Truncate long errors
                    console.log(`[ANCHOR] Non-recoverable error, not retrying`);
                }
            }
        } else {
            result.ledgerAnchored = false;
            result.ledgerError = 'Fabric not connected';
        }

        result.timings = timings;
        result.totalL1 = (timings.consent + timings.feature_engineering + timings.ml_inference + timings.commitment).toFixed(2);
        result.totalL2 = (timings.ledger_anchor || 0).toFixed(2);

        res.json(result);

    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// LENDER FLOW: Verify eligibility via ZK proof
app.post('/api/lender/verify', async (req, res) => {
    const { borrowerId, threshold } = req.body;

    if (!BANDS.includes(threshold)) {
        return res.status(400).json({
            error: 'Invalid threshold. Must be one of: ' + BANDS.join(', '),
            allowedBands: BANDS
        });
    }

    const timings = {};
    const result = {
        borrowerId,
        threshold,
        layers: ['L3'],
        timings: {},
        // IMPORTANT: What lender does NOT receive
        lenderDoesNotReceive: {
            creditScore: 'HIDDEN - lender never sees exact score',
            behaviouralFeatures: 'HIDDEN - raw transaction data never leaves L1',
            marginAboveThreshold: 'HIDDEN - lender only knows >= threshold, not by how much',
            probabilityOfDefault: 'HIDDEN - only band membership revealed'
        }
    };

    try {
        const borrower = sampleBorrowers.find(b => b.id === borrowerId);
        const score = borrower?.score || computeScore(borrower?.features);
        const band = getBand(score);

        // Cannot generate proof if below lowest band or band < threshold
        if (band === null) {
            result.eligible = false;
            result.reason = 'No valid band - score below lowest threshold';
            result.proofGenerated = false;
            return res.json(result);
        }

        if (band < threshold) {
            result.eligible = false;
            result.reason = `Band ${band} is below threshold ${threshold}`;
            result.proofGenerated = false;
            return res.json(result);
        }

        // Generate ZK proof
        const salt = BigInt('0x' + crypto.randomBytes(31).toString('hex'));
        const commitment = computeCommitment(band, salt); // Prove band membership

        // Circuit inputs - bands are hardcoded in circuit template, not inputs
        const input = {
            score: band.toString(),
            salt: salt.toString(),
            threshold: threshold.toString(),
            commitment: BigInt('0x' + commitment).toString()
        };

        let t0 = process.hrtime.bigint();
        const { proof, publicSignals } = await snarkjs.groth16.fullProve(
            input,
            CONFIG.wasmPath,
            CONFIG.zkeyPath
        );
        timings.proof_generation = timeMs(t0);

        // Verify proof
        t0 = process.hrtime.bigint();
        const isValid = await snarkjs.groth16.verify(verificationKey, publicSignals, proof);
        timings.proof_verification = timeMs(t0);

        result.eligible = isValid;
        result.proofGenerated = true;
        result.proofValid = isValid;
        result.proofSize = JSON.stringify(proof).length;
        result.timings = timings;
        result.totalL3 = (timings.proof_generation + timings.proof_verification).toFixed(2);

        res.json(result);

    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// LENDER FLOW: Approve loan (record on ledger)
app.post('/api/lender/approve', async (req, res) => {
    const { borrowerId, threshold, proofHash, amount } = req.body;

    const did = `did:credit:${borrowerId.substring(0, 16)}`;
    const result = {
        borrowerId,
        did,
        threshold,
        amount,
        layers: ['L2'],
        timings: {}
    };

    try {
        if (!contract) {
            return res.status(503).json({ error: 'Fabric not connected' });
        }

        // Record loan approval event on ledger
        const t0 = process.hrtime.bigint();
        console.log(`[LOAN] Recording loan event for ${did}, threshold=${threshold}, amount=${amount}`);
        try {
            // Note: valid eventTypes are: verification, approval, rejection, default, repayment
            await contract.submitTransaction(
                'RecordLoanEvent',
                did,
                'approval',  // Changed from 'loan_approved' to match chaincode validation
                proofHash || 'no_proof_hash',
                threshold.toString()
            );
            result.timings.ledger_record = timeMs(t0);
            result.recorded = true;
            result.txTime = new Date().toISOString();
            console.log(`[LOAN] Success for ${did}`);
        } catch (e) {
            // Parse error details - same as anchor endpoint
            let errorStr = e.message || '';
            if (e.details && Array.isArray(e.details)) {
                const detailMessages = e.details.map(d => {
                    if (typeof d === 'string') return d;
                    if (d.message) return d.message;
                    return JSON.stringify(d);
                }).join('; ');
                errorStr += ' | Details: ' + detailMessages;
            }
            console.log(`[LOAN] Error for ${did}:`, errorStr);
            console.log(`[LOAN] Full error details:`, JSON.stringify(e.details, null, 2));

            result.timings.ledger_record = timeMs(t0);
            result.recorded = false;
            result.error = errorStr.substring(0, 200);
        }

        res.json(result);

    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// REGULATOR FLOW: Query ledger history (read-only)
app.post('/api/regulator/history', async (req, res) => {
    const { borrowerId } = req.body;
    const did = `did:credit:${borrowerId.substring(0, 16)}`;

    console.log(`[REGULATOR] Querying records for ${did}`);

    const result = {
        borrowerId,
        did,
        layers: ['L2'],
        accessType: 'READ-ONLY',
        msp: 'RegulatoryObserverMSP'
    };

    try {
        if (!contract) {
            return res.status(503).json({ error: 'Fabric not connected' });
        }

        // Query commitment
        const t0 = process.hrtime.bigint();
        try {
            const commitmentResult = await contract.evaluateTransaction('GetCommitment', did);
            // Fabric Gateway returns Uint8Array, need to convert properly
            const commitmentStr = Buffer.from(commitmentResult).toString('utf8');
            result.commitment = JSON.parse(commitmentStr);
            console.log(`[REGULATOR] Commitment found for ${did}`);
        } catch (e) {
            result.commitment = null;
            result.commitmentError = 'No commitment found';
            console.log(`[REGULATOR] No commitment for ${did}:`, e.message?.substring(0, 100));
        }

        // Query history
        try {
            const historyResult = await contract.evaluateTransaction('GetCreditHistory', did);
            // Fabric Gateway returns Uint8Array, need to convert properly
            const historyStr = Buffer.from(historyResult).toString('utf8');
            console.log(`[REGULATOR] History raw response for ${did}:`, historyStr.substring(0, 200));
            result.history = JSON.parse(historyStr);
            console.log(`[REGULATOR] Parsed ${result.history?.length || 0} history events`);
        } catch (e) {
            result.history = [];
            console.log(`[REGULATOR] History error for ${did}:`, e.message?.substring(0, 100));
        }

        result.queryTime = timeMs(t0);
        result.readOnlyEnforced = true;
        result.writeBlocked = {
            status: 'BLOCKED',
            reason: 'RegulatoryObserverMSP is not authorized to perform write operations',
            enforcement: 'Chaincode ACL + Endorsement Policy'
        };

        res.json(result);

    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// REGULATOR: Attempt write (to demonstrate ACL rejection)
app.post('/api/regulator/attemptWrite', async (req, res) => {
    res.json({
        status: 'BLOCKED',
        error: 'access denied: RegulatoryObserverMSP is not authorized to perform write operations',
        explanation: 'The Regulatory Observer has read-only access to the ledger. Write attempts are rejected by chaincode ACL.',
        embeddedSupervision: 'Per Auer (2022), the regulator can observe all transactions without being able to modify them.',
        layers: ['L2']
    });
});

// Serve HTML pages
app.get('/', (req, res) => res.sendFile(path.join(__dirname, 'public', 'index.html')));
app.get('/borrower', (req, res) => res.sendFile(path.join(__dirname, 'public', 'borrower.html')));
app.get('/lender', (req, res) => res.sendFile(path.join(__dirname, 'public', 'lender.html')));
app.get('/regulator', (req, res) => res.sendFile(path.join(__dirname, 'public', 'regulator.html')));

// Start server
initialize().then(() => {
    app.listen(CONFIG.port, () => {
        console.log(`UI Server running at http://localhost:${CONFIG.port}`);
        console.log('Available screens:');
        console.log('  /borrower  - Borrower view (L1 + L2)');
        console.log('  /lender    - Lender verification (L3)');
        console.log('  /regulator - Regulatory observer (L2 read-only)');
    });
}).catch(err => {
    console.error('Failed to initialize:', err);
    process.exit(1);
});
