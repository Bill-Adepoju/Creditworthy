/**
 * T44: Concurrent Throughput Benchmarks
 *
 * Uses Fabric Gateway SDK to measure actual throughput (not inverse latency).
 * Key differences from T31c sequential benchmark:
 * 1. Direct gRPC connection (no docker exec overhead)
 * 2. Concurrent transaction submission (engages batching)
 * 3. Reports txns_per_block to verify batching
 * 4. Separates latency and throughput as distinct metrics
 */

const { connect, signers } = require('@hyperledger/fabric-gateway');
const grpc = require('@grpc/grpc-js');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Configuration
const CONFIG = {
    channelName: 'creditchannel',
    chaincodeName: 'credit',
    mspId: 'CommercialBankAMSP',

    // Crypto paths (relative to this file)
    cryptoPath: path.resolve(__dirname, '../config/crypto-config'),

    // Peer connection
    peerEndpoint: 'localhost:7051',
    peerHostAlias: 'peer0.commercialbanka.credit.ng',

    // Benchmark parameters
    concurrencyLevels: [1, 5, 10, 20, 50],  // Number of parallel workers
    txnsPerLevel: 100,  // Transactions per concurrency level
    warmupTxns: 10,  // Warmup transactions (discarded)

    resultsDir: path.resolve(__dirname, '../../results')
};

// Helper to generate random DID and hash
function generateDID() {
    return `did:credit:c${Date.now()}${crypto.randomBytes(4).toString('hex')}`;
}

function generateHash() {
    return '0x' + crypto.randomBytes(32).toString('hex');
}

// Get blockchain height via docker exec (for txns_per_block calculation)
function getBlockHeight() {
    try {
        const cmd = `docker exec cli peer channel getinfo -c ${CONFIG.channelName} 2>&1`;
        const output = execSync(cmd, { encoding: 'utf8', timeout: 30000 });
        const match = output.match(/"height":(\d+)/);
        return match ? parseInt(match[1]) : null;
    } catch (e) {
        return null;
    }
}

// Create gRPC client connection
async function createGrpcConnection() {
    const tlsCertPath = path.join(
        CONFIG.cryptoPath,
        'peerOrganizations/commercialbanka.credit.ng/peers/peer0.commercialbanka.credit.ng/tls/ca.crt'
    );
    const tlsCert = fs.readFileSync(tlsCertPath);

    const credentials = grpc.credentials.createSsl(tlsCert);

    return new grpc.Client(
        CONFIG.peerEndpoint,
        credentials,
        {
            'grpc.ssl_target_name_override': CONFIG.peerHostAlias,
            'grpc.keepalive_time_ms': 120000,
            'grpc.http2.min_time_between_pings_ms': 120000,
            'grpc.keepalive_timeout_ms': 20000,
            'grpc.http2.max_pings_without_data': 0,
            'grpc.keepalive_permit_without_calls': 1,
        }
    );
}

// Create identity from crypto materials
function createIdentity() {
    const certPath = path.join(
        CONFIG.cryptoPath,
        'peerOrganizations/commercialbanka.credit.ng/users/User1@commercialbanka.credit.ng/msp/signcerts/User1@commercialbanka.credit.ng-cert.pem'
    );
    const credentials = fs.readFileSync(certPath);
    return { mspId: CONFIG.mspId, credentials };
}

// Create signer from private key
function createSigner() {
    const keyPath = path.join(
        CONFIG.cryptoPath,
        'peerOrganizations/commercialbanka.credit.ng/users/User1@commercialbanka.credit.ng/msp/keystore/priv_sk'
    );
    const privateKeyPem = fs.readFileSync(keyPath);
    const privateKey = crypto.createPrivateKey(privateKeyPem);
    return signers.newPrivateKeySigner(privateKey);
}

// Submit transaction and measure latency
async function submitTransaction(contract, functionName, args) {
    const start = process.hrtime.bigint();
    try {
        await contract.submitTransaction(functionName, ...args);
        const latencyMs = Number(process.hrtime.bigint() - start) / 1_000_000;
        return { success: true, latencyMs };
    } catch (error) {
        const latencyMs = Number(process.hrtime.bigint() - start) / 1_000_000;
        return { success: false, latencyMs, error: error.message };
    }
}

// Run concurrent workload
async function runConcurrentWorkload(contract, concurrency, numTxns) {
    const results = [];
    const pending = [];
    let completed = 0;

    const startTime = process.hrtime.bigint();

    for (let i = 0; i < numTxns; i++) {
        const did = generateDID();
        const hash = generateHash();

        const promise = submitTransaction(contract, 'AnchorCommitment', [hash, did, 'model_v1'])
            .then(result => {
                results.push(result);
                completed++;
                process.stdout.write(`\r    Progress: ${completed}/${numTxns}`);
                return result;
            });

        pending.push(promise);

        // Maintain concurrency level
        if (pending.length >= concurrency) {
            await Promise.race(pending);
            // Remove completed promises
            for (let j = pending.length - 1; j >= 0; j--) {
                if (pending[j].completed) {
                    pending.splice(j, 1);
                }
            }
        }
    }

    // Wait for all remaining
    await Promise.all(pending);

    const totalTimeMs = Number(process.hrtime.bigint() - startTime) / 1_000_000;
    console.log('');

    return { results, totalTimeMs };
}

// Calculate statistics
function calcStats(values) {
    if (!values.length) return null;
    const sorted = [...values].sort((a, b) => a - b);
    const sum = sorted.reduce((a, b) => a + b, 0);
    return {
        n: values.length,
        min: Math.round(sorted[0]),
        max: Math.round(sorted[sorted.length - 1]),
        mean: Math.round(sum / values.length),
        p50: Math.round(sorted[Math.floor(values.length * 0.5)]),
        p95: Math.round(sorted[Math.floor(values.length * 0.95)]),
        p99: values.length >= 10 ? Math.round(sorted[Math.floor(values.length * 0.99)]) : null
    };
}

async function main() {
    console.log('='.repeat(60));
    console.log('T44: Concurrent Throughput Benchmarks');
    console.log('='.repeat(60));
    console.log('');
    console.log('Using Fabric Gateway SDK (no docker exec overhead)');
    console.log('');

    const results = {
        timestamp: new Date().toISOString(),
        task: 'T44',
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
            batch_timeout: '2s (default)',
            channel: CONFIG.channelName,
            chaincode: CONFIG.chaincodeName
        },
        caveats: [
            'SINGLE ORDERER - not fault-tolerant',
            'Raft minimum for CFT is 3 orderers',
            'Single-orderer throughput is not consortium throughput'
        ],
        benchmark_config: {
            concurrency_levels: CONFIG.concurrencyLevels,
            txns_per_level: CONFIG.txnsPerLevel,
            warmup_txns: CONFIG.warmupTxns
        },
        benchmarks: []
    };

    try {
        // Connect to Fabric
        console.log('Connecting to Fabric Gateway...');
        const client = await createGrpcConnection();
        const identity = createIdentity();
        const signer = createSigner();

        const gateway = connect({
            client,
            identity,
            signer,
            evaluateOptions: () => ({ deadline: Date.now() + 30000 }),
            endorseOptions: () => ({ deadline: Date.now() + 30000 }),
            submitOptions: () => ({ deadline: Date.now() + 30000 }),
            commitStatusOptions: () => ({ deadline: Date.now() + 60000 }),
        });

        const network = gateway.getNetwork(CONFIG.channelName);
        const contract = network.getContract(CONFIG.chaincodeName);

        console.log('Connected successfully!\n');

        // Warmup
        console.log(`Running warmup (${CONFIG.warmupTxns} transactions)...`);
        for (let i = 0; i < CONFIG.warmupTxns; i++) {
            const did = generateDID();
            const hash = generateHash();
            await contract.submitTransaction('AnchorCommitment', hash, did, 'model_v1');
            process.stdout.write(`\r  Warmup: ${i + 1}/${CONFIG.warmupTxns}`);
        }
        console.log('\n');

        // Test each concurrency level
        for (const concurrency of CONFIG.concurrencyLevels) {
            console.log(`Testing concurrency=${concurrency}...`);

            const heightBefore = getBlockHeight();
            const { results: txnResults, totalTimeMs } = await runConcurrentWorkload(
                contract, concurrency, CONFIG.txnsPerLevel
            );
            const heightAfter = getBlockHeight();

            const successfulLatencies = txnResults
                .filter(r => r.success)
                .map(r => r.latencyMs);

            const successCount = successfulLatencies.length;
            const blocksAdded = (heightBefore && heightAfter) ? heightAfter - heightBefore : null;
            const txnsPerBlock = (blocksAdded && blocksAdded > 0) ?
                (successCount / blocksAdded).toFixed(2) : 'N/A';

            // Throughput = successful txns / total time
            const throughputTPS = (successCount / (totalTimeMs / 1000)).toFixed(2);

            const latencyStats = calcStats(successfulLatencies);

            const levelResult = {
                concurrency,
                transactions: {
                    attempted: CONFIG.txnsPerLevel,
                    successful: successCount,
                    success_rate: ((successCount / CONFIG.txnsPerLevel) * 100).toFixed(1) + '%'
                },
                throughput: {
                    total_time_ms: Math.round(totalTimeMs),
                    tps: parseFloat(throughputTPS),
                    note: 'TPS = successful_txns / total_time'
                },
                latency_ms: latencyStats,
                batching: {
                    blocks_added: blocksAdded,
                    txns_per_block: txnsPerBlock,
                    batching_engaged: blocksAdded !== null && blocksAdded < successCount
                }
            };

            results.benchmarks.push(levelResult);

            console.log(`  Success: ${successCount}/${CONFIG.txnsPerLevel}`);
            console.log(`  Throughput: ${throughputTPS} TPS`);
            console.log(`  Latency: mean=${latencyStats?.mean}ms, p95=${latencyStats?.p95}ms`);
            console.log(`  Blocks added: ${blocksAdded}, txns/block: ${txnsPerBlock}`);
            console.log('');

            // Brief pause between levels
            await new Promise(r => setTimeout(r, 2000));
        }

        // Summary
        console.log('='.repeat(60));
        console.log('SUMMARY');
        console.log('='.repeat(60));
        console.log('');
        console.log('| Concurrency | TPS | Mean Latency | P95 Latency | Txns/Block |');
        console.log('|-------------|-----|--------------|-------------|------------|');

        for (const b of results.benchmarks) {
            console.log(`| ${b.concurrency.toString().padStart(11)} | ${b.throughput.tps.toString().padStart(3)} | ${(b.latency_ms?.mean || 'N/A').toString().padStart(12)}ms | ${(b.latency_ms?.p95 || 'N/A').toString().padStart(11)}ms | ${b.batching.txns_per_block.toString().padStart(10)} |`);
        }

        console.log('');
        console.log('CAVEATS:');
        for (const caveat of results.caveats) {
            console.log(`  - ${caveat}`);
        }

        // Peak throughput
        const peakTPS = Math.max(...results.benchmarks.map(b => b.throughput.tps));
        const peakLevel = results.benchmarks.find(b => b.throughput.tps === peakTPS);
        results.peak_throughput = {
            tps: peakTPS,
            at_concurrency: peakLevel?.concurrency,
            txns_per_block: peakLevel?.batching.txns_per_block
        };

        console.log('');
        console.log(`Peak throughput: ${peakTPS} TPS at concurrency=${peakLevel?.concurrency}`);

        gateway.close();
        client.close();

    } catch (error) {
        console.error('Benchmark failed:', error);
        results.error = error.message;
    }

    // Save results
    const outPath = path.join(CONFIG.resultsDir, 'fabric_throughput.json');
    fs.writeFileSync(outPath, JSON.stringify(results, null, 2));
    console.log(`\nResults saved to: ${outPath}`);
}

main().catch(console.error);
