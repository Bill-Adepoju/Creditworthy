#!/bin/bash
# Update channel configuration parameter
# Usage: update_config.sh <param_name> <value>
# param_name: MaxMessageCount or BatchTimeout
# value: numeric for MaxMessageCount, string for BatchTimeout (e.g., "500ms")

set -e

PARAM_NAME=$1
VALUE=$2
CHANNEL_NAME="creditchannel"

ORDERER_CA=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.credit.ng/orderers/orderer.orderer.credit.ng/msp/tlscacerts/tlsca.orderer.credit.ng-cert.pem
ORDERER_ADDRESS=orderer.orderer.credit.ng:7050

echo "Updating $PARAM_NAME to $VALUE..."

# Use orderer admin credentials for orderer config updates
export CORE_PEER_LOCALMSPID="OrdererMSP"
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_TLS_ROOTCERT_FILE=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.credit.ng/orderers/orderer.orderer.credit.ng/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.credit.ng/users/Admin@orderer.credit.ng/msp
export CORE_PEER_ADDRESS=peer0.commercialbanka.credit.ng:7051

cd /tmp

# Fetch current config
peer channel fetch config config_block.pb -o $ORDERER_ADDRESS -c $CHANNEL_NAME --tls --cafile $ORDERER_CA

# Decode to JSON
configtxlator proto_decode --input config_block.pb --type common.Block | jq .data.data[0].payload.data.config > config.json

# Modify based on parameter
if [ "$PARAM_NAME" == "MaxMessageCount" ]; then
    jq ".channel_group.groups.Orderer.values.BatchSize.value.max_message_count = $VALUE" config.json > modified_config.json
elif [ "$PARAM_NAME" == "BatchTimeout" ]; then
    jq ".channel_group.groups.Orderer.values.BatchTimeout.value.timeout = \"$VALUE\"" config.json > modified_config.json
else
    echo "Unknown parameter: $PARAM_NAME"
    exit 1
fi

# Encode both configs
configtxlator proto_encode --input config.json --type common.Config --output config.pb
configtxlator proto_encode --input modified_config.json --type common.Config --output modified_config.pb

# Compute update
configtxlator compute_update --channel_id $CHANNEL_NAME --original config.pb --updated modified_config.pb --output config_update.pb

# Decode the update to JSON
configtxlator proto_decode --input config_update.pb --type common.ConfigUpdate > config_update.json

# Create envelope manually
cat > config_update_envelope.json << ENVELOPE
{
  "payload": {
    "header": {
      "channel_header": {
        "channel_id": "$CHANNEL_NAME",
        "type": 2
      }
    },
    "data": {
      "config_update": $(cat config_update.json)
    }
  }
}
ENVELOPE

# Encode envelope
configtxlator proto_encode --input config_update_envelope.json --type common.Envelope --output config_update_envelope.pb

# Sign and submit
peer channel signconfigtx -f config_update_envelope.pb
peer channel update -f config_update_envelope.pb -c $CHANNEL_NAME -o $ORDERER_ADDRESS --tls --cafile $ORDERER_CA

echo "$PARAM_NAME updated to $VALUE successfully"

# Clean up
rm -f config_block.pb config.json modified_config.json config.pb modified_config.pb config_update.pb config_update.json config_update_envelope.json config_update_envelope.pb
