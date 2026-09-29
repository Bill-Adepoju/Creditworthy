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
    // The Regulator view connects as the observer org itself. Only its admin satisfies
    // the org's Writers policy, which Fabric requires for any proposal (reads included).
    regulator: {
        mspId: 'RegulatoryObserverMSP',
        org: 'regulator.credit.ng',
        user: 'Admin@regulator.credit.ng',
        peerEndpoint: 'localhost:10051',
        peerHostAlias: 'peer0.regulator.credit.ng'
    },
    featuresPath: path.resolve(__dirname, '../data/features_processed.csv'),
    splitPath: path.resolve(__dirname, '../results/canonical_split.json'),
    demoBorrowerCount: 25,
    zkeyPath: path.resolve(__dirname, '../circuits/build/ctb_final.zkey'),
    wasmPath: path.resolve(__dirname, '../circuits/build/credit_threshold_banded_js/credit_threshold_banded.wasm'),
    vkeyPath: path.resolve(__dirname, '../circuits/build/ctb_verification_key.json')
};

// Bands for threshold selection (lender can only choose these)
const BANDS = [400, 550, 700, 850];
const LENDER_THRESHOLD = 550;

// L1 model: the logistic regression exported by ml/export_model_coefficients.py.
// Fails loudly rather than falling back to a made-up score.
const MODEL = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../results/lr_model_coefficients.json'), 'utf8'));
console.log(`  Model coefficients loaded (${MODEL.feature_names.length} features)`);

// One-hot groups are shown to the borrower as a single decoded value.
const CATEGORICAL_PREFIXES = ['bank_account_type_', 'employment_status_', 'region_lat_band_'];

function parseFeatureRow(header, line) {
    const cells = line.split(',');
    const row = {};
    header.forEach((h, i) => { row[h] = cells[i]; });
    return row;
}

function modelInputs(row) {
    return MODEL.feature_names.map((name) => {
        const v = row[name];
        if (v === 'True') return 1;
        if (v === 'False') return 0;
        return Number(v);
    });
}

// score = round(1000 * (1 - P(default))), P(default) from the standardised LR model.
function scoreFromInputs(x) {
    let logit = MODEL.intercept;
    x.forEach((v, i) => {
        logit += MODEL.coefficients[i] * ((v - MODEL.scaler_mean[i]) / MODEL.scaler_scale[i]);
    });
    const pDefault = 1 / (1 + Math.exp(-logit));
    return { pDefault, score: Math.round(1000 * (1 - pDefault)) };
}

// What the borrower is shown: every model input, with one-hot groups decoded.
function displayFeatures(row) {
    const out = {};
    for (const name of MODEL.feature_names) {
        const prefix = CATEGORICAL_PREFIXES.find((p) => name.startsWith(p));
        if (!prefix) { out[name] = Number(row[name]); continue; }
        if (row[name] === 'True') out[prefix.slice(0, -1)] = name.slice(prefix.length);
    }
    return out;
}

const BAND_NAMES = { 400: 'Basic', 550: 'Standard', 700: 'Good', 850: 'Premium' };

// Demo borrowers: real customers from the canonical TEST split (never seen in training),
// picked at evenly spaced score quantiles so every band is represented.
function loadDemoBorrowers() {
    const lines = fs.readFileSync(CONFIG.featuresPath, 'utf8').trim().split(/\r?\n/);
    const header = lines[0].split(',');
    const testIdx = JSON.parse(fs.readFileSync(CONFIG.splitPath, 'utf8')).indices.test;

    const scored = testIdx.map((i) => {
        const row = parseFeatureRow(header, lines[i + 1]);
        const inputs = modelInputs(row);
        return { id: row.customerid, inputs, features: displayFeatures(row), ...scoreFromInputs(inputs) };
    }).sort((a, b) => a.score - b.score || a.id.localeCompare(b.id));

    const n = CONFIG.demoBorrowerCount;
    const picked = Array.from({ length: n }, (_, k) => scored[Math.round(k * (scored.length - 1) / (n - 1))]);
    return picked.reverse().map((b, k) => {
        const band = getBand(b.score);
        return { ...b, label: `Borrower ${String.fromCharCode(65 + k)} · ${band ? BAND_NAMES[band] : 'Below 400'}` };
    });
}

// Globals
let contract = null;           // CommercialBankA identity: borrower anchoring, lender reads + approvals
let regulatorContract = null;  // RegulatoryObserverMSP identity: regulator view
let poseidon = null;
let verificationKey = null;
let sampleBorrowers = [];

// Borrower-held credential {score, salt, commitment}. In deployment this lives in the
// borrower's wallet and the proof is generated client-side; the demo server plays that role.
const borrowerWallet = new Map();

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

    sampleBorrowers = loadDemoBorrowers();
    console.log(`  Loaded ${sampleBorrowers.length} demo borrowers from the test split (scores ${sampleBorrowers[sampleBorrowers.length - 1].score}-${sampleBorrowers[0].score})`);

    try {
        contract = connectAs({
            mspId: CONFIG.mspId,
            org: 'commercialbanka.credit.ng',
            user: 'User1@commercialbanka.credit.ng',
            peerEndpoint: CONFIG.peerEndpoint,
            peerHostAlias: CONFIG.peerHostAlias
        });
        console.log('  Fabric Gateway connected (CommercialBankAMSP)');
    } catch (e) {
        console.error('  Warning: Could not connect to Fabric:', e.message);
    }

    try {
        regulatorContract = connectAs(CONFIG.regulator);
        console.log('  Fabric Gateway connected (RegulatoryObserverMSP)');
    } catch (e) {
        console.error('  Warning: Could not connect regulator identity:', e.message);
    }

    console.log('Server initialization complete.\n');
}

function connectAs({ mspId, org, user, peerEndpoint, peerHostAlias }) {
    const orgDir = path.join(CONFIG.cryptoPath, 'peerOrganizations', org);
    const tlsCert = fs.readFileSync(path.join(orgDir, 'peers', peerHostAlias, 'tls/ca.crt'));
    const client = new grpc.Client(peerEndpoint, grpc.credentials.createSsl(tlsCert), {
        'grpc.ssl_target_name_override': peerHostAlias,
        'grpc.keepalive_time_ms': 120000,
        'grpc.http2.min_time_between_pings_ms': 120000,
        'grpc.keepalive_timeout_ms': 20000,
        'grpc.http2.max_pings_without_data': 0,
        'grpc.keepalive_permit_without_calls': 1,
    });

    const mspDir = path.join(orgDir, 'users', user, 'msp');
    const gateway = connect({
        client,
        identity: { mspId, credentials: fs.readFileSync(path.join(mspDir, 'signcerts', `${user}-cert.pem`)) },
        signer: signers.newPrivateKeySigner(crypto.createPrivateKey(fs.readFileSync(path.join(mspDir, 'keystore/priv_sk')))),
        evaluateOptions: () => ({ deadline: Date.now() + 30000 }),
        endorseOptions: () => ({ deadline: Date.now() + 30000 }),
        submitOptions: () => ({ deadline: Date.now() + 30000 }),
        commitStatusOptions: () => ({ deadline: Date.now() + 120000 }),
    });
    return gateway.getNetwork(CONFIG.channelName).getContract(CONFIG.chaincodeName);
}

// Fabric Gateway errors carry per-peer messages in e.details; the top-level message is generic.
function fabricErrorDetail(e) {
    const details = Array.isArray(e.details) ? e.details.map((d) => (d.address ? `${d.address}: ` : '') + (d.message || JSON.stringify(d))) : [];
    return [e.message, ...details].filter(Boolean).join(' | ');
}

function didFor(borrowerId) {
    return `did:credit:${borrowerId.substring(0, 16)}`;
}

// Utility functions
function timeMs(start) {
    return Number(process.hrtime.bigint() - start) / 1_000_000;
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

// Borrower picker list. Deliberately id + label only: every view (including the lender's)
// loads this, so scores and features must not travel with it.
app.get('/api/borrowers', (req, res) => {
    res.json(sampleBorrowers.map(({ id, label }) => ({ id, label })));
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

        // L1: Feature retrieval. Features were engineered offline (ml/ pipeline) into
        // features_processed.csv, so this times a lookup, not feature engineering itself.
        t0 = process.hrtime.bigint();
        const borrower = sampleBorrowers.find(b => b.id === borrowerId);
        timings.feature_engineering = timeMs(t0);
        if (!borrower) {
            return res.status(404).json({ error: 'Unknown borrower' });
        }
        result.features = borrower.features;

        // L1: ML inference on the borrower's real model inputs
        t0 = process.hrtime.bigint();
        const { score, pDefault } = scoreFromInputs(borrower.inputs);
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
            const did = didFor(borrowerId);
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

        if (result.ledgerAnchored) {
            borrowerWallet.set(borrowerId, { score, salt, commitment: '0x' + commitment });
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
        if (!contract) {
            return res.status(503).json({ error: 'Fabric not connected' });
        }

        // L2: the lender reads the borrower's commitment from the ledger. This is the
        // public input the proof must bind to; the lender never takes it from the borrower.
        const did = didFor(borrowerId);
        let t0 = process.hrtime.bigint();
        let onChain;
        try {
            onChain = JSON.parse(Buffer.from(await contract.evaluateTransaction('GetCommitment', did)).toString('utf8'));
        } catch (e) {
            return res.status(409).json({ error: `No commitment on the ledger for ${did}. Process this borrower's score in the Borrower view first.` });
        }
        timings.commitment_retrieval = timeMs(t0);
        result.layers = ['L2', 'L3'];
        result.did = did;

        if (onChain.status !== 'active') {
            return res.status(409).json({ error: `On-chain commitment for ${did} is ${onChain.status}` });
        }

        // L3 prover side: the borrower's credential (score + salt) opens that commitment.
        const credential = borrowerWallet.get(borrowerId);
        if (!credential || credential.commitment.toLowerCase() !== onChain.commitmentHash.toLowerCase()) {
            return res.status(409).json({ error: 'The borrower holds no credential for the current on-chain commitment. Re-run Process Credit Score in the Borrower view.' });
        }

        // The circuit hard-constrains score >= threshold, so an ineligible borrower cannot
        // produce a proof at all. The lender learns the same single bit from the refusal.
        if (credential.score < threshold) {
            result.eligible = false;
            result.proofGenerated = false;
            result.reason = 'Borrower cannot produce a proof for this threshold';
            result.timings = timings;
            return res.json(result);
        }

        const commitmentField = BigInt(onChain.commitmentHash).toString();
        t0 = process.hrtime.bigint();
        const { proof } = await snarkjs.groth16.fullProve(
            {
                score: credential.score.toString(),
                salt: credential.salt.toString(),
                commitment: commitmentField,
                threshold: threshold.toString()
            },
            CONFIG.wasmPath,
            CONFIG.zkeyPath
        );
        timings.proof_generation = timeMs(t0);

        // Lender side: verify against public signals the lender assembles itself
        // [eligible, commitment (from ledger), threshold (lender's choice)].
        t0 = process.hrtime.bigint();
        const isValid = await snarkjs.groth16.verify(verificationKey, ['1', commitmentField, threshold.toString()], proof);
        timings.proof_verification = timeMs(t0);

        result.eligible = isValid;
        result.proofGenerated = true;
        result.proofValid = isValid;
        result.proofSize = JSON.stringify(proof).length;
        result.proofHash = '0x' + crypto.createHash('sha256').update(JSON.stringify(proof)).digest('hex');
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

    const did = didFor(borrowerId);
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
    const did = didFor(borrowerId);

    console.log(`[REGULATOR] Querying records for ${did}`);

    const result = {
        borrowerId,
        did,
        layers: ['L2'],
        accessType: 'READ-ONLY',
        msp: 'RegulatoryObserverMSP'
    };

    try {
        if (!regulatorContract) {
            return res.status(503).json({ error: 'Fabric not connected (regulator identity)' });
        }

        // Query commitment, as RegulatoryObserverMSP
        const t0 = process.hrtime.bigint();
        try {
            const commitmentResult = await regulatorContract.evaluateTransaction('GetCommitment', did);
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
            const historyResult = await regulatorContract.evaluateTransaction('GetCreditHistory', did);
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
        res.json(result);

    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// REGULATOR: attempt a real write as RegulatoryObserverMSP. The rejection shown in the UI
// is whatever Fabric actually returns, not a canned message.
app.post('/api/regulator/attemptWrite', async (req, res) => {
    if (!regulatorContract) {
        return res.status(503).json({ error: 'Fabric not connected (regulator identity)' });
    }
    const probeDid = 'did:credit:regulator-write-probe';
    const t0 = process.hrtime.bigint();
    try {
        await regulatorContract.submitTransaction('AnchorCommitment', '0x' + '0'.repeat(63) + '1', probeDid, 'regulator_write_probe');
        // Reaching here means read-only enforcement is broken; surface it, never mask it.
        console.error('[REGULATOR] WRITE ACCEPTED - read-only enforcement failed');
        res.json({ status: 'ACCEPTED', error: 'WRITE ACCEPTED: RegulatoryObserverMSP was able to write to the ledger', rejectedBy: null, timeMs: timeMs(t0) });
    } catch (e) {
        const detail = fabricErrorDetail(e);
        const peerMsg = (Array.isArray(e.details) ? e.details : []).find((d) => /access denied/.test(d.message || ''));
        const chaincodeMatch = peerMsg && peerMsg.message.match(/chaincode response \d+, (.*)$/);
        console.log('[REGULATOR] Write rejected:', detail.substring(0, 300));
        res.json({
            status: 'BLOCKED',
            error: chaincodeMatch ? chaincodeMatch[1] : detail,
            rejectedBy: chaincodeMatch ? 'chaincode' : 'fabric',
            peer: peerMsg ? peerMsg.address : null,
            detail,
            timeMs: timeMs(t0)
        });
    }
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
