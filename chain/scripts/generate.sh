#!/bin/bash
# Generate crypto materials and channel artifacts for ZK Credit Consortium
# T31a: 3 endorsers + 1 read-only regulatory observer

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$PROJECT_DIR/config"
CHANNEL_ARTIFACTS_DIR="$PROJECT_DIR/channel-artifacts"

CHANNEL_NAME="creditchannel"

echo "=============================================="
echo "ZK Credit Consortium - Generate Crypto & Artifacts"
echo "=============================================="

# Check for required tools
command -v cryptogen >/dev/null 2>&1 || { echo "cryptogen not found. Please install Fabric binaries."; exit 1; }
command -v configtxgen >/dev/null 2>&1 || { echo "configtxgen not found. Please install Fabric binaries."; exit 1; }

# Clean previous artifacts
echo ""
echo "Cleaning previous artifacts..."
rm -rf "$CONFIG_DIR/crypto-config"
rm -rf "$CHANNEL_ARTIFACTS_DIR"
mkdir -p "$CHANNEL_ARTIFACTS_DIR"

# Generate crypto materials
echo ""
echo "Generating crypto materials..."
cd "$CONFIG_DIR"
cryptogen generate --config=crypto-config.yaml --output=crypto-config

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to generate crypto materials"
    exit 1
fi

echo "Crypto materials generated successfully"
echo "  - OrdererOrg: orderer.credit.ng"
echo "  - CommercialBankA: commercialbanka.credit.ng (endorser)"
echo "  - MicrofinanceB: microfinanceb.credit.ng (endorser)"
echo "  - FintechC: fintechc.credit.ng (endorser)"
echo "  - RegulatoryObserver: regulator.credit.ng (READ-ONLY)"

# Set FABRIC_CFG_PATH for configtxgen
export FABRIC_CFG_PATH="$CONFIG_DIR"

# Generate genesis block
echo ""
echo "Generating genesis block..."
configtxgen -profile CreditConsortiumGenesis -channelID system-channel -outputBlock "$CHANNEL_ARTIFACTS_DIR/genesis.block"

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to generate genesis block"
    exit 1
fi

# Generate channel creation transaction
echo ""
echo "Generating channel creation transaction..."
configtxgen -profile CreditChannel -outputCreateChannelTx "$CHANNEL_ARTIFACTS_DIR/${CHANNEL_NAME}.tx" -channelID $CHANNEL_NAME

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to generate channel creation transaction"
    exit 1
fi

# Generate anchor peer updates for each endorsing org
echo ""
echo "Generating anchor peer updates..."

for ORG in CommercialBankA MicrofinanceB FintechC RegulatoryObserver; do
    echo "  - ${ORG}MSP anchor peer update"
    configtxgen -profile CreditChannel -outputAnchorPeersUpdate "$CHANNEL_ARTIFACTS_DIR/${ORG}MSPanchors.tx" -channelID $CHANNEL_NAME -asOrg ${ORG}MSP
done

echo ""
echo "=============================================="
echo "Artifact Generation Complete"
echo "=============================================="
echo ""
echo "Generated files:"
echo "  Crypto:   $CONFIG_DIR/crypto-config/"
echo "  Genesis:  $CHANNEL_ARTIFACTS_DIR/genesis.block"
echo "  Channel:  $CHANNEL_ARTIFACTS_DIR/${CHANNEL_NAME}.tx"
echo "  Anchors:  $CHANNEL_ARTIFACTS_DIR/*anchors.tx"
echo ""
echo "Next: Run ./scripts/start.sh to start the network"
