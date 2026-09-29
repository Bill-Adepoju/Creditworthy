#!/bin/bash
# Generate crypto materials using Docker (no local Fabric binaries needed)
# T31a: 3 endorsers + 1 read-only regulatory observer

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$PROJECT_DIR/config"
CHANNEL_ARTIFACTS_DIR="$PROJECT_DIR/channel-artifacts"

CHANNEL_NAME="creditchannel"
FABRIC_VERSION="2.5"

echo "=============================================="
echo "ZK Credit Consortium - Generate Crypto (Docker)"
echo "=============================================="

# Clean previous artifacts
echo ""
echo "Cleaning previous artifacts..."
rm -rf "$CONFIG_DIR/crypto-config"
rm -rf "$CHANNEL_ARTIFACTS_DIR"
mkdir -p "$CHANNEL_ARTIFACTS_DIR"

# Generate crypto materials using fabric-tools container
echo ""
echo "Generating crypto materials..."
docker run --rm \
    -v "$CONFIG_DIR:/config" \
    -w /config \
    hyperledger/fabric-tools:$FABRIC_VERSION \
    cryptogen generate --config=crypto-config.yaml --output=crypto-config

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to generate crypto materials"
    exit 1
fi

echo "Crypto materials generated successfully"

# Generate genesis block
echo ""
echo "Generating genesis block..."
docker run --rm \
    -v "$CONFIG_DIR:/config" \
    -v "$CHANNEL_ARTIFACTS_DIR:/channel-artifacts" \
    -e FABRIC_CFG_PATH=/config \
    -w /config \
    hyperledger/fabric-tools:$FABRIC_VERSION \
    configtxgen -profile CreditConsortiumGenesis -channelID system-channel -outputBlock /channel-artifacts/genesis.block

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to generate genesis block"
    exit 1
fi

# Generate channel creation transaction
echo ""
echo "Generating channel creation transaction..."
docker run --rm \
    -v "$CONFIG_DIR:/config" \
    -v "$CHANNEL_ARTIFACTS_DIR:/channel-artifacts" \
    -e FABRIC_CFG_PATH=/config \
    -w /config \
    hyperledger/fabric-tools:$FABRIC_VERSION \
    configtxgen -profile CreditChannel -outputCreateChannelTx /channel-artifacts/${CHANNEL_NAME}.tx -channelID $CHANNEL_NAME

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to generate channel creation transaction"
    exit 1
fi

# Generate anchor peer updates
echo ""
echo "Generating anchor peer updates..."
for ORG in CommercialBankA MicrofinanceB FintechC RegulatoryObserver; do
    echo "  - ${ORG}MSP anchor peer update"
    docker run --rm \
        -v "$CONFIG_DIR:/config" \
        -v "$CHANNEL_ARTIFACTS_DIR:/channel-artifacts" \
        -e FABRIC_CFG_PATH=/config \
        -w /config \
        hyperledger/fabric-tools:$FABRIC_VERSION \
        configtxgen -profile CreditChannel -outputAnchorPeersUpdate /channel-artifacts/${ORG}MSPanchors.tx -channelID $CHANNEL_NAME -asOrg ${ORG}MSP
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
