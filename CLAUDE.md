# CLAUDE.md — Standing Project Brief

> Claude Code: read this file at the start of every session. It is stable context.
> The rotating work order is in `HANDOVER.md`. Read that second.

---

## Project

MIT dissertation, University of Lagos. Supervisor: Dr. U.C. Ogude.
Builds on a defended seminar: *AI-Powered Decentralized Credit Scoring for the Unbanked* (March 2026), which proposed the architecture conceptually. **This project implements and empirically evaluates it.**

**Central claim to be proven with numbers:** what does it *cost* — in accuracy, latency, and fairness — to add decentralised governance and cryptographic privacy on top of alternative-data credit scoring? Nobody has published that trade-off curve. That is the contribution.

## Architecture (fixed — do not redesign without flagging)

Four layers, functionally isolated:

1. **Alternative data + feature engineering** — off-chain. Engineers regularity/consistency features from behavioural data. Raw logs never leave this layer.
2. **ML credit scoring** — off-chain. Dual-model: interpretable logistic regression baseline + gradient-boosted ensemble. Outputs integer score 0–1000.
3. **Permissioned blockchain ledger** — Hyperledger Fabric consortium. Stores *only* Poseidon commitments of scores plus loan events. Includes a read-only regulatory observer org (embedded supervision, per Auer 2022).
4. **Zero-knowledge verification** — Groth16 circuit proving `Poseidon(score, salt) == commitment AND score >= threshold`. Threshold verification only; full ML inference in-circuit is explicitly out of scope.

**The seam between layers 2/3 and 4 is the Poseidon commitment.** Without the binding constraint, a borrower proves only "I know some number above T", which is worthless. Never weaken this.

## Hard constraints

- **Never place on-chain:** raw scores, behavioural features, PII, model weights. Only commitments, hashes, and loan event metadata. If a task seems to require otherwise, stop and flag it — the privacy argument collapses.
- **Never estimate a number that can be measured.** The seminar already cited estimated throughput figures; the whole point of this project is replacing them. If a benchmark can't run, say so in `HANDOVER.md` rather than substituting a literature value.
- **Score scaling is fixed:** `score = round(1000 * (1 - P(default)))`, integer, 16-bit range. The circuit depends on this.
- **Fairness is not optional.** It was promised in the seminar. Every model evaluation reports fairness metrics alongside accuracy.

## Repository layout

```
/circuits          circom circuits
/ml                feature engineering, training, fairness, explainability
/chain             Fabric network config + chaincode
/integration       end-to-end demo app
/results           ← ALL measured outputs land here (see convention below)
/data              gitignored; datasets live here locally
CLAUDE.md          this file
HANDOVER.md        rotating work order
```

## Results artifact convention (important)

The research/writing side of this project does not read code. It reads `/results`. So:

- Every experiment writes `results/<experiment-name>.json` with raw numbers.
- Every experiment appends a plain-language block to `results/SUMMARY.md`:

```markdown
### <experiment-name>  — <date>
**What was run:** one sentence.
**Hardware:** cores / RAM (matters for latency claims).
**Key numbers:**
| metric | value |
**Caveats:** anything that would make a reader over-claim.
```

Write numbers, not narrative. Interpretation happens on the research side.

## Style

- Python: pandas / scikit-learn / xgboost / fairlearn / shap. Notebooks for exploration, `.py` modules for anything reused.
- Determinism matters: fix random seeds, log library versions into every results JSON.
- Comment circuits and chaincode for *dissertation reuse* — this code gets quoted in Chapter 4.

## What Claude Code decides vs. escalates

**Decide freely:** library choice, code structure, hyperparameter search strategy, test design, debugging approach.

**Escalate to `HANDOVER.md` → INBOUND:** anything that changes what the dissertation claims. Dataset doesn't contain an expected field. A layer's design assumption turns out infeasible. A result contradicts the seminar's argument. Scope looks like it will overrun.

An unexpected or negative result is a finding, not a failure — report it plainly rather than tuning until it looks good.
