/**
 * Debug benchmark to see errors
 */
const { execSync } = require('child_process');

const CONFIG = {
    channelName: 'creditchannel',
    chaincodeName: 'credit',
    orderer: 'orderer.orderer.credit.ng:7050',
};

const ORDERER_CA = '/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.credit.ng/orderers/orderer.orderer.credit.ng/msp/tlscacerts/tlsca.orderer.credit.ng-cert.pem';

const PEERS = [
    { name: 'commercialbanka', address: 'peer0.commercialbanka.credit.ng:7051', tlsCert: '/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/commercialbanka.credit.ng/peers/peer0.commercialbanka.credit.ng/tls/ca.crt' },
    { name: 'microfinanceb', address: 'peer0.microfinanceb.credit.ng:8051', tlsCert: '/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/microfinanceb.credit.ng/peers/peer0.microfinanceb.credit.ng/tls/ca.crt' },
    { name: 'fintechc', address: 'peer0.fintechc.credit.ng:9051', tlsCert: '/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/fintechc.credit.ng/peers/peer0.fintechc.credit.ng/tls/ca.crt' }
];

function generateDID() {
    return `did:credit:debug${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

function generateCommitmentHash() {
    const hex = '0123456789abcdef';
    let hash = '0x';
    for (let i = 0; i < 64; i++) {
        hash += hex[Math.floor(Math.random() * 16)];
    }
    return hash;
}

function anchorCommitment(did, commitmentHash) {
    const peerArgs = PEERS.map(p => `--peerAddresses ${p.address} --tlsRootCertFiles ${p.tlsCert}`).join(' ');
    const cmd = `docker exec cli bash -c 'peer chaincode invoke -o ${CONFIG.orderer} --channelID ${CONFIG.channelName} --name ${CONFIG.chaincodeName} --tls --cafile ${ORDERER_CA} ${peerArgs} -c "{\\"function\\":\\"AnchorCommitment\\",\\"Args\\":[\\"${commitmentHash}\\",\\"${did}\\",\\"model_v1\\"]}" --waitForEvent 2>&1'`;

    console.log('Running command:');
    console.log(cmd);
    console.log('');

    try {
        const result = execSync(cmd, { encoding: 'utf8', timeout: 60000 });
        console.log('SUCCESS:');
        console.log(result);
        return { success: true, output: result };
    } catch (error) {
        console.log('ERROR:');
        console.log('stdout:', error.stdout);
        console.log('stderr:', error.stderr);
        console.log('message:', error.message);
        return { success: false, error: error.message };
    }
}

const did = generateDID();
const hash = generateCommitmentHash();
console.log('Testing with DID:', did);
console.log('Testing with Hash:', hash);
console.log('');
anchorCommitment(did, hash);
