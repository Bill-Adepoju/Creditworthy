/**
 * T31c: Fabric Benchmark Script v2
 * Fixed quoting for Windows/Git Bash environment
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const CONFIG = {
    channelName: 'creditchannel',
    chaincodeName: 'credit',
    numWriteTests: 20,
    numReadTests: 30,
    resultsDir: path.join(__dirname, '../../results')
};

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
    // Use double quotes for Windows compatibility
    const cmd = `docker exec cli bash -c "${innerCmd}"`;
    const start = process.hrtime.bigint();
    try {
        const result = execSync(cmd, { encoding: 'utf8', timeout: 60000, stdio: ['pipe', 'pipe', 'pipe'] });
        const latencyMs = Number(process.hrtime.bigint() - start) / 1_000_000;
        return { success: true, latencyMs, output: result };
    } catch (error) {
        const latencyMs = Number(process.hrtime.bigint() - start) / 1_000_000;
        return { success: false, latencyMs, error: (error.stdout || '') + (error.stderr || '') };
    }
}

function anchorCommitment(did, hash) {
    const cmd = `peer chaincode invoke -o orderer.orderer.credit.ng:7050 --channelID ${CONFIG.channelName} --name ${CONFIG.chaincodeName} --tls --cafile /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.credit.ng/orderers/orderer.orderer.credit.ng/msp/tlscacerts/tlsca.orderer.credit.ng-cert.pem --peerAddresses peer0.commercialbanka.credit.ng:7051 --tlsRootCertFiles /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/commercialbanka.credit.ng/peers/peer0.commercialbanka.credit.ng/tls/ca.crt --peerAddresses peer0.microfinanceb.credit.ng:8051 --tlsRootCertFiles /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/microfinanceb.credit.ng/peers/peer0.microfinanceb.credit.ng/tls/ca.crt --peerAddresses peer0.fintechc.credit.ng:9051 --tlsRootCertFiles /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/fintechc.credit.ng/peers/peer0.fintechc.credit.ng/tls/ca.crt -c '{\\\"function\\\":\\\"AnchorCommitment\\\",\\\"Args\\\":[\\\"${hash}\\\",\\\"${did}\\\",\\\"model_v1\\\"]}' --waitForEvent 2>&1`;
    return runDockerCmd(cmd);
}

function getCommitment(did) {
    const cmd = `peer chaincode query --channelID ${CONFIG.channelName} --name ${CONFIG.chaincodeName} -c '{\\\"function\\\":\\\"GetCommitment\\\",\\\"Args\\\":[\\\"${did}\\\"]}' 2>&1`;
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
        p95: Math.round(sorted[Math.floor(vals.length * 0.95)])
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
        caveat: 'SINGLE ORDERER - not fault-tolerant. Raft minimum is 3 orderers. Sequential testing.',
        operations: {}
    };

    // Get initial blockchain info
    console.log('Getting blockchain info...');
    const bcInfo = getBlockchainInfo();
    if (bcInfo.success) {
        const match = bcInfo.output.match(/height:(\d+)/);
        results.initial_height = match ? parseInt(match[1]) : null;
        console.log(`  Initial height: ${results.initial_height}\n`);
    }

    // Test AnchorCommitment (Write)
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
        type: 'write',
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

    // Test GetCommitment (Read)
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
        type: 'read',
        attempted: CONFIG.numReadTests,
        successful: readLatencies.length,
        success_rate: ((readLatencies.length / CONFIG.numReadTests) * 100).toFixed(1) + '%',
        latency_ms: readStats,
        sequential_qps: readStats ? (1000 / readStats.mean).toFixed(2) : null
    };

    if (readStats) {
        console.log(`  Success: ${readLatencies.length}/${CONFIG.numReadTests}`);
        console.log(`  Latency: mean=${readStats.mean}ms, p95=${readStats.p95}ms`);
        console.log(`  Sequential QPS: ${results.operations.GetCommitment.sequential_qps}`);
    }

    // Get final blockchain info
    console.log('\nGetting final blockchain info...');
    const bcFinal = getBlockchainInfo();
    if (bcFinal.success) {
        const match = bcFinal.output.match(/height:(\d+)/);
        results.final_height = match ? parseInt(match[1]) : null;
        if (results.initial_height && results.final_height) {
            results.blocks_added = results.final_height - results.initial_height;
            results.txns_per_block = (writeLatencies.length / results.blocks_added).toFixed(2);
        }
        console.log(`  Final height: ${results.final_height}, blocks added: ${results.blocks_added || 0}`);
    }

    // Summary
    console.log('\n========================================');
    console.log('SUMMARY');
    console.log('========================================');
    console.log('CAVEAT: Single orderer, sequential execution');
    console.log('');

    results.summary = {
        write_latency_mean_ms: writeStats?.mean,
        write_latency_p95_ms: writeStats?.p95,
        read_latency_mean_ms: readStats?.mean,
        read_latency_p95_ms: readStats?.p95,
        sequential_write_tps: results.operations.AnchorCommitment?.sequential_tps,
        sequential_read_qps: results.operations.GetCommitment?.sequential_qps
    };

    console.log('| Operation | Mean (ms) | P95 (ms) | Seq. Rate |');
    console.log('|-----------|-----------|----------|-----------|');
    console.log(`| AnchorCommitment | ${writeStats?.mean || 'N/A'} | ${writeStats?.p95 || 'N/A'} | ${results.operations.AnchorCommitment?.sequential_tps || 'N/A'} TPS |`);
    console.log(`| GetCommitment | ${readStats?.mean || 'N/A'} | ${readStats?.p95 || 'N/A'} | ${results.operations.GetCommitment?.sequential_qps || 'N/A'} QPS |`);

    // Save
    const outPath = path.join(CONFIG.resultsDir, 'fabric_benchmark.json');
    fs.writeFileSync(outPath, JSON.stringify(results, null, 2));
    console.log(`\nResults saved to: ${outPath}`);
}

main().catch(console.error);
