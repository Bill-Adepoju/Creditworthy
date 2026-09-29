# Reproducibility Manifest

This document enables complete reproduction of all experimental results reported in Chapters 4 and 5.

---

## 1. Environment

### Hardware
| Component | Specification |
|-----------|---------------|
| CPU | AMD Ryzen 7 4800H (8 cores / 16 threads) |
| RAM | 32 GB |
| OS | Windows 10 |
| Container runtime | Docker Desktop |

### Software Versions
| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.11 | ML training, feature engineering |
| scikit-learn | 1.7.2 | Model training, calibration |
| XGBoost | 3.2.0 | Ensemble model |
| pandas | 2.x | Data processing |
| Node.js | v20.10.0 | ZK proofs, Fabric SDK |
| snarkjs | 0.7.6 | Groth16 proof generation/verification |
| circom | 2.2.3 | Circuit compilation |
| circomlibjs | 0.1.7 | Poseidon hash |
| circomlib | 2.0.5 | Circuit library |
| Hyperledger Fabric | 2.5 | Blockchain layer |
| Go | 1.21+ | Chaincode |

---

## 2. Canonical Data Split

**Source:** Zindi SuperLender dataset (4,376 rows)

**Split configuration:**
| Set | N | Percentage |
|-----|---|------------|
| Train | 2,800 | 64% |
| Validation | 700 | 16% |
| Test | 876 | 20% |
| **Total** | **4,376** | 100% |

**Random seed:** 42 (used for all random operations)

**Stratification:** By target variable (default/good)

**Deduplication note:** The test set contains 517 Savings account rows across 516 unique customers (one customer appears twice due to duplicate records in the source data, verified in T64).

**Split file:** `results/canonical_split.json`

---

## 3. Run Order

Execute scripts in this order from the project root:

### Phase 1: Data Preparation
```bash
# 1. Profile raw data
python ml/data_profile.py

# 2. Feature engineering
python ml/features.py

# 3. Create canonical split
python ml/canonical_split.py
```

### Phase 2: Model Training and Evaluation
```bash
# 4. Train all models with CV
python ml/train.py

# 5. Hyperparameter tuning
python ml/model_tuning_v2.py

# 6. Statistical significance testing
python ml/significance_corrected.py

# 7. Feature set comparison
python ml/feature_set_significance.py

# 8. Fairness analysis
python ml/fairness_full_table_t60.py

# 9. Calibration
python ml/calibration_methodology_t58.py
```

### Phase 3: ZK Circuit
```bash
# 10. Compile circuits
cd circuits
circom credit_threshold.circom --r1cs --wasm --sym
circom credit_threshold_banded.circom --r1cs --wasm --sym

# 11. Generate proving keys
npx snarkjs groth16 setup credit_threshold_banded.r1cs pot12_final.ptau ctb_0000.zkey
npx snarkjs zkey contribute ctb_0000.zkey ctb_final.zkey

# 12. Export verification key
npx snarkjs zkey export verificationkey ctb_final.zkey ctb_verification_key.json
```

### Phase 4: Fabric Network
```bash
# 13-14. Generate crypto, start network, create channel, deploy and test chaincode
cd chain
./scripts/setup-all.sh

# Later restarts: `docker start` the existing containers.
# scripts/start.sh runs `docker-compose down --volumes`, which wipes the ledger.
```

### Phase 5: Integration Testing
```bash
# 15. End-to-end integration (generates latency decomposition and ZK metrics)
node integration/end_to_end_sdk_t61.js

# 16. Throughput benchmark (MMC sweep, 3 runs per config)
# Requires: Fabric network running, BatchTimeout at default (2s)
cd chain/caliper
node throughput_t62.js
# Output: results/throughput_t62.json

# 17. Latency benchmark (BatchTimeout sweep)
# Note: Script modifies channel config via docker exec; BatchTimeout changes
# are applied internally. Network must be in known state beforehand.
node batch_config_sweep.js
# Output: results/batch_config_sweep.json
```

---

## 4. Table Map

Every dissertation table is linked to its generating script and result file.

| Table | Title | Script | Result File |
|-------|-------|--------|-------------|
| 4.1 | Model Comparison (ROC-AUC) | `ml/model_tuning_v2.py` | `results/model_tuning_v2.json`, `results/significance_corrected.json` |
| 4.2 | Feature Set Comparison | `ml/feature_set_significance.py` | `results/feature_set_significance.json` |
| 4.3 | Fairness by Subgroup | `ml/fairness_full_table_t60.py` | `results/fairness_full_table_t60.json` |
| 4.4 | Fairness-Profit Trade-off | `ml/fairness_full_table_t60.py` | `results/fairness_full_table_t60.json` |
| 4.5 | FNR Gap Curve | `ml/calibration_methodology_t58.py` | `results/calibration_methodology_t58.json` |
| 4.6 | ZK Circuit Metrics | `integration/end_to_end_sdk_t61.js` | `results/constraint_counts.json`, `results/integration_demo_t61.json` |
| 4.7 | Privacy Leakage | `ml/leakage_5way.py` | `results/leakage_5way.json` |
| 4.8 | Fabric Throughput | `chain/caliper/throughput_t62.js` | `results/throughput_t62.json` |
| 4.9 | Fabric Latency | `chain/caliper/batch_config_sweep.js` | `results/batch_config_sweep.json` |
| 4.10 | End-to-End Decomposition | `integration/end_to_end_sdk_t61.js` | `results/integration_demo_t61.json` |

---

## 5. Known Non-Determinism

### ZK Proof Generation
| Observation | Value | Impact |
|-------------|-------|--------|
| Cold-start overhead | ~507 ms (vs 125 ms steady-state) | First proof of session 4× slower due to WASM warmup |
| Run-to-run variance | ~5% | Random salt generation; timing measurement noise |

**Mitigation:** Cold-start is excluded from statistics; 20 proofs measured per benchmark.

### Fabric Throughput
| Observation | Value | Impact |
|-------------|-------|--------|
| Run-to-run variance | 4-5% | Network timing, Docker scheduling |
| Batch starvation | At MMC ≥ 100 | Throughput collapses to ~34 TPS |

**Mitigation:** Three runs per configuration; variance explicitly reported.

### Fabric Latency
| Observation | Value | Impact |
|-------------|-------|--------|
| BatchTimeout dominance | 2,051 ms at 2s, 256 ms at 200ms | Single-transaction latency is determined by timeout, not endorsement |

**Mitigation:** Report at multiple BatchTimeout values.

### ML Training
| Observation | Value | Impact |
|-------------|-------|--------|
| Cross-validation variance | 2-3% (ROC-AUC) | 50-fold CV provides reliable estimates |

**Mitigation:** All results report mean ± std; significance tested with Nadeau-Bengio correction.

---

## 6. Result File Inventory

All result files are in `results/`:

| File | Contents |
|------|----------|
| `canonical_split.json` | Train/val/test customer IDs |
| `model_tuning_v2.json` | 50-fold CV results for all models |
| `significance_corrected.json` | Nadeau-Bengio corrected p-values |
| `feature_set_significance.json` | FS comparison with p-values |
| `fairness_full_table_t60.json` | Fairness metrics at multiple thresholds |
| `calibration_methodology_t58.json` | FNR gap curve, isotonic calibration |
| `constraint_counts.json` | Circuit constraint counts |
| `integration_demo_t61.json` | End-to-end latency decomposition |
| `leakage_5way.json` | 5-way partition entropy |
| `throughput_t62.json` | MMC sweep with 3 runs each |
| `batch_config_sweep.json` | BatchTimeout latency sweep |
| `lr_model_coefficients.json` | Trained LR model weights |
| `FINAL_TABLES.md` | All dissertation tables |
| `SUMMARY.md` | Plain-language result summaries |

---

## 7. Verification Checklist

To verify reproduction:

- [ ] All result files exist in `results/`
- [ ] Table 4.1 ROC-AUC matches: LR 0.6957, RF 0.6980, XGB 0.6998
- [ ] Table 4.2 regularity vs magnitude: +8.3 pp, p < 0.0001
- [ ] Table 4.3 FPR disparity: Savings 27.2%, Other 10.2%, ratio 2.7×
- [ ] Table 4.4 trade-off: 5.5% profit cost (292 → 276) for 10.9 pp FPR reduction
- [ ] Table 4.5 FNR gap range: 9.2% (min at FPR 0.07) to 36.8% (max at FPR 0.29)
- [ ] Table 4.6 constraints: 573 baseline, 576 banded
- [ ] Table 4.7 leakage: H = 1.99 bits
- [ ] Table 4.8 throughput: 119-133 TPS (MMC 10-50)
- [ ] Table 4.9 latency: 2,051 ms at 2s → 256 ms at 200ms (8× reduction)
- [ ] Table 4.10 end-to-end: 643 ms approved, 395 ms rejected

---

*Last updated: 2026-08-29*
