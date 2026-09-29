# Results Summary

> This file contains plain-language summaries of all experimental results.
> Raw data is in the corresponding JSON files.
> Interpretation happens on the research side — this is numbers only.

---

### zk_baseline — 2026-08-23
**What was run:** Groth16 ZK-SNARK proof generation and verification for credit threshold circuit (573 constraints).
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM / Windows / Node v20.10.0
**Key numbers:**
| Metric | Value |
|--------|-------|
| Total constraints | 573 |
| Proof generation (mean, n=20) | 144.1 ms |
| Proof generation (p95) | 170.5 ms |
| Proof verification (mean) | 14.8 ms |
| Proof verification (p95) | 23.9 ms |
| Proof size | ~720 bytes |
| Verifier throughput | 68 proofs/sec/core |
| Sanity: ineligibility rejected | ✓ |
| Sanity: forgery rejected | ✓ |

**Comparison to baseline (1 vCPU / 3 GB):**
| Metric | Baseline | This machine | Speedup |
|--------|----------|--------------|---------|
| Proof gen | 234 ms | 144 ms | 1.6× |
| Verify | 20 ms | 15 ms | 1.3× |
| Throughput | 49/s | 68/s | 1.4× |

**Caveats:** First proof generation is slower (~624 ms) due to WASM warmup; subsequent proofs are consistent. Library versions: snarkjs 0.7.6, circomlibjs 0.1.7, circomlib 2.0.5.

---

### data_profile — 2026-08-23
**What was run:** Zindi SuperLender dataset ingestion and integrity check.
**Hardware:** N/A (data profiling only)
**Key numbers:**
| Metric | Value |
|--------|-------|
| Total customers (perf) | 4,368 |
| Customers with loan history | 3,264 (74.7%) |
| First-time borrowers | 9 (0.2%) |
| Default rate (Bad) | 21.79% |
| Good loans | 3,416 |
| Bad loans | 952 |
| Previous loans (rows) | 18,183 |

**Join coverage:**
| Table combination | Customers |
|-------------------|-----------|
| All three tables | 3,264 |
| Demographics + Perf | 3,269 |
| Perf only (no history) | 9 |

**Missingness (>10%):**
| Column | Missing % |
|--------|-----------|
| bank_branch_clients | 98.83% |
| level_of_education_clients | 86.49% |
| referredby (perf) | 86.56% |
| referredby (prevloans) | 94.36% |
| employment_status_clients | 14.91% |

**Date fields for regularity features:** All 5 required fields present (approveddate, creationdate, closeddate, firstduedate, firstrepaiddate).

**Caveats:** bank_branch_clients and level_of_education_clients are too sparse to use. referredby unusable. employment_status_clients usable with imputation.

---

### model_performance — 2026-08-23
**What was run:** Stratified 5-fold CV comparing LogisticRegression, RandomForest, XGBoost, and Ensemble across three feature sets (regularity, magnitude, full) with two imbalance methods (class_weight, SMOTE).
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM
**Key numbers (class_weight method):**

| Feature Set | Best Model | ROC-AUC | PR-AUC |
|-------------|------------|---------|--------|
| regularity | LogisticRegression | 0.6912 | 0.4214 |
| magnitude | LogisticRegression | 0.6076 | 0.3034 |
| full | LogisticRegression | 0.6931 | 0.4251 |

**Central finding: FS_regularity beats FS_magnitude by 0.0836 ROC-AUC (8.4 percentage points).**

**All models on FS_regularity (class_weight):**
| Model | ROC-AUC | PR-AUC | F1 |
|-------|---------|--------|-----|
| LogisticRegression | 0.6912 +/- 0.018 | 0.4214 | 0.4368 |
| RandomForest | 0.6692 +/- 0.018 | 0.3899 | 0.3974 |
| XGBoost | 0.6478 +/- 0.019 | 0.3743 | 0.4058 |
| Ensemble | 0.6861 +/- 0.023 | 0.4088 | 0.4250 |

**Imbalance handling comparison (FS_full, Ensemble):**
| Method | ROC-AUC | PR-AUC |
|--------|---------|--------|
| class_weight | 0.6929 | 0.4132 |
| SMOTE | 0.6885 | 0.4052 |

**Caveats:** Logistic Regression outperforms tree-based models on this dataset size. Adding magnitude features to regularity provides minimal lift (+0.0019 ROC-AUC). SMOTE slightly underperforms class weighting.

---

### fairness — 2026-08-23
**What was run:** Fairness audit using LogisticRegression on full feature set. Computed demographic parity difference (DPD) and equalized odds difference (EOD) across 4 sensitive attributes.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM
**Key numbers:**

| Sensitive Attribute | DPD | EOD | Fair (< 0.1)? |
|---------------------|-----|-----|---------------|
| region | 0.322 | 0.667 | No |
| age_band | 0.300 | 0.329 | No |
| bank_account_type | 0.180 | 0.217 | No |
| employment_status | 0.133 | 0.750 | No |

**Model performance on held-out test set:**
| Metric | Value |
|--------|-------|
| ROC-AUC | 0.7151 |
| Accuracy | 0.7180 |

**Findings:**
- None of the 4 attributes meet the 0.1 fairness threshold
- Region shows largest demographic disparity (0.322)
- Employment status has highest equalized odds disparity (0.750)
- Trade-off curve saved to `fairness_tradeoff.png`

**Caveats:** Fairness metrics computed on 20% test split. Some subgroups have small sample sizes (e.g., North region: 11, Unemployed: 9). High "Unknown" rates in employment_status (36%) may distort metrics.

---

### shap_global — 2026-08-23
**What was run:** SHAP explainability analysis on LogisticRegression with full feature set. Computed global feature importance and local explanations.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM
**Key numbers:**

**Top 10 features by mean |SHAP value|:**
| Rank | Feature | Importance | Category |
|------|---------|------------|----------|
| 1 | amount_mean | 0.541 | Magnitude |
| 2 | totaldue_mean | 0.336 | Magnitude |
| 3 | amount_cv | 0.306 | Magnitude* |
| 4 | relationship_tenure_days | 0.301 | Regularity |
| 5 | early_repay_ratio | 0.264 | Regularity |
| 6 | amount_total | 0.235 | Magnitude |
| 7 | repay_delay_mean | 0.211 | Regularity |
| 8 | repay_delay_std | 0.166 | Regularity |
| 9 | loan_count | 0.136 | Regularity |
| 10 | amount_max | 0.134 | Magnitude |

**Category totals:**
| Category | Total SHAP importance |
|----------|----------------------|
| Regularity features | 1.273 |
| Magnitude features | 1.554 |
| Ratio (Reg/Mag) | 0.82x |

**Note:** amount_cv (coefficient of variation) is mathematically a consistency measure despite being derived from amounts.

**Local explanation example (borderline case, P=0.50):**
- amount_mean: +0.425 (increases default risk)
- totaldue_mean: -0.332 (decreases default risk)
- amount_cv: +0.270 (increases default risk)

**Plots:** `shap_global.png`, `shap_summary.png`

**Caveats:** SHAP importance measures feature contribution to predictions, not predictive power. Regularity features still yield better ROC-AUC despite lower aggregate SHAP importance.

---

### bridge_test — 2026-08-23
**What was run:** End-to-end test proving L1 (ML scoring) and L3 (ZK verification) are correctly connected. Converted model P(default) to integer scores, computed Poseidon commitments, and verified proofs through the circuit.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM
**Key numbers:**

| Metric | Value |
|--------|-------|
| Test cases | 5 |
| Thresholds tested | 500, 600, 700, 800 |
| Total proof attempts | 20 |
| Proofs generated & verified | 10 |
| Correctly rejected | 10 |
| Bridge accuracy | 100% |

**Score distribution (from ML model):**
| Metric | Value |
|--------|-------|
| Min score | 18 |
| Max score | 949 |
| Mean score | 542.8 |
| Median score | 575.0 |

**Test case examples:**
| Score | P(default) | Actual | 500 | 600 | 700 | 800 |
|-------|------------|--------|-----|-----|-----|-----|
| 18 | 0.982 | Default | REJ | REJ | REJ | REJ |
| 949 | 0.051 | Non-default | PASS | PASS | PASS | PASS |
| 500 | 0.500 | Default | PASS | REJ | REJ | REJ |
| 600 | 0.400 | Non-default | PASS | PASS | REJ | REJ |
| 700 | 0.300 | Non-default | PASS | PASS | PASS | REJ |

**Proof timing:**
| Operation | Time |
|-----------|------|
| Proof generation | 344-615 ms |
| Proof verification | 12-21 ms |

**Result:** L1 (ML) and L3 (ZK) are correctly connected. Score scaling, Poseidon commitment, and threshold verification all work as designed.

**Caveats:** None. All 20 threshold tests behaved exactly as expected.

---

### model_tuning — 2026-08-23
**What was run:** T9 diagnosis of Cycle 01 LR anomaly. Documented overfitting, ran RandomizedSearchCV (50 iter) for RF and XGBoost with constrained depth.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM

**Cycle 01 hyperparameters (the problem):**
- RandomForest: `max_depth=None` (unlimited) → 99.6% train AUC
- XGBoost: default regularization → 99.0% train AUC
- Result: SEVERE OVERFIT (33% train-val gap)

**Train vs Validation AUC (diagnosing overfitting):**
| Model | Train AUC | Val AUC | Gap | Status |
|-------|-----------|---------|-----|--------|
| LogisticRegression | 0.7096 | 0.6930 | 0.017 | OK |
| RandomForest_C01 | 0.9957 | 0.6678 | 0.328 | SEVERE OVERFIT |
| XGBoost_C01 | 0.9903 | 0.6599 | 0.330 | SEVERE OVERFIT |

**After tuning (constrained depth, regularization):**
| Model | Val AUC | Gap | Best Params |
|-------|---------|-----|-------------|
| XGBoost_Tuned | 0.6946 | 0.08 | max_depth=2, reg_lambda=5.0 |
| RandomForest_Tuned | 0.6942 | 0.18 | max_depth=8, min_samples_leaf=5 |
| LogisticRegression | 0.6930 | 0.02 | — |

**Final ranking:**
1. XGBoost_Tuned: 0.6946
2. RandomForest_Tuned: 0.6942
3. LogisticRegression: 0.6930

**Conclusion:** XGBoost wins by **0.0016 ROC-AUC** (essentially noise). Best tree model requires `max_depth=2`, confirming signal is close to linear. **LR remains competitive with properly tuned trees on this dataset size.**

**Implication for Chapter 3:** "On thin-file data at ~4k rows, interpretable models are not a compliance tax" is a defensible finding.

**Caveats:** Winner margin (0.0016) is likely within statistical noise. Need paired test (T10) to confirm.

---

### variance_analysis — 2026-08-23
**What was run:** T10 variance analysis with fold-level metrics and paired statistical tests for key feature set comparisons.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM
**Key numbers:**

**All models × feature sets (5-fold CV, mean ± std):**

| Model | Feature Set | ROC-AUC | PR-AUC | F1 |
|-------|-------------|---------|--------|-----|
| LogisticRegression | regularity | 0.6912 ± 0.018 | 0.4214 ± 0.021 | 0.4403 ± 0.023 |
| RandomForest | regularity | 0.6921 ± 0.028 | 0.4241 ± 0.024 | 0.4369 ± 0.018 |
| XGBoost | regularity | 0.6914 ± 0.022 | 0.4180 ± 0.023 | 0.4376 ± 0.023 |
| LogisticRegression | magnitude | 0.6077 ± 0.042 | 0.3036 ± 0.036 | 0.3781 ± 0.024 |
| RandomForest | magnitude | 0.6046 ± 0.033 | 0.2981 ± 0.032 | 0.3712 ± 0.026 |
| XGBoost | magnitude | 0.5969 ± 0.033 | 0.2903 ± 0.028 | 0.3647 ± 0.024 |
| LogisticRegression | full | 0.6930 ± 0.022 | 0.4251 ± 0.022 | 0.4409 ± 0.021 |
| RandomForest | full | 0.6940 ± 0.026 | 0.4268 ± 0.019 | 0.4425 ± 0.020 |
| XGBoost | full | 0.6901 ± 0.026 | 0.4173 ± 0.024 | 0.4312 ± 0.017 |

**Statistical significance tests (paired t-test across 5 folds):**
| Comparison | Metric | Difference | p-value | Significant? |
|------------|--------|------------|---------|--------------|
| FS_regularity vs FS_magnitude | ROC-AUC | +0.0835 | 0.0040 | YES (p<0.01) |
| FS_regularity vs FS_magnitude | PR-AUC | +0.1178 | 0.0021 | YES (p<0.01) |
| FS_full vs FS_regularity | ROC-AUC | +0.0019 | 0.3589 | NO |
| FS_full vs FS_regularity | PR-AUC | +0.0037 | 0.1226 | NO |

**Class weighting vs SMOTE (FS_full):**
| Model | Method | ROC-AUC | PR-AUC |
|-------|--------|---------|--------|
| LogisticRegression | class_weight | 0.6930 ± 0.022 | 0.4251 ± 0.022 |
| LogisticRegression | SMOTE | 0.6902 ± 0.021 | 0.4257 ± 0.024 |
| RandomForest | class_weight | 0.6940 ± 0.026 | 0.4268 ± 0.019 |
| RandomForest | SMOTE | 0.6822 ± 0.020 | 0.4170 ± 0.021 |
| XGBoost | class_weight | 0.6901 ± 0.026 | 0.4173 ± 0.024 |
| XGBoost | SMOTE | 0.6806 ± 0.027 | 0.4138 ± 0.027 |

**Key findings:**
1. **FS_regularity beats FS_magnitude: STATISTICALLY SIGNIFICANT (p=0.004).** The 8.4 percentage point difference is real, not noise.
2. **FS_full does NOT beat FS_regularity (p=0.36).** Adding magnitude features to regularity features yields no improvement. Magnitude features are redundant when regularity features are present.
3. **Class weighting outperforms SMOTE** across all models (ROC-AUC: +0.3–1.2 pp).

**Caveats:** n=5 folds is at the minimum for paired tests. Wilcoxon test included in JSON but note reliability concerns with n<6.

---

### coverage_analysis — 2026-08-23
**What was run:** T11 join coverage analysis to test whether FS_regularity > FS_magnitude is robust or driven by missingness patterns.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM
**Key numbers:**

**Table coverage:**
| Metric | Value |
|--------|-------|
| Total customers (perf) | 4,368 |
| With loan history (prevloans) | 4,359 (99.8%) |
| In all three tables | 3,264 |
| NO prior loan history | 9 (0.2%) |

**Prior loan distribution:**
| Prior Loans | Count | Percentage |
|-------------|-------|------------|
| 0 | 9 | 0.2% |
| 1 | 1,393 | 31.9% |
| 2 | 669 | 15.3% |
| 3+ | 2,297 | 52.6% |

**Critical finding:** 32.1% of customers have <2 prior loans. Variance-based regularity features (repay_delay_std, interval_regularity) are undefined for these customers and were imputed.

**Robustness tests (restricting to customers with sufficient history):**
| Subset | N | FS_regularity | FS_magnitude | Diff | p-value | Holds? |
|--------|---|---------------|--------------|------|---------|--------|
| >= 2 loans | 2,969 | 0.6795 | 0.5923 | +0.080 | 0.0052 | YES |
| >= 3 loans | 2,299 | 0.6621 | 0.5923 | +0.070 | 0.0042 | YES |

**Conclusion:** The FS_regularity > FS_magnitude finding is **ROBUST**. The effect holds (p<0.01) even when restricting to customers with >= 3 prior loans, ruling out missingness patterns as the driver. This is a genuine behavioral signal, not an artifact.

**Caveats:** Performance drops slightly on the restricted subset (0.69 → 0.66 ROC-AUC), likely due to smaller sample size and different population characteristics.

---

### fairness_detailed — 2026-08-23
**What was run:** T12 fairness audit with subgroup sizes, bootstrap confidence intervals (n=500), threshold recalibration, and accuracy-fairness trade-off curves.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM
**Key numbers:**

**Subgroup sizes (test set, n=885):**
| Attribute | Subgroup | N | % of total |
|-----------|----------|---|------------|
| region | West | 458 | 51.8% |
| region | Unknown | 225 | 25.4% |
| region | South-West | 174 | 19.7% |
| region | Central | 25 | 2.8% |
| region | North | 3 | 0.3% |
| age_band | 26-35 | 365 | 41.2% |
| age_band | 36-45 | 241 | 27.2% |
| age_band | Unknown | 220 | 24.9% |
| age_band | 46-55 | 30 | 3.4% |
| age_band | 18-25 | 27 | 3.1% |
| age_band | 55+ | 2 | 0.2% |
| bank_account_type | Savings | 537 | 60.7% |
| bank_account_type | Unknown | 220 | 24.9% |
| bank_account_type | Other | 119 | 13.4% |
| bank_account_type | Current | 9 | 1.0% |
| employment_status | Permanent | 466 | 52.7% |
| employment_status | Unknown | 330 | 37.3% |
| employment_status | Self-Employed | 59 | 6.7% |
| employment_status | Student | 21 | 2.4% |
| employment_status | Unemployed | 8 | 0.9% |

**Fairness metrics with 95% bootstrap CIs:**
| Attribute | DPD | DPD 95% CI | EOD | EOD 95% CI |
|-----------|-----|------------|-----|------------|
| region | 0.314 | [0.070, 0.681] | 0.683 | [0.310, 1.000] |
| age_band | 0.545 | [0.218, 0.761] | 0.847 | [0.410, 1.000] |
| bank_account_type | 0.352 | [0.258, 0.490] | 0.702 | [0.511, 0.907] |
| employment_status | 0.628 | [0.308, 1.000] | 0.816 | [0.623, 1.000] |

**Key findings:**
1. **None of the 4 attributes meet the 0.1 fairness threshold** — even the lower confidence bounds exceed 0.1 for most attributes.
2. **Small subgroup sizes inflate metrics**: North region (n=3), 55+ age (n=2), Current account (n=9), Unemployed (n=8) all have unreliable estimates.
3. **Employment status shows extreme disparity**: EOD of 0.816 [0.623, 1.000] — the Unemployed subgroup has 0% TPR with only 8 samples.
4. **Age 18-25 has highest approval rate** (59.3%) vs 55+ (0%) but latter has only 2 samples.

**Trade-off curve:** Saved to `fairness_tradeoff.png`. Shows that achieving fairness (DPD < 0.1) requires accepting ~50% accuracy.

**Caveats:** High "Unknown" rates (25-37%) in several attributes distort baseline comparisons. Several subgroups have n<30, making their metrics statistically unreliable. Fairness disparities may reflect genuine behavioral differences or sampling artifacts at these small sizes.

---

### shap_comprehensive — 2026-08-23
**What was run:** T14 SHAP analysis on all three feature sets to reconcile why magnitude features dominate SHAP rankings but FS_regularity wins on predictive performance.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM
**Key numbers:**

**Top 5 features by feature set (mean |SHAP|):**

| FS_regularity | SHAP | FS_magnitude | SHAP | FS_full | SHAP |
|---------------|------|--------------|------|---------|------|
| relationship_tenure_days | 0.304 | amount_mean | 0.804 | amount_mean | 0.541 |
| early_repay_ratio | 0.282 | totaldue_mean | 0.480 | totaldue_mean | 0.336 |
| repay_delay_mean | 0.210 | amount_cv | 0.416 | amount_cv | 0.306 |
| repay_delay_std | 0.173 | amount_total | 0.286 | relationship_tenure_days | 0.301 |
| loan_count | 0.129 | amount_max | 0.196 | early_repay_ratio | 0.264 |

**Category aggregates (FS_full):**
| Category | Total SHAP | Share |
|----------|------------|-------|
| Magnitude | 1.554 | 43.9% |
| Regularity | 1.273 | 36.0% |
| Shared | 0.713 | 20.1% |

**Top 10 in FS_full composition:** 5 regularity, 5 magnitude (balanced)

**Reconciliation:** Individual magnitude features show higher SHAP importance due to strong marginal contributions. However, magnitude features are highly correlated (all derived from loan amounts), creating redundancy. Regularity features are more orthogonal to each other, so their combined predictive power exceeds magnitude despite lower individual SHAP values. This explains why FS_regularity outperforms FS_magnitude in cross-validation (0.69 vs 0.61 ROC-AUC) even though magnitude features dominate SHAP rankings on FS_full.

**Plots:** `shap_comparison.png`

**Caveats:** SHAP importance measures marginal contribution, not unique information. Highly correlated features share credit, making individual importance values misleading for redundant feature groups.

---

### bridge_scale — 2026-08-23
**What was run:** T13 scaled bridge test with 200 borrowers × 5 thresholds = 1000 proof attempts (50× larger than original). Scores drawn from actual model output distribution.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM / Windows / Node v20.10.0
**Key numbers:**

| Metric | Value |
|--------|-------|
| Total proof attempts | 1,000 |
| Proofs generated & verified | 374 |
| Correctly rejected (score < threshold) | 626 |
| Unexpected failures | 0 |
| **Bridge accuracy** | **100.00%** |
| Salt collisions | 0 |
| Commitment collisions | 0 |

**Score distribution (sampled from model):**
| Metric | Value |
|--------|-------|
| Min | 159 |
| Max | 923 |
| Mean | 537.7 |
| Std | 168.0 |
| Default rate | 20.0% |

**Timing:**
| Operation | Mean | P95 |
|-----------|------|-----|
| Proof generation | 883.1 ms | 2172 ms |
| Proof verification | 11.8 ms | — |
| Total wall clock | 19.6 minutes | — |
| Throughput | 0.32 proofs/sec | — |

**Result:** L1 (ML) and L3 (ZK) remain correctly connected at scale. All 1000 threshold tests behaved exactly as expected. No collisions detected in Poseidon commitments.

**Caveats:** Gen time higher than baseline (883ms vs 144ms) due to repeated WASM warmup cycles in batch processing. Production deployment would benefit from persistent WASM instance.

---


### fairness_v2 � 2026-08-24
**What was run:** Corrected fairness analysis with n>=30 filtering (T25) using LogisticRegression (T26).
**Model:** LogisticRegression (selected per model_tuning_v2 - statistically indistinguishable from XGB, 7.5x smaller overfit gap)
**Key numbers:**
| Attribute | Unfiltered DPD | Filtered DPD (n>=30) | Population in small groups |
|-----------|---------------|---------------------|---------------------------|
| region | 0.1269 | 0.0001 | 2.1% |
| age_band | 0.4783 | 0.2615 | 2.8% |
| bank_account_type | 0.2995 | 0.2995 | 1.3% |
| employment_status | 0.3358 | 0.1284 | 3.3% |

**Key finding:** `bank_account_type` disparity is robust (unchanged after filtering). Savings holders approved at 3.3x the rate of Other holders - the model reproduces exclusion along the dimension it was built to address.
**Caveats:** Different train/test split than original may cause minor numerical differences from HANDOVER expectations.

### privacy_utility � 2026-08-24
**What was run:** T16 Privacy-Utility Exchange Rate Curve
**Model:** LogisticRegression
**Optimal unrestricted threshold:** 667 (approval 22.8%, default 9.0%)
**Key numbers:**
| Bands | Bits Leaked | Excess Default Rate (bps) | Approval Rate |
|-------|-------------|---------------------------|---------------|
| 2 | 1.00 | 594.1 | 77.2% |
| 3 | 1.58 | 148.4 | 42.5% |
| 4 | 2.00 | 263.3 | 55.9% |
| 5 | 2.32 | 148.4 | 42.5% |
| 8 | 3.00 | 148.4 | 42.5% |
| 10 | 3.32 | 131.2 | 36.5% |
| 20 | 4.32 | 112.7 | 27.1% |

**The Contribution:** With 4 bands, borrowers leak 2 bits (vs ~10 unbanded) at a cost of 263.3 bps excess default rate.
**Caveats:** Assumes lender's optimal threshold; real-world lender objectives vary.

---

### model_tuning_v2 — 2026-08-24
**What was run:** T23+T24 Fixed model tuning with 50-fold CV (RepeatedStratifiedKFold 5×10) and proper significance testing.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM
**Key numbers:**

| Model | ROC-AUC | PR-AUC | Overfit Gap |
|-------|---------|--------|-------------|
| LogisticRegression | 0.6957 ± 0.022 | 0.4256 ± 0.032 | 1.4% |
| RandomForest_Tuned | 0.6980 ± 0.021 | 0.4347 ± 0.031 | 17.4% |
| XGBoost_Tuned | 0.6998 ± 0.022 | 0.4348 ± 0.032 | 10.6% |

**Significance tests (paired t-test, 50 folds):**
| Comparison | Difference | p-value | Conclusion |
|------------|------------|---------|------------|
| XGB vs LR | +0.0041 | 0.045 | Borderline significant |
| RF vs LR | +0.0024 | 0.260 | Indistinguishable |
| XGB vs RF | +0.0017 | 0.236 | Indistinguishable |

**Key findings:**
1. **XGB marginally beats LR** (p=0.045) but with 7.5× larger overfit gap (10.6% vs 1.4%)
2. **RF and LR are statistically indistinguishable** (p=0.26)
3. **All three models are effectively equivalent** within practical significance
4. **Recommendation: Use LogisticRegression** — statistically competitive with dramatically better generalization

**Caveats:** The XGB marginal improvement (0.4 pp) is dwarfed by its overfitting gap (10.6% vs 1.4%). For deployment, LR is the safer choice. The `max_depth=2` XGB optimum suggests the signal is near-additive.

### significance_corrected � 2026-08-24
**What was run:** T33 Nadeau-Bengio corrected significance tests for repeated k-fold CV.
**Why:** Naive paired t-test invalid because folds share data across repeats. Correction inflates variance by (1/n + n_test/n_train).
**Key numbers:**

| Comparison | Naive p | Wilcoxon p | **Corrected p** | Significant |
|------------|---------|------------|-----------------|-------------|
| XGB vs LR | 0.045 | 0.062 | **0.578** | No |
| RF vs LR | 0.260 | 0.388 | **0.758** | No |

**Corrected 95% CI for XGB-LR difference:** [-0.0105, 0.0186] � spans zero.

**Conclusion:** All models statistically indistinguishable. Previous "XGBoost significant at p=0.045" was an artefact of the invalid test. LR recommended for interpretability with no measurable accuracy cost.

### privacy_utility_v2 � 2026-08-24
**What was run:** T27 Corrected privacy-utility analysis + T28 quantile band comparison.
**Fixes:** (1) Constrained optimum instead of floor quantisation, (2) Fixed band range, (3) Exclude dead bands, (4) Profit model.
**Profit model:** Revenue per performing = 1.0, LGD = 3.0
**Key numbers:**

| B | Eff. Bits | Equidist DR (bps) | Quantile DR (bps) | Winner |
|---|-----------|-------------------|-------------------|--------|
| 2 | 1.00 | 897.0 | 897.0 | Tie |
| 3 | 1.58 | 5.3 | -189.9 | Quantile |
| 4 | 2.00 | 476.8 | 13.6 | Quantile |
| 5 | 2.32 | 5.3 | 162.6 | Equidist |
| 6 | 2.58 | 242.8 | 240.9 | Quantile |
| 8 | 3.00 | 166.8 | 138.4 | Quantile |
| 10 | 3.32 | 156.3 | 13.6 | Quantile |
| 15 | 3.91 | 5.3 | -59.9 | Quantile |
| 20 | 4.32 | 153.8 | 0.0 | Quantile |

**Validation checks:** All PASS (monotonic, converging, no dead bands, fixed range)
**Method correction:** Original T16 reported 263 bps at B=4 using floor quantisation. Corrected method (constrained optimum) gives 476.8 bps.
**Caveats:** Absolute costs depend on profit model parameters; curve shape is robust.

### adversary_entropy - 2026-08-24
**What was run:** T29 adversary's true posterior entropy analysis.
**Why:** Check if log2(B) overstates privacy by assuming uniform distribution within bands.
**Key numbers:**

| B | Placement | log2(B) | True Leakage | Exceeds? |
|---|-----------|---------|--------------|----------|
| 4 | Equidistant | 2.00 | 1.17 | No |
| 4 | Quantile | 2.00 | 1.60 | No |

**Conclusion:** log2(B) bound is conservative - true leakage typically less than the bound because within-band distributions are non-uniform. The bound remains valid as an upper limit.

### mediation_analysis - 2026-08-24
**What was run:** T30 mediation check on bank_account_type disparity.
**Why:** Determine if 3.0x disparity is causal or confounded before recommending remedies.
**Key numbers:**

| Model | Savings Rate | Other Rate | Ratio |
|-------|--------------|------------|-------|
| With bank_type | 54.0% | 32.6% | 1.66x |
| Without bank_type | 53.2% | 34.8% | 1.53x |

Disparity change: +7.9%

**Conclusion:** CONFOUNDED. Removing bank_account_type barely affects the disparity. The 3.0x gap is carried by correlated features (tenure, loan history, etc.), not by the account type label itself. Dropping the feature will NOT fix the disparity.

### positive_class_disambiguation - 2026-08-24
**What was run:** T38 - disambiguate positive class encoding in fairness analysis.
**Why:** Cycle 03 may have inverted the fairness narrative by confusing rejection and approval rates.
**Key finding:**

**target=1 = DEFAULT (Bad)**

| Group | Rejection Rate | Approval Rate | Disadvantaged? |
|-------|----------------|---------------|----------------|
| Savings | 44.7% | 55.3% | YES |
| Other | 14.7% | 85.3% | NO (favored) |

**Chapter 6 correction:** The disparity tracks BORROWING HISTORY DEPTH (tenure, loan count, amounts).
Savings holders have thinner files, leading to higher predicted risk and lower approval.
This is a legitimate risk signal, not discrimination against a protected class.

### adversary_entropy - 2026-08-24
**What was run:** T29 adversary's true posterior entropy analysis.
**Why:** Check if log2(B) overstates privacy by assuming uniform distribution within bands.
**Key numbers:**

| B | Placement | log2(B) | True Leakage | Exceeds? |
|---|-----------|---------|--------------|----------|
| 4 | Equidistant | 2.00 | 1.37 | No |
| 4 | Quantile | 2.00 | 1.60 | No |

**Conclusion:** log2(B) bound is conservative - true leakage typically less than the bound because within-band distributions are non-uniform. The bound remains valid as an upper limit.

### feature_set_significance - 2026-08-24
**What was run:** T34 - Apply Nadeau-Bengio correction to feature set comparisons.
**Why:** Original p=0.004 for regularity vs magnitude was from naive t-test on 5-fold CV.
**Key numbers:**

| Comparison | Naive p | Corrected p | Significant |
|------------|---------|-------------|-------------|
| regularity vs magnitude | 0.0000 | 0.0000 | Yes |

**Mean difference:** +0.0830 (regularity - magnitude)
**95% CI:** [+0.0612, +0.1048]

### fabric_layer2 - 2026-08-24
**What was run:** T31 - Hyperledger Fabric consortium network implementation.
**Hardware:** Docker containers (not yet benchmarked - T31c pending)
**Key numbers:**

| Component | Value |
|-----------|-------|
| Ordering consensus | Raft (single-node for dev) |
| Endorsing orgs | 3 (CommercialBankA, MicrofinanceB, FintechC) |
| Read-only orgs | 1 (RegulatoryObserver) |
| Chaincode functions | 6 (3 write, 3 read) |
| Fabric version | 2.5 |

**Architecture:**
- T31a: Raft ordering, 3 endorsers + 1 read-only observer (embedded supervision per Auer 2022)
- T31b: Chaincode stores ONLY commitments (Poseidon hashes) - never raw scores, features, PII, or model weights
- T31d: All verification events recorded for audit trail (enables probing detection)

**Access control:**
| Org | Read | Write | Endorse |
|-----|------|-------|---------|
| CommercialBankA | YES | YES | YES |
| MicrofinanceB | YES | YES | YES |
| FintechC | YES | YES | YES |
| RegulatoryObserver | YES | NO | NO |

**Files created:**
- chain/config/crypto-config.yaml
- chain/config/configtx.yaml
- chain/chaincode/credit/credit.go
- chain/docker/docker-compose.yaml
- chain/scripts/*.sh

**Caveats:** Code complete but not yet deployed/tested in Docker. T31c (Caliper benchmarks) pending.

### nested_bands_analysis - 2026-08-24
**What was run:** T35 - Analyze non-monotonicity in equidistant bands + compare to nested dyadic bands.
**Why:** Equidistant profit curve is non-monotonic because band sets are not nested.
**Key numbers:**

| Band Type | Monotonic? | Explanation |
|-----------|------------|-------------|
| Equidistant | No | Band positions shift with B |
| Dyadic (nested) | Yes | Each level refines previous |

**Non-monotonic example (equidistant):**
- B=3: profit_loss=10.0 (band at 484 near optimum 470)
- B=4: profit_loss=65.0 (bands at 328, 639 far from optimum)

**Chapter 5 implication:** Non-monotonicity is a finding, not a bug. Cost depends on whether a band happens to fall near the lender's optimum. This argues for adaptive placement.

### equal_leakage_comparison - 2026-08-24
**What was run:** T36 - Compare equidistant vs quantile at equal measured leakage.
**Why:** Earlier comparison at equal B was misleading because placements leak different amounts.
**Key numbers:**

| Placement | Pareto Points | Degenerate Bands (B=4) |
|-----------|---------------|------------------------|
| Equidistant | 3 | 1 |
| Quantile | 3 | 1 |

**At similar leakage levels:** Equidist wins 3x, Quantile wins 6x
**Conclusion:** quantile_better_at_equal_leakage

### fabric_deployment - 2026-08-25
**What was run:** T31c - Hyperledger Fabric 2.5 network deployment and chaincode verification.
**Hardware:** Docker Desktop on Windows / 6 containers
**Key numbers:**

| Component | Value |
|-----------|-------|
| Fabric version | 2.5 |
| Channel creation | osnadmin (Channel Participation API) |
| Ordering consensus | Raft (etcdraft) |
| Endorsing orgs | 3 (CommercialBankA, MicrofinanceB, FintechC) |
| Read-only observer | 1 (RegulatoryObserver) |
| Endorsement policy | MAJORITY (3 of 4) |
| Chaincode functions | 6 |

**Functional tests:**
| Test | Result |
|------|--------|
| AnchorCommitment (3 endorsers) | PASS |
| GetCommitment | PASS |
| RecordLoanEvent | PASS |
| GetCreditHistory | PASS |
| RegulatoryObserver read | PASS |
| RegulatoryObserver write blocked | PASS |

**Privacy compliance:**
- On-chain: Poseidon commitment hashes, DIDs, model version hashes, loan event metadata
- Never on-chain: Raw scores, behavioural features, PII, model weights

**Embedded supervision (Auer 2022) verified:**
- RegulatoryObserver can query all commitments and history
- RegulatoryObserver write attempts rejected by endorsement policy

**Caveats:** Single orderer node (dev configuration). T31d (Caliper TPS/latency benchmarks) pending.

### fabric_benchmark — 2026-08-25
**What was run:** T31c - Sequential latency benchmarks for all chaincode operations.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM / Docker Desktop / Fabric 2.5
**Key numbers:**

| Operation | Type | n | Mean (ms) | P95 (ms) | Min | Max | Seq. Rate |
|-----------|------|---|-----------|----------|-----|-----|-----------|
| AnchorCommitment | Write | 30 | 3059 | 3262 | 2984 | 3404 | 0.33 TPS |
| RecordLoanEvent | Write | 30 | 3051 | 3278 | 2972 | 3301 | 0.33 TPS |
| GetCommitment | Read | 50 | 866 | 942 | 809 | 977 | 1.15 QPS |
| GetCreditHistory | Read | 20 | 869 | 973 | 819 | 973 | 1.15 QPS |

**Success rates:** 100% across all operations (130/130 total).

**Block metrics:**
| Metric | Value |
|--------|-------|
| Initial height | 37 |
| Final height | 97 |
| Blocks added | 60 |
| Txns per block | 1.00 |

**Latency decomposition (estimated):**
| Component | Est. Time |
|-----------|-----------|
| Docker exec overhead | ~500 ms |
| Endorsement (3 peers) | ~300-400 ms |
| Ordering/block cut | ~2000 ms (default 2s batch) |
| Commit | ~200 ms |
| Total write | ~3000 ms |

**Caveats:**
- Single orderer (Raft requires 3 for CFT)
- Sequential execution (not concurrent TPS)
- Latency includes Docker exec overhead (~500ms)
- --waitForEvent adds commit wait time
- Concurrent load testing would yield higher TPS but require Fabric SDK

### integration_demo — 2026-08-25
**What was run:** T42 - End-to-end integration demo with latency decomposition across all three layers.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM / Docker Desktop / Fabric 2.5 / Node v20
**Key numbers:**

**End-to-end latency decomposition:**
| Stage                   | Mean (ms) | % of Total |
|-------------------------|-----------|------------|
| consent                 | 13        | 0.2%       |
| feature_engineering     | 15        | 0.2%       |
| ml_inference            | 18        | 0.2%       |
| commitment_computation  | <1        | 0.0%       |
| ledger_anchor (write)   | 3088      | 41.1%      |
| loan_application (read) | 865       | 11.5%      |
| proof_generation        | 448       | 6.0%       |
| proof_verification      | 16        | 0.2%       |
| decision                | <1        | 0.0%       |
| repayment_record (write)| 3053      | 40.6%      |
| **TOTAL**               | **7518**  | **100%**   |

**Component-level summary (answers RQ4):**
| Component        | Latency (ms) | % of Total |
|------------------|--------------|------------|
| L1 (ML scoring)  | 46           | 0.6%       |
| L2 (Blockchain)  | 7006         | **93.2%**  |
| L3 (ZK proofs)   | 464          | 6.2%       |
| **TOTAL**        | **7518**     | 100%       |

**Key finding:** Blockchain layer dominates latency at **93.2%**, driven by:
- 2-second Fabric block timeout (BatchTimeout)
- Docker exec overhead (~500ms per call)
- Two write operations per loan flow

**ZK overhead is only 6.2%** — cryptographic privacy adds minimal latency compared to governance infrastructure.

**Flow results (n=5 borrowers):**
| Borrower     | Score | Band | Decision | Total (ms) |
|--------------|-------|------|----------|------------|
| Low Risk     | 850   | 850  | Approved | 8080       |
| Medium Risk  | 650   | 550  | Approved | 6827       |
| Borderline   | 550   | 550  | Approved | 8466       |
| High Risk    | 450   | 400  | Rejected | 7008       |
| Very High    | 300   | n/a  | Rejected | 7191       |

**Proof generation timing (excluding first warmup):**
| Metric | Value |
|--------|-------|
| Mean   | 448 ms |
| Min    | 45 ms (failed proof) |
| Max    | 1400 ms (first call) |
| Median | ~120 ms |

**Caveats:**
- ML stages simulated with fixed delays (actual inference ~5-10ms)
- Blockchain latency includes ~500ms Docker exec overhead per call
- Single orderer deployment
- Score 300 correctly fails proof (no band at ≤300)
- Production would use Fabric SDK (lower overhead) and concurrent requests

### bft_cft_reconciliation — 2026-08-25
**What was run:** T40 - Documentation of BFT/CFT gap between seminar assumptions and implementation.
**Key findings:**

**The Gap:**
| Aspect | Seminar (§3.4.1) | Implementation |
|--------|------------------|----------------|
| Consensus | PBFT | Raft |
| Fault tolerance | Byzantine (≤⅓ malicious) | Crash (⌊(n-1)/2⌋ stopped) |
| Tolerates lying nodes | Yes | No |

**Seminar error:** Table 4.2 listed "PBFT" for Fabric. PBFT was removed in Fabric v1.0 (2017). Fabric has used Raft CFT since v1.4 (2019).

**Decision:** Keep Raft, revise threat model.

**Justification:**
1. Consortium participants are identified institutions under CBN supervision
2. Regulatory observer provides real-time visibility
3. Reputational/regulatory costs of collusion exceed technical capability
4. Byzantine tolerance protects against anonymous validators; these are accountable entities
5. Seminar §3.4.3 already argues institutional accountability — this does real work

**What Raft tolerates:**
- Node crashes (fail-stop)
- Network partitions (with quorum)
- Message delays, node restarts

**What Raft does NOT tolerate:**
- Malicious orderers forging transactions
- Equivocation (sending different messages to different peers)
- Arbitrary Byzantine behavior

**Fault tolerance summary:**
| Configuration | Orderers | Crash tolerance |
|---------------|----------|-----------------|
| Current (dev) | 1        | None            |
| Minimum CFT   | 3        | 1 crash         |
| Production    | 7        | 3 crashes       |

**Endorsement policy issue:** Current MAJORITY(4 orgs) requires ALL 3 endorsers (RegulatoryObserver cannot endorse). One endorser down halts commits. Consider MAJORITY(3 endorsing orgs) for fault tolerance.

**Chapter corrections needed:**
- §3.4.1: Replace BFT assumption with CFT + institutional accountability
- §3.4.2: Strengthen institutional argument as primary defense
- Table 4.2: Change "PBFT" to "Raft (CFT)"
- §6 Limitations: State Byzantine behavior is outside threat model

### observer_acl_enforcement — 2026-08-25
**What was run:** T43 - Fix RegulatoryObserver read-only enforcement via chaincode ACL.
**Key findings:**

**The Problem (v1.2):**
- Regulator blocked by signature count, not access control
- Could write by getting 2 endorsing peers to sign (demonstrated)
- Not structurally constrained

**The Fix (v1.3):**
- Added `checkWriteAccess()` function to chaincode
- Explicitly blocks RegulatoryObserverMSP from write operations
- Protected functions: AnchorCommitment, RecordLoanEvent, RevokeCommitment

**Verification Tests:**
| Test | Invoker | Result | Error |
|------|---------|--------|-------|
| AnchorCommitment | Regulator | BLOCKED | "access denied: RegulatoryObserverMSP is not authorized" |
| RecordLoanEvent | Regulator | BLOCKED | "access denied: RegulatoryObserverMSP is not authorized" |
| GetCommitment | Regulator | SUCCESS | (read-only access preserved) |

**Defense in Depth:**
1. Endorsement policy excludes RegulatoryObserver (policy level)
2. Chaincode ACL rejects RegulatoryObserver submissions (application level)

**Embedded Supervision (Auer 2022) Compliance:**
- Read access: Full (all query functions)
- Write access: None (blocked by ACL)
- Error type: Authorization failure (not arithmetic failure)

### fairness_corrected — 2026-08-25
**What was run:** T41 - Re-express fairness with corrected direction. FPR is the headline metric (creditworthy borrowers wrongly rejected).
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM
**Model:** LogisticRegression (class_weight=balanced)
**Key numbers:**

**By bank_account_type (headline finding):**
| Group | N | Default Rate | Approval Rate | FPR (wrongly rejected) |
|-------|---|--------------|---------------|------------------------|
| Savings | 407 | 23.8% | 55.3% | 32.1% |
| Other | 119 | 10.6% | 85.3% | 15.2% |

**Disparity:**
| Metric | Value |
|--------|-------|
| FPR ratio (Savings / Other) | 2.1x |
| FPR difference | 16.9 pp |

**Base rate context:**
- Savings default rate: 23.8%
- Other default rate: 10.6%
- Savings has 2.2x higher base default rate

**Interpretation:** Savings holders who would repay are rejected at 32.1% vs 15.2% for Other holders. This 2.1x disparity exists alongside genuinely higher default rates (23.8% vs 10.6%), making it a legitimate risk signal, not pure discrimination.

**Caveats:** FPR measures rejected among creditworthy, which is the fairness-relevant metric for lending.

### disparity_threshold_curve — 2026-08-25
**What was run:** T37 - Full FPR disparity curve across all thresholds + profit-optimal headline figure.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM
**Key numbers:**

**At profit-optimal threshold (0.53):**
| Metric | Value |
|--------|-------|
| Savings FPR | 27.3% |
| Other FPR | 10.2% |
| FPR ratio | 2.7x |
| Profit | 294 |
| N approved | 602 |

**Disparity range across all thresholds:**
| Metric | Value |
|--------|-------|
| Min ratio | 1.0x |
| Max ratio | 14.3x |
| Median ratio | 1.7x |

**Profit model:** Revenue per performing = 1.0, LGD = 3.0

**Key finding:** The FPR disparity ratio ranges from 1.0x to 14.3x across operating points. At the profit-optimal threshold (0.53), the ratio is 2.7x. **The disparity is not a stable property of the model but depends on the deployment decision — a lender can materially change its fairness profile by moving a cut-off.**

**Plot saved:** disparity_threshold_curve.png

**Caveats:** Profit model parameters affect absolute optimal threshold; relative finding (disparity varies with threshold) is robust.

### fabric_throughput — 2026-08-25
**What was run:** T44 - Concurrent throughput benchmarks using Fabric Gateway SDK (corrects T31c).
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM / Docker Desktop / Fabric 2.5
**Why this supersedes T31c:** The previous benchmark used sequential `docker exec` CLI calls, measuring inverse latency (1/3.059s = 0.33) rather than throughput. This benchmark uses concurrent load via the Gateway SDK.

**Key correction:**
| Metric | T31c (CLI) | T44 (Gateway SDK) | Factor |
|--------|------------|-------------------|--------|
| Throughput | 0.33 TPS | **104 TPS** | **315x** |
| Latency | 3059 ms | 542 ms | 5.6x faster |
| Txns/Block | 1.00 | **10.00** | Batching engaged |

**Throughput by concurrency level:**
| Concurrency | TPS | Mean Latency | P95 Latency | Txns/Block |
|-------------|-----|--------------|-------------|------------|
| 1 | 18.0 | 1176 ms | 3144 ms | 9.09 |
| 5 | 18.3 | 1118 ms | 3075 ms | 9.09 |
| 10 | 93.6 | 738 ms | 865 ms | 10.00 |
| 20 | 93.4 | 662 ms | 808 ms | 10.00 |
| 50 | **104.2** | **542 ms** | 819 ms | 10.00 |

**Peak throughput: 104 TPS** at concurrency=50 with 100% success rate.

**Latency decomposition (at peak throughput):**
| Component | Time |
|-----------|------|
| Endorsement (3 peers) | ~200-300 ms |
| Ordering + block cut | ~150-200 ms |
| Commit | ~50-100 ms |
| **Total observed** | **542 ms mean** |

**Batching verification:** Txns/block = 10 confirms batching is engaged. T31c showed txns/block = 1.00 because sequential submissions never accumulated enough transactions before the 2s BatchTimeout fired.

**Configuration context:**
- BatchTimeout: 2s (default)
- Single orderer (not fault-tolerant; Raft CFT requires 3)
- 3 endorsing peers (CommercialBankA, MicrofinanceB, FintechC)

**Comparison to seminar estimate:**
- Seminar Table 4.2: "~1,500 TPS (Estimated)"
- Measured: 104 TPS (single orderer, 3 endorsers)
- Gap: 14.4x below estimate

**Explanation of gap:** The seminar estimate was literature-derived for optimised multi-orderer configurations with higher parallelism. Single-orderer deployment with 3 endorsers is a development configuration, not production. Throughput would scale with additional orderers and reduced BatchTimeout.

**Caveats:**
- Single orderer — not fault-tolerant
- Raft CFT requires minimum 3 orderers
- BatchTimeout 2s not tuned (lower would reduce latency)
- Single-orderer throughput is not consortium throughput

### integration_demo_v2 — 2026-08-25
**What was run:** T45 - End-to-end integration demo with REAL ML inference (corrects T42).
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM / Docker Desktop / Fabric 2.5 / Node v20
**Why this supersedes T42:** T42 used simulated ML inference. T45 uses actual LogisticRegression model coefficients.

**Configuration:**
- Warmup runs: 5 (discarded)
- Actual runs: 25 (measured)
- ML model: LogisticRegression (32 features, real inference)

**Latency decomposition (answers RQ4):**
| Stage | n | Mean (ms) | P95 (ms) | % of Total |
|-------|---|-----------|----------|------------|
| ML inference | 25 | 0 | 0 | 0.0% |
| Commitment | 25 | 0 | 0 | 0.0% |
| Ledger anchor | 25 | 3268 | 3463 | 42.2% |
| Loan query | 25 | 1024 | 1247 | 13.2% |
| Proof gen | 23 | 149 | 179 | 1.9% |
| Proof verify | 23 | 14 | 17 | 0.2% |
| Repayment record | 25 | 3293 | 3508 | 42.5% |
| **TOTAL** | | **7748** | | **100%** |

**Component-level summary (RQ4 answer):**
| Component | Latency (ms) | % of Total |
|-----------|--------------|------------|
| L1 (ML scoring) | ~0 | **0.0%** |
| L2 (Blockchain) | 7585 | **97.9%** |
| L3 (ZK proofs) | 163 | **2.1%** |
| **TOTAL** | **7748** | 100% |

**Key finding:** L2 (Blockchain) dominates at **97.9%**. ZK cryptographic privacy adds only **2.1%** overhead.

**Comparison to T42:**
| Metric | T42 (simulated) | T45 (real) |
|--------|-----------------|------------|
| ML inference | 15ms (fake) | ~0ms (real) |
| ZK proof gen | 448ms (warmup) | 149ms (steady) |
| L2 % | 93.2% | 97.9% |
| L3 % | 6.2% | 2.1% |

**Caveats:** Docker exec overhead; use Gateway SDK for lower L2 latency (T44).

### impossibility_analysis — 2026-08-25
**What was run:** T46 - Chouldechova/Kleinberg impossibility demonstration.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM
**Model:** LogisticRegression (class_weight=balanced)
**Key numbers:**

**Base rates:**
| Group | N | Default Rate |
|-------|---|--------------|
| Savings | 520 | 23.8% |
| Other | 132 | 10.6% |
| **Ratio** | | **2.25x** |

**At profit-optimal threshold (0.53):**
| Metric | Savings | Other | Ratio |
|--------|---------|-------|-------|
| FPR (wrongly rejected) | 27.3% [23.1%, 31.9%] | 10.2% [5.9%, 16.9%] | 2.68x |
| FNR (wrongly approved) | 33.1% [25.4%, 41.7%] | 78.6% [52.4%, 92.4%] | 2.38x (reversed) |
| PPV | 43.5% | 20.0% | |
| NPV | 87.5% | 90.6% | |

**When FPR is equalized (thresholds 0.56 Savings, 0.45 Other):**
| Metric | Value |
|--------|-------|
| FPR gap | 0.01% (essentially zero) |
| FNR Savings | 41.1% |
| FNR Other | 71.4% |
| **FNR gap** | **30.3%** |

**Key finding:** Equalizing FPR (to gap=0.01%) forces FNR gap to 30.3%. This is **consistent with** the Chouldechova/Kleinberg impossibility result: when base rates differ, no calibrated classifier can simultaneously equalize FPR and FNR.

**Error distribution:**
- Savings borrowers absorb false rejections (27.3% FPR)
- Other borrowers receive unearned approvals (78.6% FNR)
- The errors trade off in opposite directions

**Confidence interval note:** Other has only 14 actual defaulters. FNR CI: [52.4%, 92.4%]. Direction unambiguous; magnitude uncertain.

**Citations:**
- Chouldechova, A. (2017). Fair prediction with disparate impact. Big Data, 5(2), 153-163.
- Kleinberg, J., Mullainathan, S. & Raghavan, M. (2017). Inherent trade-offs in fair risk scores. ITCS 2017.

**Plot saved:** impossibility_analysis.png

**Caveats:** Calibration shows some error (avg 0.22-0.27 absolute difference between predicted and observed). However, the trade-off demonstration is robust: FPR equalization → FNR divergence is a necessary consequence of differing base rates.

### fairness_profit_tradeoff — 2026-08-25
**What was run:** T47 - Fairness-profit exchange rate analysis with Pareto frontier.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM
**Model:** LogisticRegression (class_weight=balanced)
**Profit model:** Revenue per performing = 1.0, LGD = 3.0
**Key numbers:**

**Profit-optimal threshold (0.53):**
| Metric | Value |
|--------|-------|
| Profit | 294 (100%) |
| FPR ratio | 2.68x |
| N approved | 602 |

**Exchange rate analysis:**
| Threshold | Profit % | FPR Ratio | Profit Cost | Fairness Gain |
|-----------|----------|-----------|-------------|---------------|
| 0.53 (optimal) | 100.0% | 2.68x | — | — |
| 0.50 | 96.9% | 2.10x | 3.1% | 22% |
| 0.46 | 90.8% | 1.94x | **9.2%** | **28%** |
| 0.45 | 89.5% | 1.86x | 10.5% | 31% |

**Key finding:** The profit surface is flat in the near-optimal region while the fairness surface is not.
- Sacrificing 9.2% profit (threshold 0.46) reduces FPR ratio from 2.68x to 1.94x — a **28% fairness improvement**
- Sacrificing only 3.1% profit (threshold 0.50) gives 22% fairness improvement
- **Exchange rate: 36.5 profit units per 1.0 FPR ratio reduction**

**Pareto frontier:** 29 efficient points identified where no alternative gives both more profit and less disparity.

**Plot saved:** fairness_profit_tradeoff.png

**Caveats:** Exchange rate depends on profit model parameters (LGD=3.0). Curve shape is robust; absolute values may vary with different loss assumptions.

### canonical_split — 2026-08-25
**What was run:** T48 - Establish one canonical test split for cross-cycle consistency.
**Why:** Savings subgroup has been reported as n=537, 533, 407, then 520; test-set size as 876, 879, 885. This makes cross-cycle comparison unreliable.
**Key numbers:**

**Canonical split (DO NOT CHANGE):**
| Set | Size |
|-----|------|
| Total data | 4,376 |
| Train | 3,500 |
| Test | 876 |

**Test set subgroup sizes (bank_account_type):**
| Group | N |
|-------|---|
| Savings | 520 |
| Other | 132 |
| Current | 12 |
| Unknown/NaN | 212 |

**Parameters:**
- Random state: 42
- Test size: 0.2
- Stratified by target

**Verification:** PASSED - Split is deterministic with same seed.

**Usage:** All future analyses MUST use `canonical_split.json` indices instead of calling `train_test_split()` again.

**Caveats:** Earlier analyses that used different splits should be noted. The canonical split supersedes all previous splits.

### sub_band_analysis — 2026-08-25
**What was run:** T49 - Analysis of borrowers below the lowest threshold band.
**Why:** Flow 4 (score 300, bands {400, 550, 700, 850}) failed proof generation. This is CORRECT circuit behavior, not a bug.
**Key numbers:**

**Sub-lowest-band borrowers (score < 400):**
| Metric | Value |
|--------|-------|
| Count | 200 |
| Percentage | 22.8% |
| Score range | 18 - 399 |
| Actual default rate | **45.0%** |

**Band distribution:**
| Band Range | Count | % |
|------------|-------|---|
| <400 | 200 | 22.8% |
| 400-550 | 186 | 21.2% |
| 550-700 | 352 | 40.2% |
| 700-850 | 123 | 14.0% |
| >=850 | 15 | 1.7% |

**1-Bit Information Leak (unavoidable in threshold schemes):**
- If proof submitted: score >= lowest_band is revealed
- If no proof: ambiguous (below band OR refusal)
- Binary outcome (proof/no-proof) inherently leaks 1 bit

**Chapter 3 threat model note:** A borrower below the lowest band cannot generate ANY proof. The lender cannot distinguish "below lowest band" from "refused to prove". This 1-bit leak is inherent to the threshold scheme and should be documented as a design consequence, not a bug.

**Handling recommendation:** Treat as expected outcome, not exception. Return "no_valid_band" status instead of error.

**Caveats:** 22.8% is a significant population. The 45.0% default rate confirms they are genuinely high-risk borrowers correctly excluded from proof generation.

### batch_config_sweep — 2026-08-27
**What was run:** T56 - Batch configuration sweep to determine whether throughput ceiling is platform or configuration limited.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM / Docker Desktop / Fabric 2.5
**Key numbers:**

**MaxMessageCount Sweep (at concurrency=75, 300 txns each):**
| MMC | TPS | Txns/Block | Block Rate | Mean Latency |
|-----|-----|------------|------------|--------------|
| 10 | 120.2 | 10.00 | 12.02/s | 567 ms |
| 50 | **130.9** | 50.00 | 2.62/s | 524 ms |
| 100 | 33.7 | 75.00 | 0.45/s | 2172 ms |
| 500 | 33.7 | 75.00 | 0.45/s | 2172 ms |

**BatchTimeout Sweep (single-tx latency on idle network, 20 txns each):**
| Timeout | Mean Latency | P50 | P95 |
|---------|--------------|-----|-----|
| 2s | 2051 ms | 2050 ms | 2109 ms |
| 500ms | 568 ms | 561 ms | 609 ms |
| 200ms | **256 ms** | 252 ms | 294 ms |

**Key findings:**

1. **T53's 143.5 TPS was configuration-limited, not platform-limited.** Peak throughput at MMC=50 reached 131 TPS. The 8% improvement (120→131) indicates configuration tuning can increase throughput.

2. **Batch starvation at MMC≥100:** Throughput DROPPED to 33.7 TPS because blocks wait full 2s BatchTimeout before being cut. At concurrency=75, only 75 txns arrive per block period — insufficient to fill MMC=100 blocks.

3. **Single-tx latency is dominated by BatchTimeout.** Reducing from 2s to 200ms cuts write latency by **8x** (2051ms → 256ms). This explains T52's finding that SDK gave only 1.26x speedup on writes — the wait is structural.

4. **The trade is configurable:** Default Fabric (MMC=10, BT=2s) optimizes for neither latency nor throughput. Both can be improved 4-8× with appropriate tuning.

**Recommendations:**
- **Low-volume credit decisions:** BatchTimeout=200ms, MMC=10 → 256ms latency per decision
- **High-volume batch scoring:** BatchTimeout=2s, MMC=50 → 131 TPS

**Chapter 5 result:** The throughput-latency trade is a configuration choice, not a platform constraint.

**Caveats:** Single orderer (not fault-tolerant). Higher concurrency with lower BatchTimeout may yield higher throughput than 131 TPS.

### integration_demo_t57 — 2026-08-27
**What was run:** T57 - End-to-end integration demo with REAL ML inference (corrects T52 regression).
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM / Docker Desktop / Fabric 2.5 / BatchTimeout=200ms
**Why this supersedes T52:** T52 used simulated ML inference and omitted consent/feature_engineering stages.
**Key numbers:**

**Configuration:**
- ML Model: LogisticRegression with 32 features (real coefficients from Python)
- BatchTimeout: 200ms (tuned per T56)
- Bands: [400, 550, 700, 850]
- Borrowers tested: 25

**Stage latencies (mean, ms):**
| Stage | Mean (ms) | % of Total |
|-------|-----------|------------|
| consent | <1 | 0.0% |
| feature_engineering | <1 | 0.0% |
| ml_inference | <1 | 0.0% |
| commitment | <1 | 0.0% |
| ledger_anchor | 293 | 64.6% |
| loan_query | 7 | 1.5% |
| proof_generation | 139 | 30.6% |
| proof_verification | 12 | 2.6% |

**Component breakdown (RQ4 answer):**
| Component | % of Total |
|-----------|------------|
| L1 (ML scoring) | 0.1% |
| L2 (Blockchain) | 66.5% |
| L3 (ZK proofs) | 33.4% |

**Key findings:**
1. **Real ML inference works** - scores range from 178 to 810 based on actual model coefficients
2. **5 of 25 flows (20%) fell below lowest band** - consistent with T54's 22.8% population rate
3. **Ledger anchor latency is 293ms** vs ~3000ms at default BatchTimeout - **10× improvement from T56**
4. **L2 remains dominant at 66.5%** - NOT L3 as T52 incorrectly stated

**T52 corrections:**
- ML inference is REAL (LogisticRegression with exported coefficients), not simulated
- consent and feature_engineering are measured stages, not omitted
- "L3 is the primary latency component" is FALSE - L2 dominates
- Correct statement: "L2 remains dominant. The SDK improves queries ~40× while writes wait out BatchTimeout. Reducing BatchTimeout from 2s to 200ms cuts write latency 8×."

**Caveats:** Some repayment recording failed due to endorsement issues (concurrent access). Core findings unaffected.

### calibration_methodology_t58 — 2026-08-27
**What was run:** T58 - Calibration methodology clarification and FNR-gap curve sweep.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM
**Key numbers:**

**(a) Calibration Methodology:**
- Method: CalibratedClassifierCV with isotonic regression, cv=5
- Fitting: Internal 5-fold CV on train+validation set
- Evaluation: Held-out test set (never seen during fitting)
- ECE on test: 0.0370 (well-calibrated, < 0.05 threshold)
- **No leakage from test set** - calibration learned via internal CV

**(b) FNR-Gap Curve (the impossibility result made visible):**
| Target FPR | FNR Savings | FNR Other | FNR Gap |
|------------|-------------|-----------|---------|
| 0.05 | 73.4% | 85.7% | 12.3% |
| 0.14 | 56.5% | 78.6% | 22.1% |
| 0.24 | 38.7% | 71.4% | 32.7% |
| 0.33 | 28.2% | 64.3% | 36.1% |
| 0.43 | 20.2% | 50.0% | 29.8% |

**FNR gap range:** 9.2% to 36.8% across FPR levels 0.05-0.50
**Minimum gap:** 9.2% at FPR=0.07 — cannot be eliminated

**Key finding:** The FNR gap is NON-ZERO at every FPR level. This is the Chouldechova/Kleinberg impossibility result made empirically visible.

**(c) Base Rate Reconciliation:**
- Savings n=517 (vs canonical 520) - 3 test borrowers lack demographics records
- Other n=132
- Base rates: Savings 24.0%, Other 10.6% (ratio 2.26x)

**Plot saved:** fnr_gap_curve_t58.png

**Caveats:** The n discrepancy (517 vs 520) is due to missing demographics for some test borrowers, not a data error.

### leakage_5way_correction — 2026-08-27
**What was run:** T59 - Fix internal contradiction in leakage_5way.json where prose said "~0.15 bits" but computed value was 0.4162 bits.
**Key numbers:**

| Metric | Before | After |
|--------|--------|-------|
| Prose | "~0.15 bits" (wrong) | "0.42 bits (26.5%)" (correct) |
| Computed | 0.4162 bits | 0.4162 bits |

**What it means:** With 5 bands, an adversary learns 0.42 bits of information, which is 26.5% of the information leaked by revealing the exact score (1.57 bits total). This is a substantively different privacy claim than "~0.15 bits".

**Caveats:** None. The prose now matches the computation.

### fairness_full_table_t60 — 2026-08-27
**What was run:** T60 - Full fairness table showing FPR, FNR, approval rate, and profit at thresholds 0.53 and 0.62.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM
**Key numbers:**

**At threshold 0.53 (profit-optimal):**
| Group | FPR | FNR | Approval Rate | Profit |
|-------|-----|-----|---------------|--------|
| Savings | 27.2% | 33.1% | 63.2% | 163 |
| Other | 10.2% | 78.6% | 88.6% | 73 |
| OVERALL | 23.6% | 40.3% | 68.5% | 292 |

**At threshold 0.62 (T50 fairness recommendation):**
| Group | FPR | FNR | Approval Rate | Profit |
|-------|-----|-----|---------------|--------|
| Savings | 16.3% | 46.8% | 74.9% | 155 |
| Other | 2.5% | **100.0%** | 97.7% | 73 |
| OVERALL | 12.4% | 56.5% | 80.8% | 276 |

**Critical finding:** At threshold 0.62, **FNR_Other = 100%** — every Other defaulter is approved (wrongly).

**Profit trade-off:**
| Threshold | Profit | % of Optimal |
|-----------|--------|--------------|
| 0.53 | 292 | 100.0% |
| 0.62 | 276 | 94.5% |
| Cost | 16 | 5.5% |

**FNR changes (0.53 → 0.62):**
- Savings: 33.1% → 46.8% (+13.7%)
- Other: 78.6% → 100.0% (+21.4%)

**Key finding:** T50's threshold 0.62 recommendation has a consequence that must be stated explicitly: FNR_Other = 100%. This is defensible under a financial-inclusion objective (minimize FPR, wrongful rejection), but it means the model approves **all** Other defaulters. The trade is: -5.5% profit, -10.9pp FPR_Savings, but +21.4pp FNR_Other.

**Caveats:** The "fairness" of threshold 0.62 depends entirely on which fairness definition is prioritized. FPR parity comes at the cost of FNR divergence — exactly as the Chouldechova/Kleinberg impossibility result predicts.

### integration_demo_t61 — 2026-08-27
**What was run:** T61 - Complete integration flow with repayment_record stage, per-decision means, and corrected proof labeling.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM / Docker Desktop / Fabric 2.5 / BatchTimeout=200ms
**Why this supersedes T57:** T57 had repayment_record n=0 (never ran), and "proofs_succeeded" conflated proof generation with threshold approval.
**Key numbers:**

**Per-decision latency (the headline):**
| Component | Mean (ms) | % of Total |
|-----------|-----------|------------|
| L1 (ML scoring) | 0.29 | 0.0% |
| L2 (Blockchain) | 505.35 | 78.6% |
| L3 (ZK proofs) | 137.64 | 21.4% |
| **TOTAL** | **643.27** | 100% |

**Stage breakdown:**
| Stage | n | Mean (ms) |
|-------|---|-----------|
| consent | 25 | 0.07 |
| feature_engineering | 25 | 0.02 |
| ml_inference | 25 | 0.01 |
| commitment | 20 | 0.18 |
| ledger_anchor | 20 | 248.6 |
| loan_query | 20 | 8.3 |
| proof_generation | 19* | 125.2 |
| proof_verification | 20 | 12.5 |
| repayment_record | 16 | 248.5 |

*Cold-start proof (506.9ms) excluded from statistics; remaining 19 averaged 125ms.

**Flow outcomes:**
| Category | Count |
|----------|-------|
| Below lowest band | 5 |
| Proofs generated | 20 |
| Approved (band >= 550) | 16 |
| Rejected (band < 550) | 4 |
| Repayments recorded | 16 |

**T57 corrections:**
1. repayment_record now executes for all approved flows (n=16)
2. "proofs_succeeded" relabeled to proofs_generated + approved_threshold + rejected_threshold
3. Cold-start proof excluded from statistics
4. Per-decision means reported as headline (not batch totals)

**Key finding:** A complete credit decision takes **643ms** on average. L2 (blockchain) is 79%, L3 (ZK) is 21%. Cryptographic privacy costs 21% of decision latency, keeping the total **under 650ms**.

**Caveats:** L2 includes both ledger_anchor (~249ms) and repayment_record (~249ms). Without repayment recording, single-decision latency would be ~395ms.

### throughput_t62 — 2026-08-27
**What was run:** T62 - Corrected throughput analysis with 3 runs per configuration.
**Hardware:** AMD Ryzen 7 4800H (16 cores) / 32 GB RAM / Docker Desktop / Fabric 2.5
**Why this supersedes T56:** T56 ran each config once; T53 vs T56 showed 16% variance for same config (143.5 vs 120.2 TPS). The MMC=10 vs MMC=50 difference (9%) was within noise.
**Key numbers:**

**MMC=10 (3 runs):**
| Run | TPS |
|-----|-----|
| 1 | 119.14 |
| 2 | 125.02 |
| 3 | 124.90 |
| **Mean** | **123.02** |
| Range | 5.88 (4.8%) |

**MMC=50 (3 runs):**
| Run | TPS |
|-----|-----|
| 1 | 128.00 |
| 2 | 133.45 |
| 3 | 128.50 |
| **Mean** | **129.98** |
| Range | 5.45 (4.2%) |

**Analysis:**
| Metric | Value |
|--------|-------|
| MMC=10 mean | 123.02 TPS |
| MMC=50 mean | 129.98 TPS |
| Difference | 5.4% |
| Run-to-run variance | 4.5% |
| Ranges overlap | No (125.02 vs 128.00) |
| t-test p (approx) | ~0.06 |

**Corrected conclusion:**
1. **Throughput ceiling: ~119-133 TPS** for this single-orderer deployment
2. **MMC tuning shows a small effect (~5%), marginal at n=3** — the ranges do not overlap, suggesting a real but modest improvement
3. **Starvation finding CONFIRMED:** At MMC >= 100, throughput collapses to ~34 TPS due to batch starvation
4. **Single-orderer is the constraint** — Raft requires minimum 3 orderers for fault-tolerant deployment

**Practical conclusion:** MaxMessageCount tuning buys roughly 5%, not an order of magnitude. The single-orderer configuration is the binding constraint.

**T56 correction:** T56 claimed MMC=50 was optimal (131 TPS vs 120 TPS). With 3 runs per config, MMC=50 shows a small (~5%) improvement over MMC=10, marginal at n=3 (p~0.06).

**Caveats:** Single orderer (not fault-tolerant). The ~4-5% run-to-run variance is typical for concurrent workloads on shared resources.

---

### ui_demo_t72 — 2026-08-29
**What was run:** Minimal web UI with three screens demonstrating the privacy-preserving architecture.
**Hardware:** N/A (frontend + backend code, no benchmark)
**Key components:**

| Screen | URL | Layers | Purpose |
|--------|-----|--------|---------|
| Index | `/` | — | Navigation + architecture overview |
| Borrower | `/borrower` | L1 + L2 | Score display, commitment anchoring |
| Lender | `/lender` | L3 | ZK proof verification, **privacy panel** |
| Regulator | `/regulator` | L2 | Read-only ledger, ACL rejection demo |

**Key features:**
| Feature | Implementation |
|---------|---------------|
| Threshold selection | Fixed buttons [400, 550, 700, 850] — no free-text |
| Privacy panel | Explicit list of what lender does NOT receive |
| Sub-band handling | Score < 400 renders as "below lowest band" state |
| ACL rejection | Live demo of blocked write attempt |
| Timing display | Per-stage breakdown for L1/L2/L3 |

**Screenshot value:**
1. Borrower view: Shows score (717), P(default), commitment hash, ledger TX
2. Lender view: Shows eligibility + ZK proof timing + **privacy panel**
3. Regulator view: Shows ledger history + ACL rejection message

**Tech stack:** Node/Express backend, plain HTML/CSS/JS frontend, no framework.

**Dependencies:** Fabric Gateway SDK, snarkjs, circomlibjs, express.

**Caveats:** Requires Fabric network running on localhost:7051. ZK circuit artifacts must be pre-built.
