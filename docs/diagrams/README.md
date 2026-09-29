# Modelling Diagrams

This directory contains system modelling diagrams in Mermaid format for Chapter 3.

## Diagrams

| File | Type | Description |
|------|------|-------------|
| `use_case.mmd` | Use Case Diagram | Four actors (Borrower, Lender, Issuing Institution, Regulatory Observer) and their interactions |
| `dfd_level0.mmd` | DFD Context | System as single process with external entities |
| `dfd_level1.mmd` | DFD Level 1 | Four layers (L1 ML, L2 Blockchain, L3 ZK) as processes with data stores |
| `erd.mmd` | Entity-Relationship | Chaincode world state entities + off-chain feature store |

## Rendering

### Online (Quick)
Paste contents into [Mermaid Live Editor](https://mermaid.live/)

### CLI (PNG export)
```bash
npm install -g @mermaid-js/mermaid-cli
mmdc -i use_case.mmd -o use_case.png
mmdc -i dfd_level0.mmd -o dfd_level0.png
mmdc -i dfd_level1.mmd -o dfd_level1.png
mmdc -i erd.mmd -o erd.png
```

### VS Code
Install "Markdown Preview Mermaid Support" extension for live preview.

## Design Notes

### Use Case Diagram
- Regulatory Observer has read-only access (highlighted in red)
- Issuing Institution handles data ingestion and commitment anchoring
- Lender's threshold selection is restricted to fixed bands

### DFD Level 1
- **Green (L1):** ML operations run off-chain; raw data never leaves this layer
- **Red (L2):** Blockchain stores only commitments and loan events
- **Purple (L3):** ZK proof generation and verification
- Dashed line to Regulator indicates read-only access

### ERD
- **On-chain entities:** `CREDIT_COMMITMENT`, `LOAN_EVENT`
- **Off-chain entities:** `FEATURE_STORE`, `ML_MODEL` (shown for completeness but not stored on ledger)
- Note what is deliberately absent from on-chain: raw scores, loan amounts, behavioural features, PII, model weights, salts

## Color Coding

| Color | Layer | Purpose |
|-------|-------|---------|
| Green (#1e5128) | L1 | ML inference (off-chain) |
| Red (#3d0c11) | L2 | Blockchain (commitments only) |
| Purple (#1b1464) | L3 | ZK proofs |
