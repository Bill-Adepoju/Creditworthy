# Final Tables for Chapters 4 and 5

> All tables state hardware, seed, split, and source result file.
> Hardware: AMD Ryzen 7 4800H (8 cores / 16 threads), 32 GB RAM, Windows 10, Docker Desktop.
> Seed: 42. Split: Train 2,800 / Validation 700 / Test 876 (canonical_split.json).

---

## Table 4.1: Model Comparison (ROC-AUC)

**Source:** `model_tuning_v2.json`, `significance_corrected.json`
**CV:** 5-fold × 10 repeats = 50 folds
**Significance:** Nadeau-Bengio corrected paired t-test

| Model | ROC-AUC (mean ± std) | PR-AUC (mean ± std) | Overfit Gap | vs LR (p-value) |
|-------|---------------------|---------------------|-------------|-----------------|
| LogisticRegression | 0.6957 ± 0.022 | 0.4256 ± 0.032 | 1.4% | — |
| RandomForest (tuned) | 0.6980 ± 0.021 | 0.4347 ± 0.031 | 17.4% | 0.758 (NS) |
| XGBoost (tuned) | 0.6998 ± 0.022 | 0.4348 ± 0.032 | 10.6% | 0.578 (NS) |

**Finding:** All models statistically indistinguishable under corrected test (p > 0.05). LR recommended due to 7.5× smaller overfit gap and regulatory interpretability.

**Best XGB params:** max_depth=2, reg_lambda=2.0 — confirms near-additive signal at this data scale.

---

## Table 4.2: Feature Set Comparison

**Source:** `feature_set_significance.json`
**CV:** 5-fold × 10 repeats = 50 folds
**Significance:** Nadeau-Bengio corrected

| Feature Set | N Features | ROC-AUC (mean ± std) | vs Magnitude (p) | vs Regularity (p) |
|-------------|------------|---------------------|------------------|-------------------|
| Regularity | 26 | 0.6927 ± 0.021 | **< 0.0001** | — |
| Magnitude | 24 | 0.6098 ± 0.025 | — | < 0.0001 |
| Full | 32 | 0.6957 ± 0.022 | < 0.0001 | 0.207 (NS) |

**Headline finding:** FS_regularity beats FS_magnitude by **8.3 percentage points** (p < 0.0001). Adding magnitude features to regularity (→ Full) provides no significant improvement.

**95% CI for regularity vs magnitude:** [+6.1 pp, +10.5 pp]

---

## Table 4.3: Fairness by Subgroup (bank_account_type, n ≥ 30 only)

**Source:** `fairness_full_table_t60.json`, `calibration_methodology_t58.json`
**Positive class:** target = 1 = DEFAULT (Bad)
**Threshold:** 0.53 (profit-optimal)

| Group | N | Base Rate | Approval Rate | FPR | FNR |
|-------|---|-----------|---------------|-----|-----|
| Savings | 517 | 24.0% | 63.2% | 27.2% | 33.1% |
| Other | 132 | 10.6% | 88.6% | 10.2% | 78.6% |

**Disparity ratios:**
- FPR ratio (Savings/Other): **2.7×**
- Base rate ratio: 2.26×

**Interpretation:** Savings holders who would have repaid are rejected at 27.2% vs 10.2% for Other — a 2.7× disparity in wrongful rejection. Because FPR conditions on actual repayment outcome, this gap is not explained by the groups' differing default rates. It is, however, consistent with the impossibility result demonstrated in Table 4.5: where base rates differ, no calibrated classifier can equalise both error rates. The disparity is therefore structural rather than a modelling defect — which constrains what can be remedied, but does not make the harm to wrongly-rejected borrowers any less real.

**Coverage note:** Unknown bank_account_type (n = 215) is excluded as a missing-data category rather than a demographic group. Fairness is therefore assessed on 649 of 876 test borrowers (74%). This limitation — that nearly a quarter of the population cannot be audited for fairness — is itself evidence of the data gaps the framework exists to address. Discussed further in Chapter 5.

---

## Table 4.4: Fairness–Profit Trade-off at Two Thresholds

**Source:** `fairness_full_table_t60.json`
**Profit model:** Revenue = 1.0 per performing, LGD = 3.0

| Threshold | Group | FPR | FNR | Approval Rate | Profit |
|-----------|-------|-----|-----|---------------|--------|
| **0.53** (profit-optimal) | Savings | 27.2% | 33.1% | 63.2% | 163 |
| | Other | 10.2% | 78.6% | 88.6% | 73 |
| | **Overall** | 23.6% | 40.3% | 68.5% | **292** |
| **0.62** (fairness) | Savings | 16.3% | 46.8% | 74.9% | 155 |
| | Other | 2.5% | **100.0%** | 97.7% | 73 |
| | **Overall** | 12.4% | 56.5% | 80.8% | **276** |

**Trade-off:** Moving from 0.53 to 0.62 costs 5.5% profit (16 units) but reduces FPR_Savings by 10.9 pp. However, FNR_Other reaches 100% — every Other defaulter is approved.

---

## Table 4.5: FNR Gap Curve (Chouldechova/Kleinberg Impossibility)

**Source:** `calibration_methodology_t58.json`
**Calibration:** Isotonic regression via CalibratedClassifierCV(cv=5), ECE = 0.037

| Target FPR | Thresh (Savings) | Thresh (Other) | FNR Savings | FNR Other | FNR Gap |
|------------|------------------|----------------|-------------|-----------|---------|
| 0.05 | 0.424 | 0.261 | 73.4% | 85.7% | 12.3% |
| 0.07 | 0.404 | 0.246 | 69.4% | 78.6% | **9.2%** (min) |
| 0.15 | 0.330 | 0.197 | 56.5% | 78.6% | 22.1% |
| 0.24 | 0.241 | 0.182 | 38.7% | 71.4% | 32.7% |
| 0.29 | 0.217 | 0.168 | 34.7% | 71.4% | **36.8%** (max) |
| 0.33 | 0.207 | 0.158 | 28.2% | 64.3% | 36.1% |

**Resolution caveat:** Other has only 14 actual defaulters, so FNR_Other can only take values k/14 (step size = 7.14 pp). The minimum observed gap (9.2%) is ~1.3 steps. The FNR gap curve cannot detect gaps below ~7 pp due to quantization.

**Contrast:** FPR is computed on 118 non-defaulters with step size 0.85 pp — far better resolved.

**Finding:** FNR gap is non-zero at every FPR level tested, consistent with the impossibility result.

---

## Table 4.6: ZK Circuit Metrics

**Source:** `constraint_counts.json`, `integration_demo_t61.json`
**Tools:** circom 2.2.3, snarkjs 0.7.6, circomlib 2.0.5

| Metric | Baseline Circuit | Banded Circuit | Delta |
|--------|-----------------|----------------|-------|
| Constraints | 573 | 576 | +3 (0.5%) |
| Private inputs | 2 (score, salt) | 2 | — |
| Public inputs | 2 (commitment, threshold) | 2 | — |

| Operation | Mean (ms) | P95 (ms) | Notes |
|-----------|-----------|----------|-------|
| Proof generation | 125.2 | 186.2 | n=19, cold-start excluded |
| Proof verification | 12.5 | 17.9 | n=20 |
| Cold-start proof | 506.9 | — | WASM warmup, single occurrence |

**Proof size:** ~720 bytes (Groth16)

---

## Table 4.7: Privacy Leakage (5-Way Partition)

**Source:** `leakage_5way.json`
**Bands:** {400, 550, 700, 850}

| Partition | Count | Share | Cumulative |
|-----------|-------|-------|------------|
| < 400 (no proof possible) | 200 | 22.8% | 22.8% |
| 400–550 | 186 | 21.2% | 44.0% |
| 550–700 | 352 | 40.2% | 84.2% |
| 700–850 | 123 | 14.0% | 98.2% |
| ≥ 850 | 15 | 1.7% | 100% |

| Leakage Measure | Entropy (bits) |
|-----------------|----------------|
| Full band membership (H_5way) | **1.99** |
| Binary proof signal only | 0.78 |
| Maximum possible (5 uniform) | 2.32 |

**Interpretation:** With 4 threshold bands, borrowers are partitioned into 5 groups. Full band membership reveals H = 1.99 bits. The proof/no-proof binary signal alone reveals 0.78 bits, dominated by the 22.8% who cannot generate any proof.

---

## Table 4.8: Fabric Throughput (MaxMessageCount Sweep)

**Source:** `throughput_t62.json`
**Configuration:** Single orderer, 3 endorsing peers, BatchTimeout = 2s
**Runs:** 3 per configuration

| MMC | Mean TPS | Min | Max | Range (%) |
|-----|----------|-----|-----|-----------|
| 10 | 123.02 | 119.14 | 125.02 | 4.8% |
| 50 | 129.98 | 128.00 | 133.45 | 4.2% |
| 100 | 33.73 | — | — | — |
| 500 | 33.71 | — | — | — |

**Analysis:**
- MMC 10 vs 50 difference: 5.4% (p ≈ 0.06, marginal at n=3)
- **Throughput ceiling: ~119–133 TPS** for single-orderer deployment
- **Starvation at MMC ≥ 100:** Throughput collapses to ~34 TPS (blocks cut by 2s timeout, not message count)

**Practical conclusion:** MaxMessageCount tuning buys roughly 5%, not an order of magnitude. Single-orderer is the binding constraint.

---

## Table 4.9: Fabric Latency (BatchTimeout Sweep)

**Source:** `batch_config_sweep.json`
**Test:** Sequential single-transaction latency (idle network)
**n:** 20 transactions per configuration

| BatchTimeout | Mean Latency (ms) | P50 | P95 | Reduction vs 2s |
|--------------|-------------------|-----|-----|-----------------|
| 2s (default) | 2,051 | 2,050 | 2,109 | — |
| 500ms | 568 | 561 | 609 | 3.6× |
| 200ms | **256** | 252 | 294 | **8.0×** |

**Finding:** Single-transaction latency is dominated by BatchTimeout. Reducing from 2s to 200ms cuts latency 8×. This explains why SDK gave only 1.26× speedup on writes — the wait is structural.

---

## Table 4.10: End-to-End Latency Decomposition

**Source:** `integration_demo_t61.json`
**Configuration:** BatchTimeout = 200ms, 25 borrowers

### Approved Path (n=16)

| Layer | Components | Mean (ms) | % of Total |
|-------|------------|-----------|------------|
| L1 (ML) | consent + features + inference + commitment | 0.29 | 0.0% |
| L2 (Blockchain) | anchor + query + repayment_record | 505.35 | 78.6% |
| L3 (ZK) | proof_generation + verification | 137.64 | 21.4% |
| **Total** | | **643.27** | 100% |

### Rejected Path (n=4)

| Layer | Components | Mean (ms) | % of Total |
|-------|------------|-----------|------------|
| L1 (ML) | consent + features + inference + commitment | 0.29 | 0.1% |
| L2 (Blockchain) | anchor + query only | 256.88 | 65.0% |
| L3 (ZK) | proof_generation + verification | 137.64 | 34.9% |
| **Total** | | **394.81** | 100% |

### Stage Detail (Approved)

| Stage | n | Mean (ms) |
|-------|---|-----------|
| consent | 25 | 0.07 |
| feature_engineering | 25 | 0.02 |
| ml_inference | 25 | 0.01 |
| commitment | 20 | 0.18 |
| ledger_anchor | 20 | 248.6 |
| loan_query | 20 | 8.3 |
| proof_generation* | 19 | 125.2 |
| proof_verification | 20 | 12.5 |
| repayment_record | 16 | 248.5 |

*Cold-start proof (506.9ms) excluded; remaining 19 averaged 125ms.

**Note on feature_engineering (0.02 ms):** This measures a feature-store read, not raw feature computation. Features are precomputed offline from historical transaction data. The batch pipeline for 4,376 borrowers completes in ~2 seconds; the per-request path reads cached values.

**RQ4 Answer:** A complete privacy-preserving credit decision takes **643 ms** (approved) or **395 ms** (rejected). L2 (blockchain) dominates at 65–79%. Cryptographic privacy (L3) costs 21–35% of decision latency.

---

## Summary of Key Findings

| Research Question | Finding | Table |
|-------------------|---------|-------|
| Model selection | All models statistically indistinguishable; LR recommended | 4.1 |
| Feature sets | Regularity beats magnitude by 8.3 pp (p < 0.0001) | 4.2 |
| Fairness | FPR disparity 2.7× at profit-optimal threshold; impossibility result demonstrated | 4.3, 4.5 |
| Privacy leakage | 1.99 bits via 5-way partition | 4.7 |
| ZK overhead | 125ms proof gen, 12.5ms verify, 576 constraints | 4.6 |
| Fabric throughput | 119–133 TPS (single orderer) | 4.8 |
| Fabric latency | 256ms at BatchTimeout=200ms (8× improvement) | 4.9 |
| End-to-end latency | 643ms approved, 395ms rejected | 4.10 |
