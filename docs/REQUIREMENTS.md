# Requirements Analysis

This document reconstructs the system specification from what was built, with functional requirements derived from implemented functionality and non-functional requirements backed by measured values.

---

## 1. Functional Requirements

### FR-1. Alternative Data Ingestion
The system shall ingest behavioural transaction data from partner institutions.

### FR-2. Feature Engineering
The system shall compute regularity and magnitude features from raw transaction history, including:
- Repayment delay statistics (mean, std)
- Early repayment ratio
- Loan count and relationship tenure
- Interval regularity between transactions
- Amount statistics (mean, max, total, coefficient of variation)

*Implementation note: Feature engineering runs as an offline batch process. The integration demo reads precomputed features from a feature store (0.02 ms). The batch pipeline processes all 4,376 borrowers in ~2 seconds.*

### FR-3. Credit Score Computation
The system shall compute an integer credit score in the range 0-1000 using the formula:
`score = round(1000 * (1 - P(default)))`

### FR-4. Commitment Generation
The system shall generate a Poseidon hash commitment of the credit score:
`commitment = Poseidon(score, salt)`

### FR-5. Ledger Anchoring
The system shall anchor score commitments to the Hyperledger Fabric ledger, indexed by borrower DID.

### FR-6. Loan Event Recording
The system shall record loan lifecycle events (disbursement, repayment) to the ledger.

### FR-7. Credit History Retrieval
The system shall support retrieval of a borrower's commitment and loan history from the ledger.

### FR-8. ZK Proof Generation
The system shall generate a Groth16 zero-knowledge proof demonstrating:
`Poseidon(score, salt) == commitment AND score >= threshold`
where threshold is one of the permitted bands {400, 550, 700, 850}.

### FR-9. Proof Verification
The system shall verify ZK proofs locally, without revealing the score to the verifier.

### FR-10. Regulator Read-Only Access
The system shall permit the regulatory observer organization to read all ledger data but block all write operations.

### FR-11. Banded Thresholds
The system shall restrict threshold selection to four fixed bands {400, 550, 700, 850} to limit information leakage.

### FR-12. Sub-Band Handling
The system shall reject proof generation requests for scores below the lowest band (< 400), returning a clear "ineligible" status rather than an error.

### FR-13. Commitment Revocation
The system shall support commitment revocation for re-scoring. The `RevokeCommitment(did)` function marks a commitment as revoked, allowing a new commitment to be anchored. *Status: Implemented in chaincode but not exercised in integration testing.*

---

## 2. Non-Functional Requirements

Each NFR is stated with its target and measured value. This is the strength of an implementation-first dissertation: most NFRs in the literature are aspirational; these are empirical.

| ID | Requirement | Target | Measured | Source |
|----|-------------|--------|----------|--------|
| NFR-1 | End-to-end decision latency (approved path) | < 1 s | **643 ms** | `integration_demo_t61.json` |
| NFR-2 | End-to-end decision latency (rejected path) | < 1 s | **395 ms** | `integration_demo_t61.json` |
| NFR-3 | Proof verification latency | < 50 ms | **12.5 ms** | `integration_demo_t61.json` |
| NFR-4 | Proof generation latency (steady state) | < 500 ms | **125 ms** | `integration_demo_t61.json` |
| NFR-5 | Proof size | < 1 KB | **720 bytes** | `zk_baseline.json` |
| NFR-6 | Ledger write latency | < 500 ms | **249 ms** (at BatchTimeout 200ms) | `batch_config_sweep.json` |
| NFR-7 | Sustained throughput | — | **119-133 TPS** (single orderer) | `throughput_t62.json` |
| NFR-8 | ML inference latency | < 10 ms | **0.01 ms** | `integration_demo_t61.json` |
| NFR-9 | Score confidentiality | Lender learns ≤ band membership | **H = 1.99 bits** over 5 partitions | `leakage_5way.json` |
| NFR-10 | Regulator write access | Blocked by ACL | **Verified** (authorisation failure) | `observer_acl_enforcement.json` |
| NFR-11 | No PII on-chain | Commitments only | **Verified** in chaincode | Chaincode source inspection |
| NFR-12 | Model accuracy | ROC-AUC > 0.65 | **0.6957** (LR) | `model_tuning_v2.json` |
| NFR-13 | Fairness reporting | FPR disparity quantified | **2.7× at threshold 0.53** | `fairness_full_table_t60.json` |
| NFR-14 | Calibration error | ECE < 0.10 | **0.037** | `calibration_methodology_t58.json` |
| NFR-15 | ZK circuit overhead | < 5% constraint increase for banding | **0.5%** (573 → 576) | `constraint_counts.json` |

---

## 3. Traceability Matrix

| Requirement | Implementation | Test Evidence |
|-------------|----------------|---------------|
| FR-1, FR-2 | `ml/feature_engineering.py` | `data_profile.json` |
| FR-3 | `ml/train_models.py` | `model_tuning_v2.json` |
| FR-4 | `circomlibjs` Poseidon (JS) | `integration_demo_t61.json` |
| FR-5, FR-6, FR-7 | `chain/chaincode/credit.go` | `fabric_deployment.json` |
| FR-8, FR-9 | `integration/end_to_end_sdk_t61.js` + circuit | `integration_demo_t61.json` |
| FR-10 | Fabric endorsement policy + chaincode ACL | `observer_acl_enforcement.json` |
| FR-11 | Circuit `bands` input | `leakage_5way.json` |
| FR-12 | Application logic | `integration_demo_t61.json` |
| FR-13 | `chain/chaincode/credit.go` RevokeCommitment | Not exercised in testing |

---

## 4. Constraints

### C-1. Score Scaling
The score formula is fixed: `score = round(1000 * (1 - P(default)))`, producing integers in range 0-1000. The ZK circuit depends on this 16-bit range.

### C-2. No Raw Data On-Chain
Raw behavioural features, exact scores, and PII must never be stored on-chain. Only Poseidon commitments and loan event metadata are permitted.

### C-3. Binding Commitment
The ZK proof must include a commitment binding constraint. Without it, a borrower could prove "I know some number ≥ T" without linking to their actual score.

### C-4. Banded Thresholds
Free-form threshold selection is prohibited. Only the four fixed bands {400, 550, 700, 850} are permitted to limit binary-search leakage.

### C-5. Read-Only Regulator
The RegulatoryObserverMSP organization must have read access to all ledger state but zero write capability. This is enforced by chaincode ACL and endorsement policy.

---

## 5. Assumptions

### A-1. Partner Data Availability
Behavioural transaction data is assumed available from partner institutions with appropriate consent.

### A-2. Consortium Trust Model
Organizations in the Fabric consortium are assumed semi-trusted: they follow the protocol but may attempt to learn private information.

### A-3. Honest Verifier
The lender is assumed to verify proofs honestly. Collusion between borrower and lender to bypass the system is outside the threat model.

### A-4. Single Borrower Per Session
The demo handles one borrower per verification request. Batch verification is not implemented.

---

*Last updated: 2026-08-29*
