# Creditworthy: Privacy-Preserving Credit Scoring



Alternative-data credit scoring for the unbanked, with a consortium blockchain for governance and zero-knowledge proofs for privacy. A lender learns only whether a borrower's score clears a threshold, never the score itself. The project builds the system end to end and **measures what that privacy and decentralisation cost** in accuracy, latency and fairness.

## Architecture

| Layer | What it does | Where |
|---|---|---|
| **L1 · ML** (off-chain) | Engineers repayment-regularity features from loan history and scores borrowers with logistic regression: `score = round(1000 × (1 − P(default)))`, 0–1000. Raw data never leaves this layer. | `ml/` |
| **L2 · Ledger** | Hyperledger Fabric consortium: 3 endorsing lenders plus a read-only regulatory observer. Stores only Poseidon commitments of scores and loan events, never scores, features or PII. | `chain/` |
| **L3 · ZK proof** | Groth16 circuit proving `Poseidon(score, salt) == on-chain commitment` **and** `score ≥ threshold`. Thresholds are restricted to four bands {400, 550, 700, 850} to stop a lender binary-searching the exact score. | `circuits/` |

The Poseidon commitment is what ties the layers together. Without it, a borrower would only prove "I know some number above T", not that the ML layer's score is above T.

## Key results

Measured on an AMD Ryzen 7 4800H (8 cores), 32 GB RAM, Docker Desktop on Windows 10. Seed 42, 876-borrower test set. Full tables with sources are in [`results/FINAL_TABLES.md`](results/FINAL_TABLES.md).

| Question | Result |
|---|---|
| Model choice | LR, random forest and XGBoost are statistically indistinguishable (ROC-AUC 0.696–0.700, Nadeau-Bengio p > 0.5). LR is used for its 7.5× smaller overfit gap and interpretability. |
| Which features matter | Repayment-regularity features beat magnitude features by 8.3 pp ROC-AUC (p < 0.0001). |
| Fairness | At the profit-optimal threshold, Savings-account holders who would have repaid are rejected 2.7× as often as others (FPR 27.2% vs 10.2%). |
| ZK cost | 576 constraints (+3 for banding); proof generation 125 ms, verification 12.5 ms; proof size ~720 bytes |
| Privacy leakage | Banding cuts what a lender can learn from ~10 bits (exact score) to 1.99 bits |
| Ledger | 119–133 TPS with a single orderer; 256 ms per write at BatchTimeout = 200 ms |
| End to end | 643 ms per approved decision, 395 ms per rejection. The ledger accounts for 65–79% of that; ZK proofs for 21–35%. |

## Repository layout

```
ml/            feature engineering, training, fairness, explainability (Python)
circuits/      circom circuits, trusted setup, proof benchmarks
chain/         Fabric network config, chaincode (Go), Caliper benchmarks
integration/   end-to-end pipeline runs that produce the latency results
ui/            demo web app: Borrower, Lender and Regulator views
results/       every measured output (JSON) plus FINAL_TABLES.md and SUMMARY.md
docs/          requirements, test cases, diagrams
```

## Running it

Prerequisites: Python 3.11, Node.js 20, Docker Desktop, Go 1.21+, Hyperledger Fabric 2.5 binaries. A Windows `circom` binary is in `bin/`.

**Data.** `data/` is not committed. Download the Zindi SuperLender dataset (`trainperf.csv`, `trainprevloans.csv`, `traindemographics.csv`) into `data/`.

**ML pipeline.**
```bash
pip install -r requirements.txt
python ml/features.py
python ml/canonical_split.py
python ml/train.py
```
Every step and the script behind each dissertation table are listed in [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).

**ZK circuit.**
```bash
npm install
npm run zk:setup     # compile baseline + banded circuits, trusted setup
npm run zk:bench     # baseline-circuit proofs, benchmarks and negative tests
```

**Fabric network.** See [`chain/README.md`](chain/README.md). The first run needs `./scripts/setup-all.sh`. After that, restart the stopped containers with `docker start`. Don't use `scripts/start.sh`: it runs `docker-compose down --volumes`, which erases the ledger.

**Demo app** (needs the Fabric network running):
```bash
cd ui
npm install
npm start            # http://localhost:3000
```

## The demo

Three views, each showing what that role can and cannot see:

- **Borrower:** consents, gets a score computed from their real features, and anchors the commitment on the ledger. Sees their full data plus the factors that raised or lowered the score.
- **Lender:** picks one of four threshold bands and verifies a ZK proof against the commitment it reads from the ledger. Learns only eligible or not. Approvals are capped by the borrower's active exposure for the proven band.
- **Regulator:** reads every commitment and loan event as the observer org. A write attempt is a real transaction, rejected by the chaincode.

The demo borrowers are 25 real customers from the held-out test set. Run each borrower through the Borrower view before checking them in the Lender view: the borrower's salt is held in server memory as a stand-in for a wallet, so it has to be re-created after a server restart.
