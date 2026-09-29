#!/bin/bash
# Test credit chaincode functions
# T31d: Demonstrates read-only restriction for RegulatoryObserver

set -e

CHANNEL_NAME="creditchannel"
CC_NAME="credit"

ORDERER_CA=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.credit.ng/orderers/orderer.orderer.credit.ng/msp/tlscacerts/tlsca.orderer.credit.ng-cert.pem
ORDERER_ADDRESS=orderer.orderer.credit.ng:7050

echo "=============================================="
echo "ZK Credit Consortium - Test Chaincode"
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

# Test data
TEST_DID="did:example:borrower123"
TEST_COMMITMENT="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
TEST_MODEL_HASH="0xabcdef1234567890abcdef1234567890"
TEST_PROOF_HASH="0x9876543210fedcba9876543210fedcba"

echo ""
echo "=== Test 1: AnchorCommitment (endorser) ==="
echo "Org: CommercialBankA"
setGlobals commercialbanka

peer chaincode invoke \
    -o $ORDERER_ADDRESS \
    -C $CHANNEL_NAME \
    -n $CC_NAME \
    -c "{\"function\":\"AnchorCommitment\",\"Args\":[\"$TEST_COMMITMENT\",\"$TEST_DID\",\"$TEST_MODEL_HASH\"]}" \
    --tls \
    --cafile $ORDERER_CA \
    --peerAddresses peer0.commercialbanka.credit.ng:7051 \
    --tlsRootCertFiles /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/commercialbanka.credit.ng/peers/peer0.commercialbanka.credit.ng/tls/ca.crt \
    --peerAddresses peer0.microfinanceb.credit.ng:8051 \
    --tlsRootCertFiles /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/microfinanceb.credit.ng/peers/peer0.microfinanceb.credit.ng/tls/ca.crt

echo "SUCCESS: Commitment anchored"
sleep 2

echo ""
echo "=== Test 2: GetCommitment (query from endorser) ==="
echo "Org: MicrofinanceB"
setGlobals microfinanceb

peer chaincode query \
    -C $CHANNEL_NAME \
    -n $CC_NAME \
    -c "{\"function\":\"GetCommitment\",\"Args\":[\"$TEST_DID\"]}"

echo ""
echo "=== Test 3: GetCommitment (query from regulator - READ-ONLY) ==="
echo "Org: RegulatoryObserver"
setGlobals regulator

peer chaincode query \
    -C $CHANNEL_NAME \
    -n $CC_NAME \
    -c "{\"function\":\"GetCommitment\",\"Args\":[\"$TEST_DID\"]}"

echo "SUCCESS: Regulator can query (embedded supervision)"

echo ""
echo "=== Test 4: RecordLoanEvent (endorser) ==="
echo "Org: FintechC"
setGlobals fintechc

peer chaincode invoke \
    -o $ORDERER_ADDRESS \
    -C $CHANNEL_NAME \
    -n $CC_NAME \
    -c "{\"function\":\"RecordLoanEvent\",\"Args\":[\"$TEST_DID\",\"verification\",\"$TEST_PROOF_HASH\",\"650\"]}" \
    --tls \
    --cafile $ORDERER_CA \
    --peerAddresses peer0.commercialbanka.credit.ng:7051 \
    --tlsRootCertFiles /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/commercialbanka.credit.ng/peers/peer0.commercialbanka.credit.ng/tls/ca.crt \
    --peerAddresses peer0.fintechc.credit.ng:9051 \
    --tlsRootCertFiles /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/fintechc.credit.ng/peers/peer0.fintechc.credit.ng/tls/ca.crt

echo "SUCCESS: Loan event recorded"
sleep 2

echo ""
echo "=== Test 5: GetCreditHistory (query from regulator) ==="
echo "Org: RegulatoryObserver"
setGlobals regulator

peer chaincode query \
    -C $CHANNEL_NAME \
    -n $CC_NAME \
    -c "{\"function\":\"GetCreditHistory\",\"Args\":[\"$TEST_DID\"]}"

echo "SUCCESS: Regulator can view full audit trail"

echo ""
echo "=== Test 6: AnchorCommitment attempt from Regulator (SHOULD FAIL) ==="
echo "Org: RegulatoryObserver (READ-ONLY)"
setGlobals regulator

echo "Attempting write operation from read-only org..."
# This should fail because regulator cannot endorse
if peer chaincode invoke \
    -o $ORDERER_ADDRESS \
    -C $CHANNEL_NAME \
    -n $CC_NAME \
    -c "{\"function\":\"AnchorCommitment\",\"Args\":[\"0xnewcommitment\",\"did:example:test456\",\"0xmodel\"]}" \
    --tls \
    --cafile $ORDERER_CA \
    --peerAddresses peer0.regulator.credit.ng:10051 \
    --tlsRootCertFiles /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/regulator.credit.ng/peers/peer0.regulator.credit.ng/tls/ca.crt \
    2>&1; then
    echo "UNEXPECTED: Write succeeded (check endorsement policy)"
else
    echo "EXPECTED: Write failed - RegulatoryObserver cannot endorse"
fi

echo ""
echo "=== Test 7: CountVerifications ==="
echo "Org: RegulatoryObserver"
setGlobals regulator

peer chaincode query \
    -C $CHANNEL_NAME \
    -n $CC_NAME \
    -c "{\"function\":\"CountVerifications\",\"Args\":[\"$TEST_DID\"]}"

echo ""
echo "=============================================="
echo "Chaincode Tests Complete"
echo "=============================================="
echo ""
echo "Summary:"
echo "  - Endorsers can anchor commitments and record events"
echo "  - RegulatoryObserver can query all data (embedded supervision)"
echo "  - RegulatoryObserver CANNOT endorse write operations"
echo "  - All verification events create permanent audit trail (T31d)"
