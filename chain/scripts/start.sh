#!/bin/bash
# Start the ZK Credit Consortium Fabric Network
# T31a: 3 endorsers + 1 read-only regulatory observer

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$PROJECT_DIR/docker"

echo "=============================================="
echo "ZK Credit Consortium - Start Network"
echo "=============================================="

# Check if crypto materials exist
if [ ! -d "$PROJECT_DIR/config/crypto-config" ]; then
    echo "ERROR: Crypto materials not found. Run ./scripts/generate.sh first."
    exit 1
fi

# Check if channel artifacts exist
if [ ! -f "$PROJECT_DIR/channel-artifacts/genesis.block" ]; then
    echo "ERROR: Channel artifacts not found. Run ./scripts/generate.sh first."
    exit 1
fi

# Stop any existing containers
echo ""
echo "Stopping any existing containers..."
cd "$DOCKER_DIR"
docker-compose down --volumes --remove-orphans 2>/dev/null || true

# Start the network
echo ""
echo "Starting Fabric network..."
docker-compose up -d

# Wait for containers to start
echo ""
echo "Waiting for containers to initialize..."
sleep 5

# Check container status
echo ""
echo "Container status:"
docker-compose ps

# Check if all containers are running
RUNNING=$(docker-compose ps | grep -c "Up" || true)
EXPECTED=6  # orderer + 4 peers + cli

if [ "$RUNNING" -lt "$EXPECTED" ]; then
    echo ""
    echo "WARNING: Not all containers are running. Expected $EXPECTED, got $RUNNING"
    echo "Check logs with: docker-compose logs"
else
    echo ""
    echo "=============================================="
    echo "Network Started Successfully"
    echo "=============================================="
    echo ""
    echo "Nodes:"
    echo "  Orderer:            orderer.orderer.credit.ng:7050"
    echo "  CommercialBankA:    peer0.commercialbanka.credit.ng:7051 (endorser)"
    echo "  MicrofinanceB:      peer0.microfinanceb.credit.ng:8051 (endorser)"
    echo "  FintechC:           peer0.fintechc.credit.ng:9051 (endorser)"
    echo "  RegulatoryObserver: peer0.regulator.credit.ng:10051 (READ-ONLY)"
    echo ""
    echo "Next: Run ./scripts/create-channel.sh to create the credit channel"
fi
