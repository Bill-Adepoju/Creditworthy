#!/bin/bash
# Create and join credit channel using Fabric 2.5 Channel Participation API
# T31a: All 4 orgs join, but only 3 can endorse

set -e

CHANNEL_NAME="creditchannel"
ORDERER_CA=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.credit.ng/orderers/orderer.orderer.credit.ng/msp/tlscacerts/tlsca.orderer.credit.ng-cert.pem
ORDERER_ADDRESS=orderer.orderer.credit.ng:7050
ORDERER_ADMIN_ADDRESS=orderer.orderer.credit.ng:7053

export CORE_PEER_TLS_ENABLED=true

echo "=============================================="
echo "ZK Credit Consortium - Create & Join Channel"
echo "=============================================="

# Function to set peer environment
setGlobals() {
    local ORG=$1
    case $ORG in
        commercialbanka)
            export CORE_PEER_LOCALMSPID="CommercialBankAMSP"
            export CORE_PEER_TLS_ROOTCERT_FILE=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/commercialbanka.credit.ng/peers/peer0.commercialbanka.credit.ng/tls/ca.crt
            export CORE_PEER_MSPCONFIGPATH=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/commercialbanka.credit.ng/users/Admin@commercialbanka.credit.ng/msp
            export CORE_PEER_ADDRESS=peer0.commercialbanka.credit.ng:7051
            ;;
        microfinanceb)
            export CORE_PEER_LOCALMSPID="MicrofinanceBMSP"
            export CORE_PEER_TLS_ROOTCERT_FILE=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/microfinanceb.credit.ng/peers/peer0.microfinanceb.credit.ng/tls/ca.crt
            export CORE_PEER_MSPCONFIGPATH=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/microfinanceb.credit.ng/users/Admin@microfinanceb.credit.ng/msp
            export CORE_PEER_ADDRESS=peer0.microfinanceb.credit.ng:8051
            ;;
        fintechc)
            export CORE_PEER_LOCALMSPID="FintechCMSP"
            export CORE_PEER_TLS_ROOTCERT_FILE=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/fintechc.credit.ng/peers/peer0.fintechc.credit.ng/tls/ca.crt
            export CORE_PEER_MSPCONFIGPATH=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/fintechc.credit.ng/users/Admin@fintechc.credit.ng/msp
            export CORE_PEER_ADDRESS=peer0.fintechc.credit.ng:9051
            ;;
        regulator)
            export CORE_PEER_LOCALMSPID="RegulatoryObserverMSP"
            export CORE_PEER_TLS_ROOTCERT_FILE=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/regulator.credit.ng/peers/peer0.regulator.credit.ng/tls/ca.crt
            export CORE_PEER_MSPCONFIGPATH=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/regulator.credit.ng/users/Admin@regulator.credit.ng/msp
            export CORE_PEER_ADDRESS=peer0.regulator.credit.ng:10051
            ;;
    esac
}

# First, join orderer to the channel using osnadmin
echo ""
echo "Step 1: Joining orderer to channel using osnadmin..."

ORDERER_ADMIN_TLS=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.credit.ng/orderers/orderer.orderer.credit.ng/tls

osnadmin channel join \
    --channelID $CHANNEL_NAME \
    --config-block /opt/gopath/src/github.com/hyperledger/fabric/peer/channel-artifacts/genesis.block \
    -o $ORDERER_ADMIN_ADDRESS \
    --ca-file $ORDERER_CA \
    --client-cert $ORDERER_ADMIN_TLS/server.crt \
    --client-key $ORDERER_ADMIN_TLS/server.key

echo "Orderer joined channel"

# Fetch the genesis block from orderer
echo ""
echo "Step 2: Fetching genesis block..."
setGlobals commercialbanka

peer channel fetch oldest /opt/gopath/src/github.com/hyperledger/fabric/peer/channel-artifacts/${CHANNEL_NAME}_genesis.block \
    -c $CHANNEL_NAME \
    -o $ORDERER_ADDRESS \
    --tls \
    --cafile $ORDERER_CA

# Join all peers to channel
echo ""
echo "Step 3: Joining peers to channel..."

for ORG in commercialbanka microfinanceb fintechc regulator; do
    echo "  Joining $ORG..."
    setGlobals $ORG
    peer channel join -b /opt/gopath/src/github.com/hyperledger/fabric/peer/channel-artifacts/${CHANNEL_NAME}_genesis.block
done

echo ""
echo "All peers joined channel"

# Update anchor peers for endorsing orgs
echo ""
echo "Step 4: Updating anchor peers..."

for ORG in commercialbanka microfinanceb fintechc; do
    echo "  Updating anchor for $ORG..."
    setGlobals $ORG

    # Map org name to MSP name
    case $ORG in
        commercialbanka) MSP="CommercialBankA" ;;
        microfinanceb) MSP="MicrofinanceB" ;;
        fintechc) MSP="FintechC" ;;
    esac

    peer channel update \
        -o $ORDERER_ADDRESS \
        -c $CHANNEL_NAME \
        -f /opt/gopath/src/github.com/hyperledger/fabric/peer/channel-artifacts/${MSP}MSPanchors.tx \
        --tls \
        --cafile $ORDERER_CA
done

echo ""
echo "=============================================="
echo "Channel Setup Complete"
echo "=============================================="
echo ""
echo "Channel: $CHANNEL_NAME"
echo "Members:"
echo "  - CommercialBankA (endorser)"
echo "  - MicrofinanceB (endorser)"
echo "  - FintechC (endorser)"
echo "  - RegulatoryObserver (READ-ONLY)"
