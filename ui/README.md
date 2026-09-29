# Credit Scoring Demo UI

Web demo of the privacy-preserving pipeline, with one view per role: Borrower, Lender and Regulator. It runs against the real model, Fabric ledger and Groth16 circuit; nothing is simulated.

## Prerequisites

1. **Fabric network running.** The server connects as CommercialBankA (`localhost:7051`) and as the regulatory observer (`localhost:10051`). Restart stopped containers with `docker start`; see `../chain/README.md`.
2. **ZK artifacts** in `../circuits/build/`: `ctb_final.zkey`, `credit_threshold_banded_js/credit_threshold_banded.wasm`, `ctb_verification_key.json`
3. **Model and data:** `../results/lr_model_coefficients.json`, `../results/canonical_split.json`, `../data/features_processed.csv`

## Running

```bash
cd ui
npm install
npm start            # http://localhost:3000
```

## Views

**Borrower** (`/borrower`, L1 + L2)
- Consent, score computed from the borrower's real model inputs, Poseidon commitment anchored on the ledger
- Per-stage timing breakdown
- "What Shaped Your Score": points each factor added or removed versus a typical borrower
- "Data Used for Your Score": every model input

**Lender** (`/lender`, L2 + L3)
- Four fixed threshold bands only: 400, 550, 700, 850
- Reads the commitment from the ledger, then generates a Groth16 proof and verifies it against that commitment
- Privacy disclosure: what the lender receives and what it does not
- Loan approval, capped by the borrower's active exposure for the proven band. Each proof authorises one loan; loans can be marked repaid.

**Regulator** (`/regulator`, L2, read-only)
- Queries commitments and loan events as `RegulatoryObserverMSP` (Admin identity; see the caveat in `../chain/README.md`)
- "Attempt Write" sends a real transaction, which the chaincode rejects

## Where the data comes from

| Display | Source |
|---|---|
| Borrowers | 25 real customers from the canonical test split, at evenly spaced score quantiles |
| Scores and features | Computed live from `features_processed.csv` with the exported LR model |
| Timings | Measured live per request |
| Proofs | Generated and verified live with snarkjs |
| Ledger data | Live Fabric queries and transactions |

## Demo state

- **Borrower credentials** (score and salt) live in server memory, standing in for the borrower's wallet. After a server restart, run a borrower through the Borrower view again before verifying them as a lender.
- **Loan book**: `loan-book.json` (gitignored). This is the lender's own off-chain record of amounts and repayments; the ledger records only approval events. Delete the file to start with an empty book.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/borrowers` | Picker list (id and label only, no scores) |
| POST | `/api/borrower/process` | Score, commit, anchor; returns features and factor explanation |
| POST | `/api/lender/verify` | Read commitment, prove, verify; returns the lender's credit position |
| POST | `/api/lender/approve` | Record a loan approval, subject to proof and exposure checks |
| POST | `/api/lender/repay` | Mark a loan repaid (off-chain) |
| POST | `/api/regulator/history` | Commitment and event history, as the regulator |
| POST | `/api/regulator/attemptWrite` | Real write attempt as the regulator |

## Design

The visual system (Industry: steel-blue, square hairline frames) is described in `DESIGN_SYSTEM.md`. Styles are in `public/styles/`; fonts and icons are self-hosted so the demo works offline.
