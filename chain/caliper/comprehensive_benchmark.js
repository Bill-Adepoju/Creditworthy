/**
 * T31c: Comprehensive Fabric Benchmark
 * Measures latency for all chaincode operations via sequential execution.
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const CONFIG = {
    channelName: 'creditchannel',
    chaincodeName: 'credit',
    numWriteTests: 30,
    numReadTests: 50,
    resultsDir: path.join(__dirname, '../../results')
};

const ORDERER_CA = '/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.credit.ng/orderers/orderer.orderer.credit.ng/msp/tlscacerts/tlsca.orderer.credit.ng-cert.pem';

const PEERS = [
    { address: 'peer0.commercialbanka.credit.ng:7051', tlsCert: '/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/commercialbanka.credit.ng/peers/peer0.commercialbanka.credit.ng/tls/ca.crt' },
    { address: 'peer0.microfinanceb.credit.ng:8051', tlsCert: '/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/microfinanceb.credit.ng/peers/peer0.microfinanceb.credit.ng/tls/ca.crt' },
    { address: 'peer0.fintechc.credit.ng:9051', tlsCert: '/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/fintechc.credit.ng/peers/peer0.fintechc.credit.ng/tls/ca.crt' }
];

function generateDID() {
    return `did:credit:b${Date.now()}${Math.random().toString(36).substr(2, 6)}`;
}

function generateHash() {
    const hex = '0123456789abcdef';
    let hash = '0x';
    for (let i = 0; i < 64; i++) hash += hex[Math.floor(Math.random() * 16)];
    return hash;
}

function runDockerCmd(innerCmd) {
    const cmd = `docker exec cli bash -c "${innerCmd}"`;
    const start = process.hrtime.bigint();
    try {
        const result = execSync(cmd, { encoding: 'utf8', timeout: 120000, stdio: ['pipe', 'pipe', 'pipe'] });
        const latencyMs = Number(process.hrtime.bigint() - start) / 1_000_000;
        return { success: true, latencyMs, output: result };
    } catch (error) {
        const latencyMs = Number(process.hrtime.bigint() - start) / 1_000_000;
        return { success: false, latencyMs, error: (error.stdout || '') + (error.stderr || '') };
    }
}

function anchorCommitment(did, hash) {
    const peerArgs = PEERS.map(p => `--peerAddresses ${p.address} --tlsRootCertFiles ${p.tlsCert}`).join(' ');
    const cmd = `peer chaincode invoke -o orderer.orderer.credit.ng:7050 --channelID ${CONFIG.channelName} --name ${CONFIG.chaincodeName} --tls --cafile ${ORDERER_CA} ${peerArgs} -c '{\\\"function\\\":\\\"AnchorCommitment\\\",\\\"Args\\\":[\\\"${hash}\\\",\\\"${did}\\\",\\\"model_v1\\\"]}' --waitForEvent 2>&1`;
    return runDockerCmd(cmd);
}

function getCommitment(did) {
    const cmd = `peer chaincode query --channelID ${CONFIG.channelName} --name ${CONFIG.chaincodeName} -c '{\\\"function\\\":\\\"GetCommitment\\\",\\\"Args\\\":[\\\"${did}\\\"]}' 2>&1`;
    return runDockerCmd(cmd);
}

function recordLoanEvent(did, eventType, proofHash, threshold) {
    const peerArgs = PEERS.map(p => `--peerAddresses ${p.address} --tlsRootCertFiles ${p.tlsCert}`).join(' ');
    const cmd = `peer chaincode invoke -o orderer.orderer.credit.ng:7050 --channelID ${CONFIG.channelName} --name ${CONFIG.chaincodeName} --tls --cafile ${ORDERER_CA} ${peerArgs} -c '{\\\"function\\\":\\\"RecordLoanEvent\\\",\\\"Args\\\":[\\\"${did}\\\",\\\"${eventType}\\\",\\\"${proofHash}\\\",\\\"${threshold}\\\"]}' --waitForEvent 2>&1`;
    return runDockerCmd(cmd);
}

function getCreditHistory(did) {
    const cmd = `peer chaincode query --channelID ${CONFIG.channelName} --name ${CONFIG.chaincodeName} -c '{\\\"function\\\":\\\"GetCreditHistory\\\",\\\"Args\\\":[\\\"${did}\\\"]}' 2>&1`;
    return runDockerCmd(cmd);
}

function getBlockchainInfo() {
    return runDockerCmd(`peer channel getinfo -c ${CONFIG.channelName} 2>&1`);
}

function calcStats(vals) {
    if (!vals.length) return null;
    const sorted = [...vals].sort((a, b) => a - b);
    const sum = sorted.reduce((a, b) => a + b, 0);
    return {
        n: vals.length,
        min: Math.round(sorted[0]),
        max: Math.round(sorted[sorted.length - 1]),
        mean: Math.round(sum / vals.length),
        p50: Math.round(sorted[Math.floor(vals.length * 0.5)]),
        p95: Math.round(sorted[Math.floor(vals.length * 0.95)]),
        p99: vals.length >= 10 ? Math.round(sorted[Math.floor(vals.length * 0.99)]) : null
    };
}

async function main() {
    console.log('========================================');
    console.log('T31c: Comprehensive Fabric Benchmark');
    console.log('========================================\n');

    const results = {
        timestamp: new Date().toISOString(),
        task: 'T31c',
        hardware: {
            cpu: 'AMD Ryzen 7 4800H',
            cores: 8,
            threads: 16,
            ram_gb: 32,
            platform: 'Windows 10 / Docker Desktop'
        },
        network: {
            fabric_version: '2.5',
            ordering: 'Raft (single orderer)',
            orderer_count: 1,
            endorsers: 3,
            endorsement_policy: 'MAJORITY (3 of 4)',
            channel: 'creditchannel',
            chaincode_version: '1.1'
        },
        caveat: 'SINGLE ORDERER - not fault-tolerant. Sequential execution - latency includes Docker exec overhead (~500ms).',
        operations: {}
    };

    // Get initial blockchain info
    console.log('Getting blockchain info...');
    const bcInfo = getBlockchainInfo();
    if (bcInfo.success) {
        const match = bcInfo.output.match(/"height":(\d+)/);
        results.initial_height = match ? parseInt(match[1]) : null;
        console.log(`  Initial height: ${results.initial_height}\n`);
    }

    // Test 1: AnchorCommitment (Write)
    console.log(`Testing AnchorCommitment (n=${CONFIG.numWriteTests})...`);
    const writeLatencies = [];
    const createdDIDs = [];

    for (let i = 0; i < CONFIG.numWriteTests; i++) {
        const did = generateDID();
        const hash = generateHash();
        const result = anchorCommitment(did, hash);

        if (result.success && result.output.includes('Chaincode invoke successful')) {
            writeLatencies.push(result.latencyMs);
            createdDIDs.push(did);
        }
        process.stdout.write(`\r  Progress: ${i + 1}/${CONFIG.numWriteTests} (${writeLatencies.length} success)`);
    }
    console.log('');

    const writeStats = calcStats(writeLatencies);
    results.operations.AnchorCommitment = {
        type: 'write (endorsement + ordering + commit)',
        attempted: CONFIG.numWriteTests,
        successful: writeLatencies.length,
        success_rate: ((writeLatencies.length / CONFIG.numWriteTests) * 100).toFixed(1) + '%',
        latency_ms: writeStats,
        sequential_tps: writeStats ? (1000 / writeStats.mean).toFixed(2) : null
    };

    if (writeStats) {
        console.log(`  Success: ${writeLatencies.length}/${CONFIG.numWriteTests}`);
        console.log(`  Latency: mean=${writeStats.mean}ms, p95=${writeStats.p95}ms, min=${writeStats.min}ms, max=${writeStats.max}ms`);
        console.log(`  Sequential TPS: ${results.operations.AnchorCommitment.sequential_tps}`);
    }

    // Test 2: RecordLoanEvent (Write)
    console.log(`\nTesting RecordLoanEvent (n=${CONFIG.numWriteTests})...`);
    const eventLatencies = [];

    for (let i = 0; i < CONFIG.numWriteTests && createdDIDs.length > 0; i++) {
        const did = createdDIDs[i % createdDIDs.length];
        const proofHash = generateHash();
        const result = recordLoanEvent(did, 'verification', proofHash, '650');

        if (result.success && result.output.includes('Chaincode invoke successful')) {
            eventLatencies.push(result.latencyMs);
        }
        process.stdout.write(`\r  Progress: ${i + 1}/${CONFIG.numWriteTests} (${eventLatencies.length} success)`);
    }
    console.log('');

    const eventStats = calcStats(eventLatencies);
    results.operations.RecordLoanEvent = {
        type: 'write (endorsement + ordering + commit)',
        attempted: CONFIG.numWriteTests,
        successful: eventLatencies.length,
        success_rate: ((eventLatencies.length / CONFIG.numWriteTests) * 100).toFixed(1) + '%',
        latency_ms: eventStats,
        sequential_tps: eventStats ? (1000 / eventStats.mean).toFixed(2) : null
    };

    if (eventStats) {
        console.log(`  Success: ${eventLatencies.length}/${CONFIG.numWriteTests}`);
        console.log(`  Latency: mean=${eventStats.mean}ms, p95=${eventStats.p95}ms, min=${eventStats.min}ms, max=${eventStats.max}ms`);
        console.log(`  Sequential TPS: ${results.operations.RecordLoanEvent.sequential_tps}`);
    }

    // Test 3: GetCommitment (Read)
    console.log(`\nTesting GetCommitment (n=${CONFIG.numReadTests})...`);
    const readLatencies = [];

    for (let i = 0; i < CONFIG.numReadTests && createdDIDs.length > 0; i++) {
        const did = createdDIDs[i % createdDIDs.length];
        const result = getCommitment(did);

        if (result.success && result.output.includes('commitmentHash')) {
            readLatencies.push(result.latencyMs);
        }
        process.stdout.write(`\r  Progress: ${i + 1}/${CONFIG.numReadTests} (${readLatencies.length} success)`);
    }
    console.log('');

    const readStats = calcStats(readLatencies);
    results.operations.GetCommitment = {
        type: 'read (query single peer)',
        attempted: CONFIG.numReadTests,
        successful: readLatencies.length,
        success_rate: ((readLatencies.length / CONFIG.numReadTests) * 100).toFixed(1) + '%',
        latency_ms: readStats,
        sequential_qps: readStats ? (1000 / readStats.mean).toFixed(2) : null
    };

    if (readStats) {
        console.log(`  Success: ${readLatencies.length}/${CONFIG.numReadTests}`);
        console.log(`  Latency: mean=${readStats.mean}ms, p95=${readStats.p95}ms, min=${readStats.min}ms, max=${readStats.max}ms`);
        console.log(`  Sequential QPS: ${results.operations.GetCommitment.sequential_qps}`);
    }

    // Test 4: GetCreditHistory (Read - range query)
    console.log(`\nTesting GetCreditHistory (n=${Math.min(20, createdDIDs.length)})...`);
    const historyLatencies = [];

    for (let i = 0; i < Math.min(20, createdDIDs.length); i++) {
        const did = createdDIDs[i];
        const result = getCreditHistory(did);

        if (result.success) {
            historyLatencies.push(result.latencyMs);
        }
        process.stdout.write(`\r  Progress: ${i + 1}/${Math.min(20, createdDIDs.length)} (${historyLatencies.length} success)`);
    }
    console.log('');

    const historyStats = calcStats(historyLatencies);
    results.operations.GetCreditHistory = {
        type: 'read (range query)',
        attempted: Math.min(20, createdDIDs.length),
        successful: historyLatencies.length,
        success_rate: ((historyLatencies.length / Math.min(20, createdDIDs.length)) * 100).toFixed(1) + '%',
        latency_ms: historyStats,
        sequential_qps: historyStats ? (1000 / historyStats.mean).toFixed(2) : null
    };

    if (historyStats) {
        console.log(`  Success: ${historyLatencies.length}/${Math.min(20, createdDIDs.length)}`);
        console.log(`  Latency: mean=${historyStats.mean}ms, p95=${historyStats.p95}ms`);
    }

    // Get final blockchain info
    console.log('\nGetting final blockchain info...');
    const bcFinal = getBlockchainInfo();
    if (bcFinal.success) {
        const match = bcFinal.output.match(/"height":(\d+)/);
        results.final_height = match ? parseInt(match[1]) : null;
        if (results.initial_height && results.final_height) {
            results.blocks_added = results.final_height - results.initial_height;
            const totalTxns = writeLatencies.length + eventLatencies.length;
            results.txns_per_block = totalTxns > 0 && results.blocks_added > 0 ?
                (totalTxns / results.blocks_added).toFixed(2) : 'N/A';
        }
        console.log(`  Final height: ${results.final_height}, blocks added: ${results.blocks_added || 0}`);
        console.log(`  Transactions per block: ${results.txns_per_block}`);
    }

    // Summary
    console.log('\n========================================');
    console.log('SUMMARY');
    console.log('========================================');
    console.log('');
    console.log('CAVEATS:');
    console.log('  - Single orderer (Raft requires 3 for CFT)');
    console.log('  - Sequential execution (not concurrent TPS)');
    console.log('  - Latency includes Docker exec overhead (~500ms)');
    console.log('');

    results.summary = {
        AnchorCommitment: {
            mean_ms: writeStats?.mean,
            p95_ms: writeStats?.p95,
            sequential_tps: results.operations.AnchorCommitment?.sequential_tps
        },
        RecordLoanEvent: {
            mean_ms: eventStats?.mean,
            p95_ms: eventStats?.p95,
            sequential_tps: results.operations.RecordLoanEvent?.sequential_tps
        },
        GetCommitment: {
            mean_ms: readStats?.mean,
            p95_ms: readStats?.p95,
            sequential_qps: results.operations.GetCommitment?.sequential_qps
        },
        GetCreditHistory: {
            mean_ms: historyStats?.mean,
            p95_ms: historyStats?.p95,
            sequential_qps: results.operations.GetCreditHistory?.sequential_qps
        },
        measurement_type: 'sequential (not concurrent)'
    };

    console.log('| Operation          | Type  | Mean (ms) | P95 (ms) | Seq. Rate |');
    console.log('|--------------------|-------|-----------|----------|-----------|');
    console.log(`| AnchorCommitment   | Write | ${writeStats?.mean || 'N/A'} | ${writeStats?.p95 || 'N/A'} | ${results.operations.AnchorCommitment?.sequential_tps || 'N/A'} TPS |`);
    console.log(`| RecordLoanEvent    | Write | ${eventStats?.mean || 'N/A'} | ${eventStats?.p95 || 'N/A'} | ${results.operations.RecordLoanEvent?.sequential_tps || 'N/A'} TPS |`);
    console.log(`| GetCommitment      | Read  | ${readStats?.mean || 'N/A'} | ${readStats?.p95 || 'N/A'} | ${results.operations.GetCommitment?.sequential_qps || 'N/A'} QPS |`);
    console.log(`| GetCreditHistory   | Read  | ${historyStats?.mean || 'N/A'} | ${historyStats?.p95 || 'N/A'} | ${results.operations.GetCreditHistory?.sequential_qps || 'N/A'} QPS |`);

    // Save
    const outPath = path.join(CONFIG.resultsDir, 'fabric_benchmark.json');
    fs.writeFileSync(outPath, JSON.stringify(results, null, 2));
    console.log(`\nResults saved to: ${outPath}`);
}

main().catch(console.error);
