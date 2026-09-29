# Operating Requirements Specification

This document specifies the hardware and software requirements for the privacy-preserving credit scoring system, as required by MIT899 Chapter 4.

---

## 1. Development Environment (As Measured)

All figures in Chapters 4 and 5 were produced on this configuration:

### Hardware
| Component | Specification |
|-----------|---------------|
| CPU | AMD Ryzen 7 4800H |
| Cores | 8 physical / 16 logical |
| RAM | 32 GB DDR4 |
| Storage | SSD (NVMe) |
| Network | Localhost only (no external network latency) |

### Operating System
| Component | Version |
|-----------|---------|
| OS | Windows 10 |
| Container Runtime | Docker Desktop |
| Docker Memory | 8 GB allocated |

### Software Stack
| Component | Version | Layer |
|-----------|---------|-------|
| Python | 3.11 | L1 (ML) |
| scikit-learn | 1.7.2 | L1 (ML) |
| XGBoost | 3.2.0 | L1 (ML) |
| pandas | 2.x | L1 (ML) |
| Node.js | v20.10.0 | L2/L3 |
| Hyperledger Fabric | 2.5 | L2 |
| Go | 1.21+ | L2 (chaincode) |
| snarkjs | 0.7.6 | L3 (ZK) |
| circom | 2.2.3 | L3 (ZK) |
| circomlibjs | 0.1.7 | L3 (ZK) |

---

## 2. Minimum Viable Specification

These are the minimum requirements to run each layer, based on observations during development.

### L1: ML Training
| Resource | Minimum | Basis |
|----------|---------|-------|
| RAM | 2 GB | Dataset is 4,376 rows × 32 features; observed peak ~500 MB during CV |
| CPU | Any modern | Training completes in < 1 minute on single core |
| Storage | 50 MB | Model coefficients + feature engineering artifacts |

**Notes:**
- Training is CPU-bound, not memory-bound at this scale
- GPU not required (LogisticRegression uses liblinear)

### L1: ML Inference
| Resource | Minimum | Basis |
|----------|---------|-------|
| RAM | 50 MB | Model loaded in memory |
| CPU | Any | 0.01 ms per inference measured |
| Latency | Negligible | Dominated by L2/L3 operations |

**Notes:**
- Inference is effectively instantaneous relative to other layers
- Could run on embedded hardware if needed

### L2: Hyperledger Fabric
| Resource | Minimum | Observed |
|----------|---------|----------|
| RAM (Docker) | 4 GB | ~900 MB total across 6 containers |
| CPU cores | 2 | Single orderer configuration |
| Storage | 1 GB | Ledger grows with transactions |
| Network ports | 7050-7054, 9440-9444 | Peer and orderer endpoints |

**Container breakdown (from fabric_deployment.json):**
| Container | Purpose | RAM (typical) |
|-----------|---------|---------------|
| orderer.orderer.credit.ng | Ordering service | 100 MB |
| peer0.commercialbanka.credit.ng | Endorsing peer (issuer) | 200 MB |
| peer0.microfinanceb.credit.ng | Endorsing peer | 200 MB |
| peer0.fintechc.credit.ng | Endorsing peer | 200 MB |
| peer0.regulator.credit.ng | Observer peer (read-only) | 150 MB |
| cli | Admin container | 50 MB |

**State database:** LevelDB (Fabric default) — no separate CouchDB containers.

**Notes:**
- Single-orderer deployment used for development (not fault-tolerant)
- Production requires minimum 3 orderers for Raft CFT

### L3: ZK Proof Generation
| Resource | Minimum | Observed |
|----------|---------|----------|
| RAM | 1 GB | Proving key ~20 MB; working set ~500 MB |
| CPU | 1 core | Proof generation 125 ms mean on 8-core |
| Cold start | 507 ms | WASM warmup; subsequent proofs 125 ms |

**Tested minimal configuration:**
- 1 vCPU / 3 GB container in early testing
- Proof generation completed successfully

**Notes:**
- WASM-based prover is single-threaded
- Circuit size (576 constraints) is small; scales linearly with constraints

### L3: ZK Proof Verification
| Resource | Minimum | Observed |
|----------|---------|----------|
| RAM | 100 MB | Verification key ~2 KB |
| CPU | Any | 12.5 ms mean |
| Throughput | ~80/sec/core | Embarrassingly parallelizable |

---

## 3. Deployment Recommendations

### Development/Testing
| Component | Recommendation |
|-----------|----------------|
| Docker | Docker Desktop with 8 GB allocated |
| Fabric | Single orderer, BatchTimeout 200 ms for fast iteration |
| ZK | Pre-compiled circuits; skip trusted setup |

### Production Consortium

**Fabric Network:**
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Orderers | Minimum 3 | Raft requires 2f+1 for f=1 fault tolerance |
| BatchTimeout | 200-500 ms | Lower = faster interactive responses |
| MaxMessageCount | 10-50 | Little difference in this range (~5%); values ≥ 100 cause starvation |
| Endorsing orgs | 3 | MAJORITY endorsement policy |

**Capacity Planning:**
| Metric | Measured | Notes |
|--------|----------|-------|
| Throughput ceiling | 119-133 TPS | Single orderer; scales with orderer count |
| Write latency | 249 ms | At BatchTimeout 200 ms |
| Query latency | 8 ms | LevelDB state queries |

**Security:**
| Component | Requirement |
|-----------|-------------|
| TLS | Required for all peer-to-peer communication |
| MSP | Separate certificate authorities per organization |
| ACL | RegulatoryObserverMSP restricted to read-only |

### ZK Infrastructure

**Trusted Setup:**
| Parameter | Value |
|-----------|-------|
| Powers of Tau | pot12 (4,096 constraints max) |
| Per-circuit setup | ~3 seconds |
| Phase 1 ceremony | Reusable across circuits |

**Verification Key Distribution:**
- Embed in smart contract for on-chain verification
- Or distribute via trusted channel for off-chain verification
- Key size: ~2 KB (Groth16)

---

## 4. Scaling Considerations

### Horizontal Scaling
| Layer | Scalability |
|-------|-------------|
| L1 (ML) | Trivially parallelizable; inference is stateless |
| L2 (Fabric) | Add peers per org; multiple orderer nodes |
| L3 (ZK) | Proof generation parallelizable across requests |

### Vertical Scaling
| Layer | Benefit |
|-------|---------|
| L1 (ML) | Minimal (already < 1 ms) |
| L2 (Fabric) | Marginal (network-bound, not CPU-bound) |
| L3 (ZK) | Linear with CPU cores for concurrent proofs |

### Bottleneck Analysis
*Based on approved path (643 ms total)*

| Component | Latency | % of Total | Scaling Strategy |
|-----------|---------|------------|------------------|
| L2 anchor write | 248.6 ms | 38.7% | More orderers; Raft vs single |
| L2 repayment write | 248.5 ms | 38.6% | (same as above) |
| L3 proof generation | 125.2 ms | 19.5% | Faster prover; GPU acceleration (future) |
| L3 proof verification | 12.5 ms | 1.9% | Already fast; parallelizable |
| L2 query | 8.3 ms | 1.3% | Already fast |
| L1 (ML) | 0.29 ms | 0.0% | Already negligible |
| **Total** | **643.4 ms** | **100%** | |

---

## 5. Not Measured

The following were not measured during development and should be verified before production deployment:

- [ ] Network latency impact (all tests on localhost)
- [ ] Concurrent user load beyond 75 TPS
- [ ] Long-term ledger growth and pruning
- [ ] Certificate renewal procedures
- [ ] Disaster recovery procedures
- [ ] GPU-accelerated proof generation (bellman, rapidsnark)

---

*Last updated: 2026-08-29*
*Source: Results from T61, T62, T56, and development observations*
