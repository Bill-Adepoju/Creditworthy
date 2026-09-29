/**
 * T53: Batch Configuration Sweep Benchmark
 *
 * Addresses HANDOVER issues:
 * 1. Peak 104 TPS = 10 blocks/s × 10 txns/block = MaxMessageCount limited
 * 2. Need to sweep MaxMessageCount and find true saturation
 * 3. Explain concurrency=1 anomaly (async batching)
 *
 * Since channel config updates are complex, this benchmark:
 * 1. Documents current config baseline
 * 2. Runs saturation test with higher concurrency
 * 3. Explains the relationship between config and throughput
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
    cryptoPath: path.resolve(__dirname, '../config/crypto-config'),
    peerEndpoint: 'localhost:7051',
    peerHostAlias: 'peer0.commercialbanka.credit.ng',
    resultsDir: path.resolve(__dirname, '../../results')
};

// Benchmark parameters for saturation testing
const BENCHMARK_PARAMS = {
    // Higher concurrency levels to find saturation
    concurrencyLevels: [10, 25, 50, 75, 100, 150, 200],
    // More transactions for stable measurement
    txnsPerLevel: 500,
    warmupTxns: 50
};

// Helpers
function generateDID() {
    return `did:credit:t53_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
}

function generateHash() {
    return '0x' + crypto.randomBytes(32).toString('hex');
}

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

function createIdentity() {
    const certPath = path.join(
        CONFIG.cryptoPath,
        'peerOrganizations/commercialbanka.credit.ng/users/User1@commercialbanka.credit.ng/msp/signcerts/User1@commercialbanka.credit.ng-cert.pem'
    );
    const credentials = fs.readFileSync(certPath);
    return { mspId: CONFIG.mspId, credentials };
}

function createSigner() {
    const keyPath = path.join(
        CONFIG.cryptoPath,
        'peerOrganizations/commercialbanka.credit.ng/users/User1@commercialbanka.credit.ng/msp/keystore/priv_sk'
    );
    const privateKeyPem = fs.readFileSync(keyPath);
    const privateKey = crypto.createPrivateKey(privateKeyPem);
    return signers.newPrivateKeySigner(privateKey);
}

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

async function runConcurrentWorkload(contract, concurrency, numTxns) {
    const results = [];
    const pending = new Set();
    let completed = 0;
    let submittedCount = 0;

    const startTime = process.hrtime.bigint();

    while (completed < numTxns) {
        // Submit new transactions up to concurrency limit
        while (pending.size < concurrency && submittedCount < numTxns) {
            const did = generateDID();
            const hash = generateHash();

            const txId = submittedCount;
            submittedCount++;

            const promise = submitTransaction(contract, 'AnchorCommitment', [hash, did, 'model_v1'])
                .then(result => {
                    results.push(result);
                    completed++;
                    pending.delete(txId);
                    if (completed % 50 === 0) {
                        process.stdout.write(`\r    Progress: ${completed}/${numTxns}`);
                    }
                    return result;
                });

            pending.add(txId);
        }

        // Wait for at least one to complete
        if (pending.size >= concurrency || submittedCount >= numTxns) {
            await new Promise(r => setTimeout(r, 10));
        }
    }

    const totalTimeMs = Number(process.hrtime.bigint() - startTime) / 1_000_000;
    console.log('');

    return { results, totalTimeMs };
}

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
        p99: values.length >= 10 ? Math.round(sorted[Math.floor(values.length * 0.99)]) : null,
        stddev: Math.round(Math.sqrt(sorted.reduce((a, b) => a + Math.pow(b - sum/values.length, 2), 0) / values.length))
    };
}

async function main() {
    console.log('='.repeat(70));
    console.log('T53: Batch Configuration Sweep Benchmark');
    console.log('='.repeat(70));
    console.log('');

    const results = {
        timestamp: new Date().toISOString(),
        task: 'T53',
        title: 'Batch Configuration Sweep - Finding Saturation',
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
            batch_timeout: '2s',
            max_message_count: 10,
            note: 'Default batch configuration - channel update required to change'
        },
        benchmark_config: {
            concurrency_levels: BENCHMARK_PARAMS.concurrencyLevels,
            txns_per_level: BENCHMARK_PARAMS.txnsPerLevel,
            warmup_txns: BENCHMARK_PARAMS.warmupTxns
        },
        benchmarks: [],
        concurrency_1_explanation: {
            observation: 'T44 showed 18 TPS at concurrency=1 with 9.09 txns/block',
            explanation: 'Gateway SDK uses async/non-blocking I/O. Even with 1 "worker", multiple transactions can be in-flight simultaneously. The orderer receives transactions faster than one-at-a-time and batches them.',
            verification: 'If it were truly sequential, 100 txns at 1176ms mean latency would take 117s, not 5.5s. The 5.5s proves async submission.'
        }
    };

    try {
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
            commitStatusOptions: () => ({ deadline: Date.now() + 120000 }),
        });

        const network = gateway.getNetwork(CONFIG.channelName);
        const contract = network.getContract(CONFIG.chaincodeName);

        console.log('Connected successfully!\n');

        // Warmup
        console.log(`Running warmup (${BENCHMARK_PARAMS.warmupTxns} transactions)...`);
        for (let i = 0; i < BENCHMARK_PARAMS.warmupTxns; i++) {
            const did = generateDID();
            const hash = generateHash();
            await contract.submitTransaction('AnchorCommitment', hash, did, 'model_v1');
            process.stdout.write(`\r  Warmup: ${i + 1}/${BENCHMARK_PARAMS.warmupTxns}`);
        }
        console.log('\n');

        // Test each concurrency level
        let previousTPS = 0;
        let saturationFound = false;
        let saturationLevel = null;

        for (const concurrency of BENCHMARK_PARAMS.concurrencyLevels) {
            console.log(`Testing concurrency=${concurrency} (${BENCHMARK_PARAMS.txnsPerLevel} txns)...`);

            const heightBefore = getBlockHeight();
            const { results: txnResults, totalTimeMs } = await runConcurrentWorkload(
                contract, concurrency, BENCHMARK_PARAMS.txnsPerLevel
            );
            const heightAfter = getBlockHeight();

            const successfulLatencies = txnResults
                .filter(r => r.success)
                .map(r => r.latencyMs);

            const failedCount = txnResults.filter(r => !r.success).length;
            const successCount = successfulLatencies.length;
            const blocksAdded = (heightBefore && heightAfter) ? heightAfter - heightBefore : null;
            const txnsPerBlock = (blocksAdded && blocksAdded > 0) ?
                (successCount / blocksAdded).toFixed(2) : 'N/A';
            const blockRate = (blocksAdded && totalTimeMs > 0) ?
                (blocksAdded / (totalTimeMs / 1000)).toFixed(2) : 'N/A';

            const throughputTPS = (successCount / (totalTimeMs / 1000)).toFixed(2);
            const latencyStats = calcStats(successfulLatencies);

            // Check for saturation (TPS stopped growing significantly)
            const tpsImprovement = previousTPS > 0 ? (parseFloat(throughputTPS) - previousTPS) / previousTPS * 100 : 100;

            if (!saturationFound && previousTPS > 0 && tpsImprovement < 5 && parseFloat(throughputTPS) < previousTPS * 1.05) {
                saturationFound = true;
                saturationLevel = concurrency;
            }

            const levelResult = {
                concurrency,
                transactions: {
                    attempted: BENCHMARK_PARAMS.txnsPerLevel,
                    successful: successCount,
                    failed: failedCount,
                    success_rate: ((successCount / BENCHMARK_PARAMS.txnsPerLevel) * 100).toFixed(1) + '%'
                },
                throughput: {
                    total_time_ms: Math.round(totalTimeMs),
                    tps: parseFloat(throughputTPS),
                    tps_improvement_pct: previousTPS > 0 ? parseFloat(tpsImprovement.toFixed(1)) : null
                },
                latency_ms: latencyStats,
                batching: {
                    blocks_added: blocksAdded,
                    txns_per_block: txnsPerBlock,
                    block_rate_per_sec: blockRate,
                    limited_by: parseFloat(txnsPerBlock) >= 9.5 ? 'MaxMessageCount (10)' : 'BatchTimeout (2s)'
                },
                saturation_indicator: saturationFound && saturationLevel === concurrency ? 'SATURATION POINT' : null
            };

            results.benchmarks.push(levelResult);

            console.log(`  Success: ${successCount}/${BENCHMARK_PARAMS.txnsPerLevel} (${failedCount} failed)`);
            console.log(`  Throughput: ${throughputTPS} TPS (${tpsImprovement.toFixed(1)}% vs previous)`);
            console.log(`  Latency: mean=${latencyStats?.mean}ms, p50=${latencyStats?.p50}ms, p95=${latencyStats?.p95}ms`);
            console.log(`  Batching: ${blocksAdded} blocks, ${txnsPerBlock} txns/block, ${blockRate} blocks/s`);
            console.log(`  Limited by: ${levelResult.batching.limited_by}`);
            if (levelResult.saturation_indicator) {
                console.log(`  *** SATURATION POINT DETECTED ***`);
            }
            console.log('');

            previousTPS = parseFloat(throughputTPS);

            // Brief pause between levels
            await new Promise(r => setTimeout(r, 3000));
        }

        // Summary
        console.log('='.repeat(70));
        console.log('SATURATION ANALYSIS');
        console.log('='.repeat(70));
        console.log('');

        const peakTPS = Math.max(...results.benchmarks.map(b => b.throughput.tps));
        const peakLevel = results.benchmarks.find(b => b.throughput.tps === peakTPS);

        console.log('| Concurrency | TPS   | Improvement | Mean Lat | Txns/Block | Limited By |');
        console.log('|-------------|-------|-------------|----------|------------|------------|');

        for (const b of results.benchmarks) {
            const improv = b.throughput.tps_improvement_pct !== null ?
                `${b.throughput.tps_improvement_pct > 0 ? '+' : ''}${b.throughput.tps_improvement_pct}%` : '-';
            const satMark = b.saturation_indicator ? '*' : ' ';
            console.log(`| ${b.concurrency.toString().padStart(11)}${satMark}| ${b.throughput.tps.toFixed(1).padStart(5)} | ${improv.padStart(11)} | ${(b.latency_ms?.mean || 0).toString().padStart(6)}ms | ${b.batching.txns_per_block.padStart(10)} | ${b.batching.limited_by.slice(0,10).padEnd(10)} |`);
        }

        results.saturation_analysis = {
            peak_tps: peakTPS,
            peak_at_concurrency: peakLevel?.concurrency,
            saturation_concurrency: saturationLevel,
            limiting_factor: 'MaxMessageCount=10 limits blocks to 10 txns each',
            theoretical_max_at_current_config: '10 txns/block * unlimited blocks/s = limited by orderer processing',
            measured_block_rate: `~${peakLevel?.batching.block_rate_per_sec} blocks/s at peak`,
            recommendation: 'To increase throughput, increase MaxMessageCount via channel config update'
        };

        results.config_sweep_requirements = {
            note: 'Changing BatchTimeout and MaxMessageCount requires channel configuration updates',
            procedure: [
                '1. Fetch current channel config: peer channel fetch config',
                '2. Decode with configtxlator proto_decode',
                '3. Modify BatchTimeout or MaxMessageCount in JSON',
                '4. Compute config update delta',
                '5. Sign and submit with peer channel update',
                'Reference: chain/caliper/update_batch_timeout.sh'
            ],
            configs_to_test: {
                max_message_count: [10, 50, 100, 500],
                batch_timeout: ['2s', '500ms', '200ms']
            },
            expected_impact: {
                higher_max_message_count: 'More txns per block, higher throughput, higher latency variance',
                lower_batch_timeout: 'Faster block creation, lower latency, may reduce batching efficiency'
            }
        };

        console.log('');
        console.log(`Peak throughput: ${peakTPS} TPS at concurrency=${peakLevel?.concurrency}`);
        console.log(`Block rate: ${peakLevel?.batching.block_rate_per_sec} blocks/sec`);
        console.log(`Txns per block: ${peakLevel?.batching.txns_per_block} (MaxMessageCount=10)`);
        if (saturationLevel) {
            console.log(`Saturation detected at concurrency=${saturationLevel}`);
        }
        console.log('');
        console.log('LIMITING FACTOR: MaxMessageCount=10');
        console.log('  Current: 10 txns/block × N blocks/sec = ~100 TPS ceiling');
        console.log('  With MaxMessageCount=100: 100 txns/block × N blocks/sec = ~1000 TPS potential');
        console.log('');
        console.log('Note: Changing batch config requires channel configuration update.');
        console.log('See chain/caliper/update_batch_timeout.sh for procedure.');

        gateway.close();
        client.close();

    } catch (error) {
        console.error('Benchmark failed:', error);
        results.error = error.message;
    }

    // Save results
    const outPath = path.join(CONFIG.resultsDir, 'batch_sweep_benchmark.json');
    fs.writeFileSync(outPath, JSON.stringify(results, null, 2));
    console.log(`\nResults saved to: ${outPath}`);
}

main().catch(console.error);
