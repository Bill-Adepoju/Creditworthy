# Layer 2: Hyperledger Fabric Consortium Network

ZK Credit Scoring consortium network implementation for T31.

## Architecture

```
                    +------------------+
                    |   Raft Orderer   |
                    | (orderer.credit) |
                    +--------+---------+
                             |
        +--------------------+--------------------+
        |                    |                    |
+-------v-------+    +-------v-------+    +-------v-------+
| CommercialBankA|   | MicrofinanceB |   |   FintechC    |
|   (endorser)  |    |   (endorser)  |   |   (endorser)  |
+---------------+    +---------------+    +---------------+
        |                    |                    |
        +--------------------+--------------------+
                             |
                    +--------v---------+
                    | RegulatoryObserver|
                    |   (READ-ONLY)    |
                    +------------------+
```

## Organizations

| Org | MSP ID | Role | Capabilities |
|-----|--------|------|--------------|
| CommercialBankA | CommercialBankAMSP | Endorser | Read, Write, Endorse |
| MicrofinanceB | MicrofinanceBMSP | Endorser | Read, Write, Endorse |
| FintechC | FintechCMSP | Endorser | Read, Write, Endorse |
| RegulatoryObserver | RegulatoryObserverMSP | Observer | Read ONLY |

The RegulatoryObserver implements "embedded supervision" per Auer (2022) - they can observe all transactions in real-time but cannot modify ledger state.

## Chaincode Functions

### Write Operations (Endorsers Only)

- `AnchorCommitment(commitmentHash, did, modelVersionHash)` - Store Poseidon commitment
- `RecordLoanEvent(did, eventType, proofHash, thresholdUsed)` - Record verification/loan event
- `RevokeCommitment(did)` - Mark commitment as revoked

### Read Operations (All Orgs)

- `GetCommitment(did)` - Retrieve commitment by DID
- `GetCreditHistory(did)` - Get all events for a DID
- `CountVerifications(did)` - Count verification attempts

## Data Model

### Commitment (on-chain)
```json
{
  "commitmentHash": "Poseidon(score, salt)",
  "did": "borrower DID",
  "modelVersionHash": "hash of ML model",
  "issuerMSP": "issuing org",
  "timestamp": "ISO8601",
  "status": "active|revoked",
  "txId": "transaction ID"
}
```

### LoanEvent (on-chain)
```json
{
  "eventId": "unique ID",
  "did": "borrower DID",
  "eventType": "verification|approval|rejection|default|repayment",
  "proofHash": "hash of ZK proof",
  "thresholdUsed": 650,
  "issuerMSP": "recording org",
  "timestamp": "ISO8601",
  "txId": "transaction ID"
}
```

**Privacy Note:** Raw scores, behavioural features, PII, and model weights are NEVER stored on-chain. Only commitments and hashes.

## Setup

### Prerequisites

- Docker & Docker Compose
- Hyperledger Fabric binaries v2.5+ (`cryptogen`, `configtxgen`)
- Go 1.21+

### Quick Start

```bash
# Complete setup (generates, starts, deploys, tests)
./scripts/setup-all.sh

# Or step by step:
./scripts/generate.sh      # Generate crypto materials
./scripts/start.sh         # Start Docker containers
docker exec cli ./scripts/create-channel.sh
docker exec cli ./scripts/deploy-chaincode.sh
docker exec cli ./scripts/test-chaincode.sh

# Stop network
./scripts/stop.sh
```

## Directory Structure

```
chain/
  config/
    crypto-config.yaml     # Org definitions
    configtx.yaml          # Channel config
    crypto-config/         # Generated crypto materials
  chaincode/
    credit/
      credit.go            # Chaincode implementation
      go.mod               # Go module
  docker/
    docker-compose.yaml    # Container definitions
  scripts/
    generate.sh            # Generate crypto
    start.sh               # Start network
    create-channel.sh      # Create/join channel
    deploy-chaincode.sh    # Deploy chaincode
    test-chaincode.sh      # Test functions
    stop.sh                # Stop network
  channel-artifacts/       # Generated channel tx
```

## T31 Compliance

- **T31a:** Raft ordering, 3 endorsers + 1 read-only observer
- **T31b:** Chaincode stores only commitments (never raw scores)
- **T31d:** All verifications recorded for audit trail
