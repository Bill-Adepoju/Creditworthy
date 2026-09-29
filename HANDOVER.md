# HANDOVER.md

> Research side writes OUTBOUND; Claude Code writes INBOUND. Either side appends to DECISION LOG, never deletes. **Code lives only in the repo.**

**Cycle:** 14 — final three, then standby
**Last updated by:** research chat
**Date:** 2026-08-29

---

## STATUS

| Item | State |
|---|---|
| Analysis, build, UI, documentation | ✅ Complete |
| Cross-document consistency | ✅ Substantially complete — three small gaps |
| Drafting | 🟢 **Starting now, in parallel** |

**The build phase is over.** Three small reproducibility gaps remain; after those, Claude Code moves to standby for figure rendering and any regeneration that drafting turns up.

---

## CYCLE 13 REVIEW

All four resolved, and T79 is exactly the right shape:

> *"This test predates the canonical 876-row test split and was not regenerated against it. The 1,000 borrowers were sampled from the full dataset before the train/validation/test split was finalised. The test validates ML→ZK integration but does not confirm coverage of the specific canonical test population."*

That keeps the evidence and states the limitation precisely. It is the model for how any remaining discrepancy should be handled during drafting.

Table 4.3's coverage note also lands well — it states the exclusion, gives the 74% figure, and connects the gap to the argument rather than treating it as a footnote.

---

## OUTBOUND — Cycle 14

Three items, all in `REPRODUCIBILITY.md`. None blocks drafting.

### T83. The Phase 5 command is not reproducible

§3 Phase 5 now reads:

```
# 16. Throughput and batch timeout benchmarks
# Run via end_to_end_sdk_t61.js with --benchmark flags
```

"With `--benchmark` flags" does not tell anyone what to run. In a reproducibility manifest that is the one thing that must be exact.

**Do:** give the literal commands, including the flags and any arguments, for producing `throughput_t62.json` and `batch_config_sweep.json`. If they need the network in a particular state — BatchTimeout already reconfigured, for instance — say so, since Table 4.9 depends on channel configuration having been changed first.

### T84. Confirm which script produces Tables 4.8 and 4.9

The §4 table map now attributes both to `integration/end_to_end_sdk_t61.js`. The Cycle 10 record lists a separate file, `chain/caliper/throughput_t62.js`.

Either the scripts were consolidated since — in which case the map is right and the earlier file no longer exists — or the map now points at the wrong script. **Verify against the filesystem** rather than reasoning about it, and report which is true.

### T85. Complete the verification checklist

§7 covers Tables 4.1, 4.2, 4.6, 4.7, 4.8 and 4.10, but omits 4.3, 4.4, 4.5 and 4.9.

Table 4.9 in particular should be there — the 8× latency reduction (2,051 ms → 256 ms) is a headline result and among the easiest to re-verify. Add checklist entries for the fairness figures (FPR 27.2% vs 10.2%, ratio 2.7×), the trade-off (5.5% profit for 10.9 pp FPR reduction), the FNR gap range (9.2%–36.8%), and the latency sweep.

---

## AFTER CYCLE 14 — standby

Drafting begins on the research side. Claude Code stays available for:

- Rendering the four Mermaid diagrams to PNG for the figure list
- Capturing UI screenshots for §4.3
- Regenerating any table whose numbers the drafting process questions
- Producing Appendix C and D (full FNR-gap and disparity-threshold curves) as formatted tables

No further analysis is expected. If drafting surfaces a genuine gap, it comes back as a new task.

---

## HUMAN TASKS (Bill)

- [ ] Locate the real publication record for Israel (2025)
- [ ] Verify remaining seminar references — 2 of 2 checked had faulty metadata
- [ ] Version control — handling separately

---

## INBOUND — From Claude Code

**Cycle 14 complete.** All three reproducibility gaps resolved.

### Results produced
| Task | File | Change |
|---|---|---|
| T83 | `REPRODUCIBILITY.md` §3 | Fixed Phase 5 commands: exact `node chain/caliper/throughput_t62.js` and `batch_config_sweep.js` with prerequisites |
| T84 | `REPRODUCIBILITY.md` §4 | Corrected Tables 4.8/4.9 scripts from `integration/` to `chain/caliper/` |
| T85 | `REPRODUCIBILITY.md` §7 | Added checklist entries for Tables 4.3, 4.4, 4.5, 4.9 |

### T84 Finding
The Cycle 10 record was correct: `chain/caliper/throughput_t62.js` and `chain/caliper/batch_config_sweep.js` exist and produce the benchmark results. The table map had been incorrectly consolidated to `integration/end_to_end_sdk_t61.js` — now corrected.

### Codebase state
All reproducibility documentation is now complete. Ready for standby.

### Blockers
None.

### Decisions needed from research side

---

## DECISION LOG

| Date | Decision | Rationale |
|---|---|---|
| 2026-08-23 | Build order L3 → L1 → L2 | L3 proved small (~570 constraints); Fabric is the real time risk. |
| 2026-08-23 | ZKP scoped to threshold verification only | Proof cost scales with circuit depth; in-circuit inference infeasible. Seminar §4.5. |
| 2026-08-23 | `ge.out === 1` as hard constraint | Existence of a proof *is* the attestation; no false proof to misattribute. |
| 2026-08-23 | Num2Bits range checks on both operands | Prevents `score = p − k` field-wraparound attack. |
| 2026-08-23 | Three parallel feature sets | Turns a design assumption into a testable hypothesis. |
| 2026-08-23 | Cycle 02 hardens Cycle 01 rather than advancing | Point estimates without variance cannot be defended at viva. |
| 2026-08-23 | Fairness disparities reported as a primary finding | Confirms the seminar's own §2.3.2 prediction — a result, not a shortfall. |
| 2026-08-23 | **D1 resolved: threshold banding, not rate limiting** | Rate limiting is a policy control; the thesis requires privacy as a mathematical property. Banding is collusion-resistant and costs ~1% constraints. |
| 2026-08-23 | **Nonce-binding retained but reclassified** | It prevents proof *replay*, a separate threat. It does not address binary search — that adversary issues fresh legitimate requests. The two were initially conflated; the threat model must distinguish them. |
| 2026-08-23 | **Chapter 3 dual-model rationale to be revised as scale-conditional** | LR and tuned GBM statistically indistinguishable at ~4.4k rows; `max_depth=2` optimum indicates a near-additive signal. Claim bounded to this scale. |
| 2026-08-23 | **Fairness headline metrics restricted to n ≥ 30 subgroups** | Estimates on n=3 are noise. Small subgroups reported separately; their scarcity treated as a finding in its own right. |
| 2026-08-24 | **T15 banding implemented with 4 bands** | {400, 550, 700, 850} reduces leakage from 9.97 bits to 2.00 bits. Constraint cost: 3 (0.5%). |
| 2026-08-24 | **T23/T24 model tuning NaN resolved** | Original used `needs_proba` (deprecated). Fixed with `scoring='roc_auc'`. 50-fold CV confirms statistical power. |
| 2026-08-24 | **LR recommended over XGB despite borderline significance** | XGB p=0.045 but 7.5× overfit gap (10.6% vs 1.4%). For deployment at this scale, generalisation matters more than marginal accuracy. |
| 2026-08-24 | **T33: Significance test corrected** | Nadeau-Bengio correction gives p=0.578 (not 0.045). All models statistically indistinguishable. LR case now statistical AND regulatory. |
| 2026-08-24 | **T27: Privacy-utility corrected** | Original 263 bps INVALID. Corrected: equidist 476.8 bps, quantile 13.6 bps at B=4. |
| 2026-08-24 | **T28: Quantile band placement recommended** | Quantile wins 7/9 B values. 35× better utility cost at B=4. Design recommendation for dissertation. |
| 2026-08-24 | **T29: log₂(B) bound validated** | True leakage < bound for all configs. Bound is conservative, not an underestimate. |
| 2026-08-24 | **T30: bank_account_type disparity is confounded** | Removing feature changes disparity by only 7.9%. Chapter 6 should recommend fairness constraints, not feature removal. |
| 2026-08-24 | **T32: Constraint counts reconciled** | 573→576 (delta 3) using snarkjs 0.7.6. Wire count diff due to circom versions. |
| 2026-08-24 | **T38: Positive class = DEFAULT** | target=1 = Bad. pred_rate is REJECTION rate. Cycle 03 narrative inverted. |
| 2026-08-24 | **T37: Disparity is threshold-dependent** | Ranges 1.0x to 27x. Quote at stated threshold and note dependence. |
| 2026-08-24 | **T34: FS_regularity vs FS_magnitude survives** | p<0.0001 under Nadeau-Bengio. +8.3 pp difference. Full adds little over regularity. |
| 2026-08-24 | **T31: Fabric Layer 2 code complete** | 3 endorsers + 1 read-only observer. Chaincode stores only commitments. |
| 2026-08-25 | **T31: Fabric Layer 2 DEPLOYED** | Network running (6 containers), channel created via osnadmin, chaincode deployed with MAJORITY endorsement. RegulatoryObserver verified read-only (write blocked by policy). |

---

## OPEN RESEARCH QUESTIONS

1. ~~Binary-search leak~~ — **RESOLVED.** Banding implemented (T15), privacy-utility curve corrected (T27). 4 quantile bands → 13.6 bps cost.
2. **Citation audit** — several seminar references resist verification (Ayari, Guetari & Kraïem 2026; Israel 2025). Chapter 2 leans on the former repeatedly, and now also for the explainability–accuracy tension in the T9 discussion. Being worked in the research chat.
3. **Synthetic behavioural augmentation** — add simulated mobile-money features, or stay with real Zindi data only? Leaning toward staying real, given the dataset survived both robustness checks.
4. **Groth16 vs Plonk** — Plonk's universal setup addresses the seminar's trusted-setup concern. Note: phase 1 is universal and per-circuit setup is only ~3 s, so that concern may be smaller than the seminar assumed. Deferred to a later cycle.
5. ~~Band placement — equal spacing vs deciles~~ — **RESOLVED (T28).** Quantile wins 7/9 B values. At B=4: quantile 13.6 bps vs equidistant 476.8 bps (35× better). Design recommendation: use quantile band placement.
6. ~~Is `bank_account_type` disparity causal or confounded?~~ — **RESOLVED (T30).** Confounded. Savings correlates with tenure (r=−0.35), loan count (r=−0.31). Removing feature changes disparity by only 7.9%. Chapter 6: disparity is structural, requires fairness constraints.
7. ~~Does log₂(B) overstate privacy?~~ — **RESOLVED (T29).** No — log₂(B) is conservative. True leakage is LESS than bound (e.g., B=4 equidist: 1.17 bits < 2.00). Bound remains valid as upper limit.