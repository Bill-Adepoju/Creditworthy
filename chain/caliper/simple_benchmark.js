/**
 * T31c: Simple Fabric Benchmark
 *
 * Measures latency for individual operations via sequential execution.
 * Note: This measures per-operation latency, not concurrent throughput.
 *
 * For true TPS, concurrent load testing with Fabric SDK would be needed.
 */

const { execSync, exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const CONFIG = {
    channelName: 'creditchannel',
    chaincodeName: 'credit',
    orderer: 'orderer.orderer.credit.ng:7050',
    numWriteTests: 30,
    numReadTests: 50,
    resultsDir: path.join(__dirname, '../../results')
};

const ORDERER_CA = '/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.credit.ng/orderers/orderer.orderer.credit.ng/msp/tlscacerts/tlsca.orderer.credit.ng-cert.pem';

const PEERS = [
    { name: 'commercialbanka', address: 'peer0.commercialbanka.credit.ng:7051', tlsCert: '/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/commercialbanka.credit.ng/peers/peer0.commercialbanka.credit.ng/tls/ca.crt' },
    { name: 'microfinanceb', address: 'peer0.microfinanceb.credit.ng:8051', tlsCert: '/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/microfinanceb.credit.ng/peers/peer0.microfinanceb.credit.ng/tls/ca.crt' },
    { name: 'fintechc', address: 'peer0.fintechc.credit.ng:9051', tlsCert: '/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/fintechc.credit.ng/peers/peer0.fintechc.credit.ng/tls/ca.crt' }
];

function generateDID() {
    return `did:credit:bench${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

function generateCommitmentHash() {
    const hex = '0123456789abcdef';
    let hash = '0x';
    for (let i = 0; i < 64; i++) {
        hash += hex[Math.floor(Math.random() * 16)];
    }
    return hash;
}

function runCommand(cmd) {
    const start = process.hrtime.bigint();
    try {
        const result = execSync(cmd, { encoding: 'utf8', timeout: 60000, stdio: ['pipe', 'pipe', 'pipe'] });
        const end = process.hrtime.bigint();
        return { success: true, latencyMs: Number(end - start) / 1_000_000, output: result };
    } catch (error) {
        const end = process.hrtime.bigint();
        return { success: false, latencyMs: Number(end - start) / 1_000_000, error: error.stderr || error.message };
    }
}

function anchorCommitment(did, commitmentHash) {
    const peerArgs = PEERS.map(p => `--peerAddresses ${p.address} --tlsRootCertFiles ${p.tlsCert}`).join(' ');
    const cmd = `docker exec cli bash -c 'peer chaincode invoke -o ${CONFIG.orderer} --channelID ${CONFIG.channelName} --name ${CONFIG.chaincodeName} --tls --cafile ${ORDERER_CA} ${peerArgs} -c "{\\"function\\":\\"AnchorCommitment\\",\\"Args\\":[\\"${commitmentHash}\\",\\"${did}\\",\\"model_v1\\"]}" --waitForEvent 2>&1'`;
    return runCommand(cmd);
}

function getCommitment(did) {
    const cmd = `docker exec cli bash -c 'peer chaincode query --channelID ${CONFIG.channelName} --name ${CONFIG.chaincodeName} -c "{\\"function\\":\\"GetCommitment\\",\\"Args\\":[\\"${did}\\"]}" 2>&1'`;
    return runCommand(cmd);
}

function recordLoanEvent(did, eventType, proofHash, threshold) {
    const peerArgs = PEERS.map(p => `--peerAddresses ${p.address} --tlsRootCertFiles ${p.tlsCert}`).join(' ');
    const cmd = `docker exec cli bash -c 'peer chaincode invoke -o ${CONFIG.orderer} --channelID ${CONFIG.channelName} --name ${CONFIG.chaincodeName} --tls --cafile ${ORDERER_CA} ${peerArgs} -c "{\\"function\\":\\"RecordLoanEvent\\",\\"Args\\":[\\"${did}\\",\\"${eventType}\\",\\"${proofHash}\\",\\"${threshold}\\"]}" --waitForEvent 2>&1'`;
    return runCommand(cmd);
}

function getBlockchainInfo() {
    const cmd = `docker exec cli bash -c 'peer channel getinfo -c ${CONFIG.channelName} 2>&1'`;
    return runCommand(cmd);
}

function calculateStats(values) {
    if (values.length === 0) return null;
    const sorted = [...values].sort((a, b) => a - b);
    const sum = sorted.reduce((a, b) => a + b, 0);
    return {
        n: sorted.length,
        min: Math.round(sorted[0]),
        max: Math.round(sorted[sorted.length - 1]),
        mean: Math.round(sum / sorted.length),
        median: Math.round(sorted[Math.floor(sorted.length / 2)]),
        p95: Math.round(sorted[Math.floor(sorted.length * 0.95)]),
        p99: sorted.length > 10 ? Math.round(sorted[Math.floor(sorted.length * 0.99)]) : null
    };
}

async function main() {
    console.log('========================================');
    console.log('T31c: Fabric Benchmark');
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
            ordering: 'Raft (CFT)',
            orderer_count: 1,
            endorsers: 3,
            endorsement_policy: 'MAJORITY (3 of 4)',
            channel: 'creditchannel'
        },
        caveat: 'SINGLE ORDERER - not fault-tolerant. Raft minimum is 3 orderers. Sequential testing - not concurrent TPS.',
        operations: {}
    };

    // Get blockchain info
    console.log('Getting blockchain info...');
    const bcInfo = getBlockchainInfo();
    if (bcInfo.success) {
        const heightMatch = bcInfo.output.match(/height:(\d+)/);
        results.initial_height = heightMatch ? parseInt(heightMatch[1]) : null;
        console.log(`  Initial block height: ${results.initial_height}\n`);
    }

    // Test 1: AnchorCommitment (Write)
    console.log(`Testing AnchorCommitment (n=${CONFIG.numWriteTests})...`);
    const writeLatencies = [];
    const createdDIDs = [];

    for (let i = 0; i < CONFIG.numWriteTests; i++) {
        const did = generateDID();
        const hash = generateCommitmentHash();
        const result = anchorCommitment(did, hash);

        if (result.success) {
            writeLatencies.push(result.latencyMs);
            createdDIDs.push(did);
        }
        process.stdout.write(`\r  Progress: ${i + 1}/${CONFIG.numWriteTests} (${writeLatencies.length} success)`);
    }
    console.log('');

    results.operations.AnchorCommitment = {
        type: 'write',
        attempted: CONFIG.numWriteTests,
        successful: writeLatencies.length,
        success_rate: ((writeLatencies.length / CONFIG.numWriteTests) * 100).toFixed(1) + '%',
        latency_ms: calculateStats(writeLatencies),
        sequential_tps: writeLatencies.length > 0 ? (1000 / calculateStats(writeLatencies).mean).toFixed(2) : null
    };

    console.log(`  Success: ${writeLatencies.length}/${CONFIG.numWriteTests}`);
    if (writeLatencies.length > 0) {
        const stats = calculateStats(writeLatencies);
        console.log(`  Latency: mean=${stats.mean}ms, p95=${stats.p95}ms, min=${stats.min}ms, max=${stats.max}ms`);
        console.log(`  Sequential TPS: ${results.operations.AnchorCommitment.sequential_tps}`);
    }

    // Test 2: RecordLoanEvent (Write)
    console.log(`\nTesting RecordLoanEvent (n=${CONFIG.numWriteTests})...`);
    const eventLatencies = [];

    for (let i = 0; i < CONFIG.numWriteTests && i < createdDIDs.length; i++) {
        const did = createdDIDs[i];
        const proofHash = generateCommitmentHash();
        const result = recordLoanEvent(did, 'verification', proofHash, '650');

        if (result.success) {
            eventLatencies.push(result.latencyMs);
        }
        process.stdout.write(`\r  Progress: ${i + 1}/${Math.min(CONFIG.numWriteTests, createdDIDs.length)}`);
    }
    console.log('');

    results.operations.RecordLoanEvent = {
        type: 'write',
        attempted: Math.min(CONFIG.numWriteTests, createdDIDs.length),
        successful: eventLatencies.length,
        success_rate: ((eventLatencies.length / Math.min(CONFIG.numWriteTests, createdDIDs.length)) * 100).toFixed(1) + '%',
        latency_ms: calculateStats(eventLatencies),
        sequential_tps: eventLatencies.length > 0 ? (1000 / calculateStats(eventLatencies).mean).toFixed(2) : null
    };

    if (eventLatencies.length > 0) {
        const stats = calculateStats(eventLatencies);
        console.log(`  Latency: mean=${stats.mean}ms, p95=${stats.p95}ms`);
    }

    // Test 3: GetCommitment (Read)
    console.log(`\nTesting GetCommitment (n=${CONFIG.numReadTests})...`);
    const readLatencies = [];

    for (let i = 0; i < CONFIG.numReadTests; i++) {
        const did = createdDIDs[i % createdDIDs.length];
        const result = getCommitment(did);

        if (result.success) {
            readLatencies.push(result.latencyMs);
        }
        process.stdout.write(`\r  Progress: ${i + 1}/${CONFIG.numReadTests}`);
    }
    console.log('');

    results.operations.GetCommitment = {
        type: 'read',
        attempted: CONFIG.numReadTests,
        successful: readLatencies.length,
        success_rate: ((readLatencies.length / CONFIG.numReadTests) * 100).toFixed(1) + '%',
        latency_ms: calculateStats(readLatencies),
        sequential_qps: readLatencies.length > 0 ? (1000 / calculateStats(readLatencies).mean).toFixed(2) : null
    };

    if (readLatencies.length > 0) {
        const stats = calculateStats(readLatencies);
        console.log(`  Latency: mean=${stats.mean}ms, p95=${stats.p95}ms, min=${stats.min}ms, max=${stats.max}ms`);
        console.log(`  Sequential QPS: ${results.operations.GetCommitment.sequential_qps}`);
    }

    // Get final blockchain info
    console.log('\nGetting final blockchain info...');
    const bcInfoFinal = getBlockchainInfo();
    if (bcInfoFinal.success) {
        const heightMatch = bcInfoFinal.output.match(/height:(\d+)/);
        results.final_height = heightMatch ? parseInt(heightMatch[1]) : null;
        console.log(`  Final block height: ${results.final_height}`);

        if (results.initial_height && results.final_height) {
            results.blocks_added = results.final_height - results.initial_height;
            const totalTxns = writeLatencies.length + eventLatencies.length;
            results.txns_per_block = totalTxns > 0 ? (totalTxns / results.blocks_added).toFixed(2) : null;
            console.log(`  Blocks added: ${results.blocks_added}`);
            console.log(`  Transactions per block: ${results.txns_per_block}`);
        }
    }

    // Summary
    console.log('\n========================================');
    console.log('SUMMARY (Sequential Performance)');
    console.log('========================================');
    console.log('');
    console.log('NOTE: These are SEQUENTIAL latencies, not concurrent TPS.');
    console.log('Single orderer deployment - NOT fault-tolerant.');
    console.log('');

    const writeStats = results.operations.AnchorCommitment.latency_ms;
    const readStats = results.operations.GetCommitment.latency_ms;

    results.summary = {
        write_latency_mean_ms: writeStats?.mean,
        write_latency_p95_ms: writeStats?.p95,
        read_latency_mean_ms: readStats?.mean,
        read_latency_p95_ms: readStats?.p95,
        sequential_write_tps: results.operations.AnchorCommitment.sequential_tps,
        sequential_read_qps: results.operations.GetCommitment.sequential_qps,
        measurement_type: 'sequential (not concurrent)'
    };

    console.log('| Operation | Mean (ms) | P95 (ms) | Seq. Rate |');
    console.log('|-----------|-----------|----------|-----------|');
    console.log(`| AnchorCommitment | ${writeStats?.mean || 'N/A'} | ${writeStats?.p95 || 'N/A'} | ${results.operations.AnchorCommitment.sequential_tps || 'N/A'} TPS |`);
    console.log(`| RecordLoanEvent | ${calculateStats(eventLatencies)?.mean || 'N/A'} | ${calculateStats(eventLatencies)?.p95 || 'N/A'} | ${results.operations.RecordLoanEvent.sequential_tps || 'N/A'} TPS |`);
    console.log(`| GetCommitment | ${readStats?.mean || 'N/A'} | ${readStats?.p95 || 'N/A'} | ${results.operations.GetCommitment.sequential_qps || 'N/A'} QPS |`);

    // Save results
    const outputPath = path.join(CONFIG.resultsDir, 'fabric_benchmark.json');
    fs.writeFileSync(outputPath, JSON.stringify(results, null, 2));
    console.log(`\nResults saved to: ${outputPath}`);

    return results;
}

main().catch(console.error);
