# Test Case Documentation

Appendix E: Formalised testing performed during development.

---

## Test Summary

| Type | Count | Pass | Fail | Evidence |
|------|-------|------|------|----------|
| Unit | 4 | 4 | 0 | Circuit verification |
| Integration | 2 | 2 | 0 | Bridge test, E2E flow |
| Performance | 4 | 4 | 0 | Benchmarks |
| Security | 2 | 2 | 0 | ACL, leakage analysis |
| **Total** | **12** | **12** | **0** | |

---

## 1. Unit Tests

### TC-U01: Eligible Proof Generation
| Field | Value |
|-------|-------|
| **ID** | TC-U01 |
| **Type** | Unit |
| **Objective** | Verify ZK proof generation for eligible borrower |
| **Preconditions** | Circuit compiled, proving key generated |
| **Input** | score=717, threshold=550, salt=random, bands=[400,550,700,850] |
| **Expected Result** | Valid Groth16 proof generated |
| **Actual Result** | Proof generated in 125ms, verification returns true |
| **Pass/Fail** | PASS |
| **Source** | `results/zk_baseline.json` |

### TC-U02: Ineligible Rejection
| Field | Value |
|-------|-------|
| **ID** | TC-U02 |
| **Type** | Unit |
| **Objective** | Verify circuit rejects score below threshold |
| **Preconditions** | Circuit compiled |
| **Input** | score=400, threshold=550 |
| **Expected Result** | Constraint `ge.out === 1` fails |
| **Actual Result** | Witness generation fails with constraint violation |
| **Pass/Fail** | PASS |
| **Source** | `results/zk_baseline.json` (sanity check) |

### TC-U03: Commitment Binding
| Field | Value |
|-------|-------|
| **ID** | TC-U03 |
| **Type** | Unit |
| **Objective** | Verify forged commitment is rejected |
| **Preconditions** | Circuit compiled |
| **Input** | Mismatched score/salt pair for given commitment |
| **Expected Result** | Poseidon constraint fails |
| **Actual Result** | Proof generation fails; cannot forge commitment |
| **Pass/Fail** | PASS |
| **Source** | `results/zk_baseline.json` (sanity check) |

### TC-U04: Off-Band Threshold Rejection
| Field | Value |
|-------|-------|
| **ID** | TC-U04 |
| **Type** | Unit |
| **Objective** | Verify non-band threshold is rejected |
| **Preconditions** | Banded circuit compiled |
| **Input** | threshold=600 (not in [400,550,700,850]) |
| **Expected Result** | Band polynomial constraint fails |
| **Actual Result** | Circuit rejects invalid threshold |
| **Pass/Fail** | PASS |
| **Source** | `results/constraint_counts.json` |

---

## 2. Integration Tests

### TC-I01: Bridge Test at Scale (1,000 attempts)
| Field | Value |
|-------|-------|
| **ID** | TC-I01 |
| **Type** | Integration |
| **Objective** | Verify ML → ZK bridge at scale with diverse scores |
| **Preconditions** | Circuit compiled, 1,000 borrowers with computed scores |
| **Input** | 1,000 proof generation/verification cycles across score range |
| **Expected Result** | 100% round-trip accuracy; zero hash collisions |
| **Actual Result** | 1,000 proofs generated; 100% accuracy; zero collisions |
| **Pass/Fail** | PASS |
| **Source** | `results/bridge_test.json` (Cycle 02) |

*Provenance note: This test predates the canonical 876-row test split and was not regenerated against it. The 1,000 borrowers were sampled from the full dataset before the train/validation/test split was finalised. The test validates ML→ZK integration but does not confirm coverage of the specific canonical test population.*

### TC-I02: End-to-End Flow (25 borrowers)
| Field | Value |
|-------|-------|
| **ID** | TC-I02 |
| **Type** | Integration |
| **Objective** | Full L1 → L2 → L3 flow with real Fabric network |
| **Preconditions** | Fabric network running, chaincode deployed |
| **Input** | 25 borrowers from test set, threshold=550 |
| **Expected Result** | Commitments anchored, proofs generated, loans recorded |
| **Actual Result** | 20 proofs generated (5 below lowest band); 16 approved; 4 rejected (band < threshold) |
| **Pass/Fail** | PASS |
| **Source** | `results/integration_demo_t61.json` |

---

## 3. Performance Tests

### TC-P01: ZK Proof Throughput
| Field | Value |
|-------|-------|
| **ID** | TC-P01 |
| **Type** | Performance |
| **Objective** | Measure proof generation and verification latency |
| **Preconditions** | Warmup completed |
| **Input** | 20 proof generation/verification cycles |
| **Expected Result** | Latency < 500ms |
| **Actual Result** | Proof gen: 125.2ms (mean), 186.2ms (P95); Verify: 12.5ms (mean) |
| **Pass/Fail** | PASS |
| **Source** | `results/integration_demo_t61.json` |

### TC-P02: Fabric Throughput (MMC Sweep)
| Field | Value |
|-------|-------|
| **ID** | TC-P02 |
| **Type** | Performance |
| **Objective** | Measure sustained transaction throughput |
| **Preconditions** | Fabric network running, 3 endorsing peers |
| **Input** | 75 concurrent clients, 300 transactions per config |
| **Expected Result** | Throughput > 100 TPS |
| **Actual Result** | MMC=10: 123 TPS; MMC=50: 130 TPS; ceiling ~133 TPS |
| **Pass/Fail** | PASS |
| **Source** | `results/throughput_t62.json` |

### TC-P03: Fabric Latency (BatchTimeout Sweep)
| Field | Value |
|-------|-------|
| **ID** | TC-P03 |
| **Type** | Performance |
| **Objective** | Measure single-transaction latency at different BatchTimeout |
| **Preconditions** | Idle network |
| **Input** | 20 sequential transactions per configuration |
| **Expected Result** | Latency proportional to BatchTimeout |
| **Actual Result** | 2s: 2051ms; 500ms: 568ms; 200ms: 256ms |
| **Pass/Fail** | PASS |
| **Source** | `results/batch_config_sweep.json` |

### TC-P04: End-to-End Decision Latency
| Field | Value |
|-------|-------|
| **ID** | TC-P04 |
| **Type** | Performance |
| **Objective** | Measure complete credit decision latency |
| **Preconditions** | All layers operational, BatchTimeout=200ms |
| **Input** | 25 borrower flows |
| **Expected Result** | Total < 1 second |
| **Actual Result** | Approved: 643ms; Rejected: 395ms |
| **Pass/Fail** | PASS |
| **Source** | `results/integration_demo_t61.json` |

---

## 4. Security Tests

### TC-S01: Regulator ACL Enforcement
| Field | Value |
|-------|-------|
| **ID** | TC-S01 |
| **Type** | Security |
| **Objective** | Verify RegulatoryObserverMSP cannot write to ledger |
| **Preconditions** | Fabric network with MAJORITY endorsement policy |
| **Input** | Write operation invoked by regulator identity |
| **Expected Result** | Authorization failure |
| **Actual Result** | `access denied: RegulatoryObserverMSP is not authorized` |
| **Pass/Fail** | PASS |
| **Source** | `results/observer_acl_enforcement.json` |

### TC-S02: Information Leakage Quantification
| Field | Value |
|-------|-------|
| **ID** | TC-S02 |
| **Type** | Security |
| **Objective** | Quantify information leakage from banded thresholds |
| **Preconditions** | 876 test borrowers with computed bands |
| **Input** | Band distribution analysis |
| **Expected Result** | Leakage ≤ log₂(5) = 2.32 bits |
| **Actual Result** | H = 1.99 bits (5-way partition); binary signal = 0.78 bits |
| **Pass/Fail** | PASS |
| **Source** | `results/leakage_5way.json` |

---

## 5. Testing Not Performed

The following test categories were not performed and should be acknowledged:

| Category | Status | Reason |
|----------|--------|--------|
| User Acceptance Testing | NOT PERFORMED | No end-users available for pilot |
| Load Testing (>100 TPS) | NOT PERFORMED | Single-orderer deployment limits capacity |
| Network Partition Testing | NOT PERFORMED | Localhost deployment only |
| Certificate Revocation Testing | NOT PERFORMED | Out of scope |
| Mobile/Responsive UI Testing | NOT PERFORMED | Desktop-only demo |
| Accessibility Testing | NOT PERFORMED | Demo UI only |

These limitations should be noted in Chapter 5 (Discussion and Limitations).

---

*Last updated: 2026-08-29*
