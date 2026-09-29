#!/bin/bash
# Update BatchTimeout for benchmark comparison
# Usage: ./update_batch_timeout.sh <timeout_value>
# Examples: ./update_batch_timeout.sh 2s, ./update_batch_timeout.sh 500ms, ./update_batch_timeout.sh 200ms

set -e

TIMEOUT=${1:-"2s"}
CHANNEL_NAME="creditchannel"

echo "Updating BatchTimeout to $TIMEOUT..."

# Set peer environment
export CORE_PEER_LOCALMSPID="CommercialBankAMSP"
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_TLS_ROOTCERT_FILE=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/commercialbanka.credit.ng/peers/peer0.commercialbanka.credit.ng/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/commercialbanka.credit.ng/users/Admin@commercialbanka.credit.ng/msp
export CORE_PEER_ADDRESS=peer0.commercialbanka.credit.ng:7051

ORDERER_CA=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.credit.ng/orderers/orderer.orderer.credit.ng/msp/tlscacerts/tlsca.orderer.credit.ng-cert.pem
ORDERER_ADDRESS=orderer.orderer.credit.ng:7050

# Fetch current config
echo "Fetching current channel config..."
peer channel fetch config config_block.pb -o $ORDERER_ADDRESS -c $CHANNEL_NAME --tls --cafile $ORDERER_CA

# Decode config
configtxlator proto_decode --input config_block.pb --type common.Block | jq .data.data[0].payload.data.config > config.json

# Create modified config with new BatchTimeout
echo "Modifying BatchTimeout to $TIMEOUT..."
jq ".channel_group.groups.Orderer.values.BatchTimeout.value.timeout = \"$TIMEOUT\"" config.json > modified_config.json

# Encode configs
configtxlator proto_encode --input config.json --type common.Config --output config.pb
configtxlator proto_encode --input modified_config.json --type common.Config --output modified_config.pb

# Compute update
configtxlator compute_update --channel_id $CHANNEL_NAME --original config.pb --updated modified_config.pb --output config_update.pb

# Wrap in envelope
echo '{"payload":{"header":{"channel_header":{"channel_id":"'$CHANNEL_NAME'","type":2}},"data":{"config_update":'$(configtxlator proto_decode --input config_update.pb --type common.ConfigUpdate | jq -c .)'}}}'  | jq . > config_update_in_envelope.json
configtxlator proto_encode --input config_update_in_envelope.json --type common.Envelope --output config_update_in_envelope.pb

# Sign and submit
echo "Signing and submitting config update..."
peer channel signconfigtx -f config_update_in_envelope.pb

peer channel update -f config_update_in_envelope.pb -c $CHANNEL_NAME -o $ORDERER_ADDRESS --tls --cafile $ORDERER_CA

echo "BatchTimeout updated to $TIMEOUT"

# Clean up
rm -f config_block.pb config.json modified_config.json config.pb modified_config.pb config_update.pb config_update_in_envelope.json config_update_in_envelope.pb

echo "Done!"
