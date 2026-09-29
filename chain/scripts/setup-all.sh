#!/bin/bash
# Complete setup script for ZK Credit Consortium Fabric Network
# Runs: generate -> start -> create-channel -> deploy-chaincode -> test

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=============================================="
echo "ZK Credit Consortium - Complete Setup"
echo "=============================================="
echo ""
echo "This script will:"
echo "  1. Generate crypto materials and channel artifacts"
echo "  2. Start the Fabric network (Docker containers)"
echo "  3. Create and join the credit channel"
echo "  4. Deploy the credit chaincode"
echo "  5. Run chaincode tests"
echo ""
echo "Prerequisites:"
echo "  - Docker and Docker Compose installed"
echo "  - Fabric binaries (cryptogen, configtxgen) in PATH"
echo "  - Go 1.21+ installed (for chaincode)"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Step 1: Generate
echo ""
echo "========== Step 1/5: Generate Crypto Materials =========="
"$SCRIPT_DIR/generate.sh"

# Step 2: Start
echo ""
echo "========== Step 2/5: Start Network =========="
"$SCRIPT_DIR/start.sh"

# Wait for network to stabilize
echo "Waiting for network to stabilize..."
sleep 10

# Step 3: Create channel (run inside CLI container)
echo ""
echo "========== Step 3/5: Create & Join Channel =========="
docker exec cli /opt/gopath/src/github.com/hyperledger/fabric/peer/scripts/create-channel.sh

# Step 4: Deploy chaincode
echo ""
echo "========== Step 4/5: Deploy Chaincode =========="
docker exec cli /opt/gopath/src/github.com/hyperledger/fabric/peer/scripts/deploy-chaincode.sh

# Step 5: Test
echo ""
echo "========== Step 5/5: Test Chaincode =========="
docker exec cli /opt/gopath/src/github.com/hyperledger/fabric/peer/scripts/test-chaincode.sh

echo ""
echo "=============================================="
echo "Setup Complete!"
echo "=============================================="
echo ""
echo "Network is running with:"
echo "  - 1 Orderer (Raft)"
echo "  - 3 Endorsing peers (CommercialBankA, MicrofinanceB, FintechC)"
echo "  - 1 Read-only peer (RegulatoryObserver)"
echo ""
echo "Chaincode 'credit' is deployed on channel 'creditchannel'"
echo ""
echo "To interact with the network:"
echo "  docker exec -it cli bash"
echo ""
echo "To stop the network:"
echo "  ./scripts/stop.sh"
