#!/bin/bash
# Create and join credit channel for ZK Credit Consortium
# T31a: All 4 orgs join, but only 3 can endorse

set -e

CHANNEL_NAME="creditchannel"
ORDERER_CA=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.credit.ng/orderers/orderer.orderer.credit.ng/msp/tlscacerts/tlsca.orderer.credit.ng-cert.pem
ORDERER_ADDRESS=orderer.orderer.credit.ng:7050

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

# Create channel
echo ""
echo "Creating channel: $CHANNEL_NAME"
setGlobals commercialbanka

peer channel create \
    -o $ORDERER_ADDRESS \
    -c $CHANNEL_NAME \
    -f /opt/gopath/src/github.com/hyperledger/fabric/peer/channel-artifacts/${CHANNEL_NAME}.tx \
    --outputBlock /opt/gopath/src/github.com/hyperledger/fabric/peer/channel-artifacts/${CHANNEL_NAME}.block \
    --tls \
    --cafile $ORDERER_CA

echo "Channel created successfully"

# Join all peers to channel
echo ""
echo "Joining peers to channel..."

for ORG in commercialbanka microfinanceb fintechc regulator; do
    echo "  Joining $ORG..."
    setGlobals $ORG
    peer channel join -b /opt/gopath/src/github.com/hyperledger/fabric/peer/channel-artifacts/${CHANNEL_NAME}.block
done

echo ""
echo "All peers joined channel"

# Update anchor peers for endorsing orgs
echo ""
echo "Updating anchor peers..."

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

# Also update anchor for regulator (for gossip)
echo "  Updating anchor for regulator..."
setGlobals regulator
peer channel update \
    -o $ORDERER_ADDRESS \
    -c $CHANNEL_NAME \
    -f /opt/gopath/src/github.com/hyperledger/fabric/peer/channel-artifacts/RegulatoryObserverMSPanchors.tx \
    --tls \
    --cafile $ORDERER_CA

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
echo ""
echo "Next: Run ./scripts/deploy-chaincode.sh to deploy the credit chaincode"
