#!/bin/bash
# Deploy credit chaincode to ZK Credit Consortium
# T31b: Only endorsing orgs can invoke write functions

set -e

CHANNEL_NAME="creditchannel"
CC_NAME="credit"
CC_VERSION="1.0"
CC_SEQUENCE="1"
CC_PATH="/opt/gopath/src/github.com/hyperledger/fabric-samples/chaincode/credit"

ORDERER_CA=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.credit.ng/orderers/orderer.orderer.credit.ng/msp/tlscacerts/tlsca.orderer.credit.ng-cert.pem
ORDERER_ADDRESS=orderer.orderer.credit.ng:7050

echo "=============================================="
echo "ZK Credit Consortium - Deploy Chaincode"
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

# Package chaincode
echo ""
echo "Packaging chaincode..."
setGlobals commercialbanka

cd $CC_PATH
GO111MODULE=on go mod vendor 2>/dev/null || true
cd -

peer lifecycle chaincode package ${CC_NAME}.tar.gz \
    --path $CC_PATH \
    --lang golang \
    --label ${CC_NAME}_${CC_VERSION}

echo "Chaincode packaged: ${CC_NAME}.tar.gz"

# Install on all peers (including regulator for query capability)
echo ""
echo "Installing chaincode on all peers..."

for ORG in commercialbanka microfinanceb fintechc regulator; do
    echo "  Installing on $ORG..."
    setGlobals $ORG
    peer lifecycle chaincode install ${CC_NAME}.tar.gz
done

# Get package ID
echo ""
echo "Getting package ID..."
setGlobals commercialbanka
PACKAGE_ID=$(peer lifecycle chaincode queryinstalled | grep "${CC_NAME}_${CC_VERSION}" | awk -F '[, ]+' '{print $3}')
echo "Package ID: $PACKAGE_ID"

# Approve for endorsing orgs (NOT regulator - they can't endorse)
echo ""
echo "Approving chaincode for endorsing orgs..."

for ORG in commercialbanka microfinanceb fintechc; do
    echo "  Approving for $ORG..."
    setGlobals $ORG
    peer lifecycle chaincode approveformyorg \
        -o $ORDERER_ADDRESS \
        --channelID $CHANNEL_NAME \
        --name $CC_NAME \
        --version $CC_VERSION \
        --package-id $PACKAGE_ID \
        --sequence $CC_SEQUENCE \
        --tls \
        --cafile $ORDERER_CA
done

# Note: Regulator does NOT approve - they are read-only

# Check commit readiness
echo ""
echo "Checking commit readiness..."
setGlobals commercialbanka
peer lifecycle chaincode checkcommitreadiness \
    --channelID $CHANNEL_NAME \
    --name $CC_NAME \
    --version $CC_VERSION \
    --sequence $CC_SEQUENCE \
    --output json

# Commit chaincode definition
echo ""
echo "Committing chaincode definition..."
setGlobals commercialbanka

# Build peer addresses for endorsing orgs only
PEER_ADDRESSES="--peerAddresses peer0.commercialbanka.credit.ng:7051 --tlsRootCertFiles /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/commercialbanka.credit.ng/peers/peer0.commercialbanka.credit.ng/tls/ca.crt"
PEER_ADDRESSES="$PEER_ADDRESSES --peerAddresses peer0.microfinanceb.credit.ng:8051 --tlsRootCertFiles /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/microfinanceb.credit.ng/peers/peer0.microfinanceb.credit.ng/tls/ca.crt"
PEER_ADDRESSES="$PEER_ADDRESSES --peerAddresses peer0.fintechc.credit.ng:9051 --tlsRootCertFiles /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/fintechc.credit.ng/peers/peer0.fintechc.credit.ng/tls/ca.crt"

peer lifecycle chaincode commit \
    -o $ORDERER_ADDRESS \
    --channelID $CHANNEL_NAME \
    --name $CC_NAME \
    --version $CC_VERSION \
    --sequence $CC_SEQUENCE \
    $PEER_ADDRESSES \
    --tls \
    --cafile $ORDERER_CA

# Verify deployment
echo ""
echo "Verifying deployment..."
peer lifecycle chaincode querycommitted --channelID $CHANNEL_NAME --name $CC_NAME

echo ""
echo "=============================================="
echo "Chaincode Deployment Complete"
echo "=============================================="
echo ""
echo "Chaincode: $CC_NAME v$CC_VERSION"
echo "Channel: $CHANNEL_NAME"
echo ""
echo "Functions available:"
echo "  - AnchorCommitment(commitmentHash, did, modelVersionHash)"
echo "  - GetCommitment(did)"
echo "  - RecordLoanEvent(did, eventType, proofHash, thresholdUsed)"
echo "  - GetCreditHistory(did)"
echo "  - RevokeCommitment(did)"
echo "  - CountVerifications(did)"
echo ""
echo "Access control:"
echo "  - Endorsers (CommercialBankA, MicrofinanceB, FintechC): full access"
echo "  - RegulatoryObserver: read-only (GetCommitment, GetCreditHistory, CountVerifications)"
echo ""
echo "Next: Run ./scripts/test-chaincode.sh to test the chaincode"
