# Credit Scoring Demo UI

Privacy-preserving credit scoring demonstration with three screens for Borrower, Lender, and Regulator views.

## Prerequisites

1. **Fabric network running** — the UI connects to `localhost:7051` for ledger operations
2. **ZK circuit artifacts** — in `../circuits/build/`:
   - `ctb_final.zkey`
   - `credit_threshold_banded_js/credit_threshold_banded.wasm`
   - `ctb_verification_key.json`
3. **Model coefficients** — `../results/lr_model_coefficients.json`

## Running

```bash
cd ui
npm install
npm start
```

Open http://localhost:3000

## Screens

### 1. Borrower (`/borrower`)
**Layers:** L1 (ML) + L2 (Ledger)

- Select borrower from test set
- Consent checkbox
- Displays: credit score, P(default), band, Poseidon commitment
- Anchors commitment to Fabric ledger
- Per-stage timing breakdown

### 2. Lender (`/lender`)
**Layers:** L3 (ZK Proof)

- Select borrower
- Threshold selection from bands [400, 550, 700, 850] only (fixed buttons)
- Generates and verifies Groth16 proof
- **Privacy panel showing what lender does NOT receive**

### 3. Regulator (`/regulator`)
**Layers:** L2 (Read-only)

- Query ledger history for any borrower
- Shows commitments and loan events
- **ACL rejection demo** — blocked write operation

## Data Sources

| Display | Source |
|---------|--------|
| Credit scores | Pre-computed from LR model (`data/test_borrowers_sample.json`) |
| Timing data | Live measurement |
| ZK proofs | Live generation via snarkjs |
| Ledger data | Live queries to Fabric |

## Screenshots

Capture screenshots for Chapter 4:
1. Borrower view with score and commitment
2. Lender view with eligibility result and privacy panel
3. Sub-band borrower (score < 400) showing "below lowest band"
4. Regulator view with ACL rejection message
