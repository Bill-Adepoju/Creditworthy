/**
 * T31c: Fabric Benchmark Script
 *
 * Measures:
 * - TPS at send rates 50→1000
 * - Latency min/mean/max/p95
 * - Ledger growth estimation
 *
 * Note: Single orderer deployment - not representative of fault-tolerant production.
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// Configuration
const CONFIG = {
    channelName: 'creditchannel',
    chaincodeName: 'credit',
    orderer: 'orderer.orderer.credit.ng:7050',
    sendRates: [50, 100, 200, 500, 1000],  // transactions to attempt
    endorserCounts: [3],  // currently have 3 endorsing peers
    warmupTxns: 10,
    resultsDir: path.join(__dirname, '../../results')
};

// Peer configurations for endorsement
const PEERS = {
    commercialbanka: {
        address: 'peer0.commercialbanka.credit.ng:7051',
        mspId: 'CommercialBankAMSP',
        tlsCert: '/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/commercialbanka.credit.ng/peers/peer0.commercialbanka.credit.ng/tls/ca.crt'
    },
    microfinanceb: {
        address: 'peer0.microfinanceb.credit.ng:8051',
        mspId: 'MicrofinanceBMSP',
        tlsCert: '/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/microfinanceb.credit.ng/peers/peer0.microfinanceb.credit.ng/tls/ca.crt'
    },
    fintechc: {
        address: 'peer0.fintechc.credit.ng:9051',
        mspId: 'FintechCMSP',
        tlsCert: '/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/fintechc.credit.ng/peers/peer0.fintechc.credit.ng/tls/ca.crt'
    }
};

const ORDERER_CA = '/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.credit.ng/orderers/orderer.orderer.credit.ng/msp/tlscacerts/tlsca.orderer.credit.ng-cert.pem';

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

function buildInvokeCommand(did, commitmentHash) {
    const peerArgs = Object.values(PEERS).map(p =>
        `--peerAddresses ${p.address} --tlsRootCertFiles ${p.tlsCert}`
    ).join(' ');

    return `docker exec cli bash -c 'peer chaincode invoke -o ${CONFIG.orderer} --channelID ${CONFIG.channelName} --name ${CONFIG.chaincodeName} --tls --cafile ${ORDERER_CA} ${peerArgs} -c "{\\"function\\":\\"AnchorCommitment\\",\\"Args\\":[\\"${commitmentHash}\\",\\"${did}\\",\\"model_bench_v1\\"]}" --waitForEvent 2>&1'`;
}

function buildQueryCommand(did) {
    return `docker exec cli bash -c 'peer chaincode query --channelID ${CONFIG.channelName} --name ${CONFIG.chaincodeName} -c "{\\"function\\":\\"GetCommitment\\",\\"Args\\":[\\"${did}\\"]}" 2>&1'`;
}

async function measureTransaction(did, commitmentHash) {
    const cmd = buildInvokeCommand(did, commitmentHash);
    const start = process.hrtime.bigint();

    try {
        execSync(cmd, { encoding: 'utf8', timeout: 30000 });
        const end = process.hrtime.bigint();
        const latencyMs = Number(end - start) / 1_000_000;
        return { success: true, latencyMs };
    } catch (error) {
        const end = process.hrtime.bigint();
        const latencyMs = Number(end - start) / 1_000_000;
        return { success: false, latencyMs, error: error.message };
    }
}

async function measureQuery(did) {
    const cmd = buildQueryCommand(did);
    const start = process.hrtime.bigint();

    try {
        const result = execSync(cmd, { encoding: 'utf8', timeout: 10000 });
        const end = process.hrtime.bigint();
        const latencyMs = Number(end - start) / 1_000_000;
        return { success: true, latencyMs, result };
    } catch (error) {
        const end = process.hrtime.bigint();
        const latencyMs = Number(end - start) / 1_000_000;
        return { success: false, latencyMs, error: error.message };
    }
}

function calculateStats(latencies) {
    if (latencies.length === 0) return null;

    const sorted = [...latencies].sort((a, b) => a - b);
    const sum = sorted.reduce((a, b) => a + b, 0);

    return {
        min: sorted[0],
        max: sorted[sorted.length - 1],
        mean: sum / sorted.length,
        p50: sorted[Math.floor(sorted.length * 0.50)],
        p95: sorted[Math.floor(sorted.length * 0.95)],
        p99: sorted[Math.floor(sorted.length * 0.99)]
    };
}

async function runBenchmark(numTransactions) {
    console.log(`\n--- Running benchmark: ${numTransactions} transactions ---`);

    const results = [];
    const successLatencies = [];
    const failedLatencies = [];

    const startTime = Date.now();

    for (let i = 0; i < numTransactions; i++) {
        const did = generateDID();
        const commitmentHash = generateCommitmentHash();

        const result = await measureTransaction(did, commitmentHash);
        results.push(result);

        if (result.success) {
            successLatencies.push(result.latencyMs);
        } else {
            failedLatencies.push(result.latencyMs);
        }

        // Progress indicator
        if ((i + 1) % 10 === 0 || i === numTransactions - 1) {
            process.stdout.write(`\r  Progress: ${i + 1}/${numTransactions} (${results.filter(r => r.success).length} success)`);
        }
    }

    const endTime = Date.now();
    const totalTimeSeconds = (endTime - startTime) / 1000;

    console.log('');

    const successCount = results.filter(r => r.success).length;
    const failCount = results.filter(r => !r.success).length;
    const tps = successCount / totalTimeSeconds;

    return {
        attempted: numTransactions,
        successful: successCount,
        failed: failCount,
        successRate: (successCount / numTransactions * 100).toFixed(2) + '%',
        totalTimeSeconds: totalTimeSeconds.toFixed(2),
        tps: tps.toFixed(2),
        latencyStats: calculateStats(successLatencies),
        failedLatencyStats: calculateStats(failedLatencies)
    };
}

async function runQueryBenchmark(numQueries) {
    console.log(`\n--- Running query benchmark: ${numQueries} queries ---`);

    // First create some commitments to query
    const dids = [];
    console.log('  Creating test commitments...');
    for (let i = 0; i < 5; i++) {
        const did = generateDID();
        const commitmentHash = generateCommitmentHash();
        await measureTransaction(did, commitmentHash);
        dids.push(did);
    }

    // Now query them
    const latencies = [];
    const startTime = Date.now();

    for (let i = 0; i < numQueries; i++) {
        const did = dids[i % dids.length];
        const result = await measureQuery(did);
        if (result.success) {
            latencies.push(result.latencyMs);
        }

        if ((i + 1) % 10 === 0 || i === numQueries - 1) {
            process.stdout.write(`\r  Progress: ${i + 1}/${numQueries}`);
        }
    }

    const endTime = Date.now();
    const totalTimeSeconds = (endTime - startTime) / 1000;

    console.log('');

    return {
        queries: numQueries,
        successful: latencies.length,
        totalTimeSeconds: totalTimeSeconds.toFixed(2),
        qps: (latencies.length / totalTimeSeconds).toFixed(2),
        latencyStats: calculateStats(latencies)
    };
}

async function getLedgerInfo() {
    try {
        const cmd = `docker exec cli bash -c 'peer channel getinfo -c ${CONFIG.channelName} 2>&1'`;
        const result = execSync(cmd, { encoding: 'utf8' });

        // Parse blockchain height
        const heightMatch = result.match(/Blockchain info:.*height:(\d+)/);
        const height = heightMatch ? parseInt(heightMatch[1]) : null;

        return { height, raw: result.trim() };
    } catch (error) {
        return { error: error.message };
    }
}

async function main() {
    console.log('========================================');
    console.log('T31c: Fabric Benchmark');
    console.log('========================================');
    console.log('');
    console.log('Hardware:');
    console.log('  CPU: AMD Ryzen 7 4800H (8 cores / 16 threads)');
    console.log('  RAM: 32 GB');
    console.log('  Platform: Windows 10 / Docker Desktop');
    console.log('');
    console.log('Network Configuration:');
    console.log('  Fabric Version: 2.5');
    console.log('  Ordering: Raft (single orderer - NOT fault-tolerant)');
    console.log('  Endorsers: 3 (CommercialBankA, MicrofinanceB, FintechC)');
    console.log('  Endorsement Policy: MAJORITY (3 of 4)');
    console.log('  Channel: creditchannel');
    console.log('');
    console.log('CAVEAT: Single orderer deployment. Numbers are NOT');
    console.log('representative of fault-tolerant production configuration.');
    console.log('Minimum fault-tolerant Raft deployment requires 3 orderers.');
    console.log('');

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
            ordering: 'Raft',
            orderer_count: 1,
            endorsers: 3,
            endorsement_policy: 'MAJORITY (3 of 4)',
            channel: 'creditchannel'
        },
        caveat: 'Single orderer deployment - NOT fault-tolerant. Minimum fault-tolerant Raft requires 3 orderers.',
        benchmarks: {}
    };

    // Get initial ledger height
    console.log('Getting initial ledger state...');
    const initialLedger = await getLedgerInfo();
    results.ledger_initial = initialLedger;
    console.log(`  Initial height: ${initialLedger.height || 'unknown'}`);

    // Warmup
    console.log('\nWarmup phase...');
    for (let i = 0; i < CONFIG.warmupTxns; i++) {
        const did = generateDID();
        const commitmentHash = generateCommitmentHash();
        await measureTransaction(did, commitmentHash);
    }
    console.log('  Warmup complete.');

    // Run transaction benchmarks at different scales
    const txnBenchmarks = [];
    for (const numTxns of CONFIG.sendRates) {
        const benchResult = await runBenchmark(numTxns);
        txnBenchmarks.push({
            transactions: numTxns,
            ...benchResult
        });

        console.log(`  TPS: ${benchResult.tps}, Success: ${benchResult.successRate}`);
        if (benchResult.latencyStats) {
            console.log(`  Latency - Mean: ${benchResult.latencyStats.mean.toFixed(0)}ms, P95: ${benchResult.latencyStats.p95.toFixed(0)}ms`);
        }
    }
    results.benchmarks.transactions = txnBenchmarks;

    // Run query benchmark
    const queryBench = await runQueryBenchmark(100);
    results.benchmarks.queries = queryBench;
    console.log(`  QPS: ${queryBench.qps}`);
    if (queryBench.latencyStats) {
        console.log(`  Latency - Mean: ${queryBench.latencyStats.mean.toFixed(0)}ms, P95: ${queryBench.latencyStats.p95.toFixed(0)}ms`);
    }

    // Get final ledger height
    console.log('\nGetting final ledger state...');
    const finalLedger = await getLedgerInfo();
    results.ledger_final = finalLedger;
    console.log(`  Final height: ${finalLedger.height || 'unknown'}`);

    if (initialLedger.height && finalLedger.height) {
        const blocksAdded = finalLedger.height - initialLedger.height;
        const totalTxns = CONFIG.warmupTxns + CONFIG.sendRates.reduce((a, b) => a + b, 0);
        results.ledger_growth = {
            blocks_added: blocksAdded,
            transactions_submitted: totalTxns,
            txns_per_block_estimate: (totalTxns / blocksAdded).toFixed(2)
        };
        console.log(`  Blocks added: ${blocksAdded}`);
        console.log(`  Est. transactions per block: ${results.ledger_growth.txns_per_block_estimate}`);
    }

    // Summary
    console.log('\n========================================');
    console.log('SUMMARY');
    console.log('========================================');

    const bestTxnBench = txnBenchmarks.reduce((best, curr) =>
        parseFloat(curr.tps) > parseFloat(best.tps) ? curr : best
    );

    console.log(`\nPeak Write TPS: ${bestTxnBench.tps} (at ${bestTxnBench.transactions} txns)`);
    console.log(`Write Latency (Mean): ${bestTxnBench.latencyStats?.mean.toFixed(0) || 'N/A'} ms`);
    console.log(`Write Latency (P95): ${bestTxnBench.latencyStats?.p95.toFixed(0) || 'N/A'} ms`);
    console.log(`Read QPS: ${queryBench.qps}`);
    console.log(`Read Latency (Mean): ${queryBench.latencyStats?.mean.toFixed(0) || 'N/A'} ms`);

    results.summary = {
        peak_write_tps: parseFloat(bestTxnBench.tps),
        peak_write_at_transactions: bestTxnBench.transactions,
        write_latency_mean_ms: bestTxnBench.latencyStats?.mean,
        write_latency_p95_ms: bestTxnBench.latencyStats?.p95,
        read_qps: parseFloat(queryBench.qps),
        read_latency_mean_ms: queryBench.latencyStats?.mean,
        read_latency_p95_ms: queryBench.latencyStats?.p95
    };

    // Save results
    const outputPath = path.join(CONFIG.resultsDir, 'fabric_benchmark.json');
    fs.writeFileSync(outputPath, JSON.stringify(results, null, 2));
    console.log(`\nResults saved to: ${outputPath}`);

    return results;
}

main().catch(console.error);
