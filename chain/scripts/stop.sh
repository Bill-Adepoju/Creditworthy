#!/bin/bash
# Stop and clean up the ZK Credit Consortium Fabric Network

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$PROJECT_DIR/docker"

echo "=============================================="
echo "ZK Credit Consortium - Stop Network"
echo "=============================================="

cd "$DOCKER_DIR"

# Stop containers
echo "Stopping containers..."
docker-compose down --volumes --remove-orphans

# Optional: clean up chaincode containers and images
echo ""
echo "Cleaning up chaincode containers..."
docker rm -f $(docker ps -aq --filter "name=dev-peer") 2>/dev/null || true
docker rmi -f $(docker images -q "dev-peer*") 2>/dev/null || true

echo ""
echo "Network stopped and cleaned up"
