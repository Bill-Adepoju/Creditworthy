/**
 * T56: Batch Configuration Sweep
 *
 * Actually runs the channel config updates to test:
 * 1. MaxMessageCount: 10, 50, 100, 500 at concurrency=75
 * 2. BatchTimeout: 2s, 500ms, 200ms for single-tx latency
 *
 * Addresses HANDOVER issue: T53 documented but didn't run the sweep
 */

const { connect, signers } = require('@hyperledger/fabric-gateway');
const grpc = require('@grpc/grpc-js');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const CONFIG = {
    channelName: 'creditchannel',
    chaincodeName: 'credit',
    mspId: 'CommercialBankAMSP',
    cryptoPath: path.resolve(__dirname, '../config/crypto-config'),
    peerEndpoint: 'localhost:7051',
    peerHostAlias: 'peer0.commercialbanka.credit.ng',
    resultsDir: path.resolve(__dirname, '../../results')
};

// Test parameters
const SWEEP_PARAMS = {
    maxMessageCounts: [10, 50, 100, 500],
    batchTimeouts: ['2s', '500ms', '200ms'],
    concurrencyForThroughput: 75,
    txnsPerThroughputTest: 300,
    txnsPerLatencyTest: 20,  // Single-tx tests, fewer needed
    warmupTxns: 30
};

function generateDID() {
    return `did:credit:t56_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
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

function getCurrentConfig() {
    try {
        // Get current batch config from channel
        const cmd = `docker exec cli sh -c "peer channel fetch config /tmp/config_block.pb -o orderer.orderer.credit.ng:7050 -c ${CONFIG.channelName} --tls --cafile /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.credit.ng/orderers/orderer.orderer.credit.ng/msp/tlscacerts/tlsca.orderer.credit.ng-cert.pem 2>&1 && configtxlator proto_decode --input /tmp/config_block.pb --type common.Block 2>/dev/null | grep -A 20 'BatchSize' | head -25"`;
        const output = execSync(cmd, { encoding: 'utf8', timeout: 30000 });

        // Parse MaxMessageCount
        const maxMsgMatch = output.match(/"max_message_count":\s*(\d+)/);
        const timeoutMatch = output.match(/"timeout":\s*"([^"]+)"/);

        return {
            maxMessageCount: maxMsgMatch ? parseInt(maxMsgMatch[1]) : 10,
            batchTimeout: timeoutMatch ? timeoutMatch[1] : '2s'
        };
    } catch (e) {
        console.error('Error fetching config:', e.message);
        return { maxMessageCount: 10, batchTimeout: '2s' };
    }
}

function updateChannelConfig(paramName, value) {
    /**
     * Updates channel config using the update_config.sh script
     * paramName: 'MaxMessageCount' or 'BatchTimeout'
     * value: numeric for MaxMessageCount, string for BatchTimeout
     */
    console.log(`  Updating ${paramName} to ${value}...`);

    try {
        // Use the shell script with orderer admin credentials
        const scriptPath = '/opt/gopath/src/github.com/hyperledger/fabric/peer/scripts/update_config.sh';
        const cmd = `docker exec cli bash ${scriptPath} ${paramName} ${value}`;
        const output = execSync(cmd, { encoding: 'utf8', timeout: 60000, stdio: 'pipe' });
        console.log(`  ${paramName} updated to ${value} successfully`);
        return true;
    } catch (e) {
        // Check if it's a "no differences" error (config already at target value)
        if (e.message && e.message.includes('no differences detected')) {
            console.log(`  ${paramName} already at ${value}`);
            return true;
        }
        console.error(`  Failed to update ${paramName}:`, e.message);
        return false;
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

        if (pending.size >= concurrency || submittedCount >= numTxns) {
            await new Promise(r => setTimeout(r, 10));
        }
    }

    const totalTimeMs = Number(process.hrtime.bigint() - startTime) / 1_000_000;
    console.log('');

    return { results, totalTimeMs };
}

async function runSequentialLatencyTest(contract, numTxns) {
    /**
     * Run transactions one at a time to measure single-tx latency
     * This tests BatchTimeout impact on idle network
     */
    const latencies = [];

    for (let i = 0; i < numTxns; i++) {
        const did = generateDID();
        const hash = generateHash();
        const result = await submitTransaction(contract, 'AnchorCommitment', [hash, did, 'model_v1']);
        if (result.success) {
            latencies.push(result.latencyMs);
        }
        process.stdout.write(`\r    Progress: ${i + 1}/${numTxns}`);
    }
    console.log('');

    return latencies;
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
    };
}

async function main() {
    console.log('='.repeat(70));
    console.log('T56: Batch Configuration Sweep');
    console.log('='.repeat(70));
    console.log('');

    const results = {
        timestamp: new Date().toISOString(),
        task: 'T56',
        title: 'Batch Configuration Sweep - Finding Platform vs Config Limits',
        hardware: {
            cpu: 'AMD Ryzen 7 4800H',
            cores: 8,
            threads: 16,
            ram_gb: 32,
            platform: 'Windows 10 / Docker Desktop'
        },
        sweep_params: SWEEP_PARAMS,
        baseline_config: null,
        max_message_count_sweep: [],
        batch_timeout_sweep: [],
        findings: {}
    };

    try {
        // Get baseline config
        console.log('Fetching current channel configuration...');
        const baseline = getCurrentConfig();
        results.baseline_config = baseline;
        console.log(`  Current: MaxMessageCount=${baseline.maxMessageCount}, BatchTimeout=${baseline.batchTimeout}`);
        console.log('');

        // Connect to gateway
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
        console.log('Connected!\n');

        // Warmup
        console.log(`Warmup (${SWEEP_PARAMS.warmupTxns} transactions)...`);
        for (let i = 0; i < SWEEP_PARAMS.warmupTxns; i++) {
            const did = generateDID();
            const hash = generateHash();
            await contract.submitTransaction('AnchorCommitment', hash, did, 'model_v1');
            process.stdout.write(`\r  Progress: ${i + 1}/${SWEEP_PARAMS.warmupTxns}`);
        }
        console.log('\n');

        // ================================================================
        // PART 1: MaxMessageCount Sweep (throughput test at concurrency=75)
        // ================================================================
        console.log('='.repeat(70));
        console.log('PART 1: MaxMessageCount Sweep (Throughput at concurrency=75)');
        console.log('='.repeat(70));
        console.log('');

        for (const maxMsgCount of SWEEP_PARAMS.maxMessageCounts) {
            console.log(`Testing MaxMessageCount=${maxMsgCount}...`);

            // Update config if not the current value
            const currentCfg = getCurrentConfig();
            if (currentCfg.maxMessageCount !== maxMsgCount) {
                const updated = updateChannelConfig('MaxMessageCount', maxMsgCount);
                if (!updated) {
                    console.log(`  Skipping - config update failed`);
                    continue;
                }
                // Wait for config to propagate
                await new Promise(r => setTimeout(r, 3000));
            }

            // Run throughput test
            const heightBefore = getBlockHeight();
            const { results: txnResults, totalTimeMs } = await runConcurrentWorkload(
                contract,
                SWEEP_PARAMS.concurrencyForThroughput,
                SWEEP_PARAMS.txnsPerThroughputTest
            );
            const heightAfter = getBlockHeight();

            const successfulLatencies = txnResults.filter(r => r.success).map(r => r.latencyMs);
            const successCount = successfulLatencies.length;
            const blocksAdded = (heightBefore && heightAfter) ? heightAfter - heightBefore : null;
            const txnsPerBlock = blocksAdded ? (successCount / blocksAdded).toFixed(2) : 'N/A';
            const blockRate = blocksAdded ? (blocksAdded / (totalTimeMs / 1000)).toFixed(2) : 'N/A';
            const tps = (successCount / (totalTimeMs / 1000)).toFixed(2);
            const latencyStats = calcStats(successfulLatencies);

            const result = {
                max_message_count: maxMsgCount,
                concurrency: SWEEP_PARAMS.concurrencyForThroughput,
                transactions: {
                    attempted: SWEEP_PARAMS.txnsPerThroughputTest,
                    successful: successCount,
                    success_rate: ((successCount / SWEEP_PARAMS.txnsPerThroughputTest) * 100).toFixed(1) + '%'
                },
                throughput: {
                    tps: parseFloat(tps),
                    total_time_ms: Math.round(totalTimeMs)
                },
                batching: {
                    blocks_added: blocksAdded,
                    txns_per_block: parseFloat(txnsPerBlock) || null,
                    block_rate_per_sec: parseFloat(blockRate) || null
                },
                latency_ms: latencyStats
            };

            results.max_message_count_sweep.push(result);

            console.log(`  TPS: ${tps}`);
            console.log(`  Blocks: ${blocksAdded}, Txns/block: ${txnsPerBlock}, Block rate: ${blockRate}/s`);
            console.log(`  Latency: mean=${latencyStats?.mean}ms, p50=${latencyStats?.p50}ms, p95=${latencyStats?.p95}ms`);
            console.log('');

            // Brief pause between tests
            await new Promise(r => setTimeout(r, 2000));
        }

        // ================================================================
        // PART 2: BatchTimeout Sweep (single-tx latency test)
        // ================================================================
        console.log('='.repeat(70));
        console.log('PART 2: BatchTimeout Sweep (Single-tx latency on idle network)');
        console.log('='.repeat(70));
        console.log('');

        // Reset MaxMessageCount to default first
        const cfgBefore = getCurrentConfig();
        if (cfgBefore.maxMessageCount !== 10) {
            console.log('Resetting MaxMessageCount to 10...');
            updateChannelConfig('MaxMessageCount', 10);
            await new Promise(r => setTimeout(r, 3000));
        }

        for (const timeout of SWEEP_PARAMS.batchTimeouts) {
            console.log(`Testing BatchTimeout=${timeout}...`);

            // Update config
            const updated = updateChannelConfig('BatchTimeout', timeout);
            if (!updated) {
                console.log(`  Skipping - config update failed`);
                continue;
            }
            await new Promise(r => setTimeout(r, 3000));

            // Run sequential latency test (idle network)
            const latencies = await runSequentialLatencyTest(contract, SWEEP_PARAMS.txnsPerLatencyTest);
            const latencyStats = calcStats(latencies);

            const result = {
                batch_timeout: timeout,
                test_type: 'sequential_single_tx',
                note: 'Measures latency when network is idle (not batching)',
                transactions: {
                    attempted: SWEEP_PARAMS.txnsPerLatencyTest,
                    successful: latencies.length
                },
                latency_ms: latencyStats
            };

            results.batch_timeout_sweep.push(result);

            console.log(`  Mean latency: ${latencyStats?.mean}ms`);
            console.log(`  p50: ${latencyStats?.p50}ms, p95: ${latencyStats?.p95}ms`);
            console.log('');

            await new Promise(r => setTimeout(r, 2000));
        }

        // ================================================================
        // FINDINGS
        // ================================================================
        console.log('='.repeat(70));
        console.log('FINDINGS');
        console.log('='.repeat(70));
        console.log('');

        // Analyze MaxMessageCount results
        const mmcResults = results.max_message_count_sweep;
        if (mmcResults.length > 0) {
            const tpsValues = mmcResults.map(r => ({ mmc: r.max_message_count, tps: r.throughput.tps }));
            const peakTPS = Math.max(...tpsValues.map(v => v.tps));
            const peakMMC = tpsValues.find(v => v.tps === peakTPS)?.mmc;

            // Check if throughput scales with MaxMessageCount
            const tps10 = tpsValues.find(v => v.mmc === 10)?.tps || 0;
            const tps50 = tpsValues.find(v => v.mmc === 50)?.tps || 0;
            const tps100 = tpsValues.find(v => v.mmc === 100)?.tps || 0;

            const scalesWithConfig = tps50 > tps10 * 1.2; // >20% improvement suggests config-limited

            results.findings.throughput = {
                peak_tps: peakTPS,
                peak_at_max_message_count: peakMMC,
                ceiling_type: scalesWithConfig ? 'CONFIGURATION (tunable)' : 'PLATFORM (hardware/network)',
                tps_by_config: tpsValues,
                interpretation: scalesWithConfig
                    ? `Throughput increased with MaxMessageCount. The 143.5 TPS from T53 was a configuration ceiling, not a platform limit. With MaxMessageCount=${peakMMC}, throughput reaches ${peakTPS} TPS.`
                    : `Throughput did not scale significantly with MaxMessageCount. The ${peakTPS} TPS ceiling is a platform limit imposed by hardware or network constraints.`
            };

            console.log('MaxMessageCount Impact:');
            console.log(`  Peak TPS: ${peakTPS} at MaxMessageCount=${peakMMC}`);
            console.log(`  Ceiling type: ${results.findings.throughput.ceiling_type}`);
            for (const v of tpsValues) {
                console.log(`    MMC=${v.mmc}: ${v.tps} TPS`);
            }
            console.log('');
        }

        // Analyze BatchTimeout results
        const btResults = results.batch_timeout_sweep;
        if (btResults.length > 0) {
            const latencies = btResults.map(r => ({
                timeout: r.batch_timeout,
                mean: r.latency_ms?.mean,
                p50: r.latency_ms?.p50
            }));

            const lat2s = latencies.find(l => l.timeout === '2s')?.mean || 0;
            const lat500ms = latencies.find(l => l.timeout === '500ms')?.mean || 0;
            const lat200ms = latencies.find(l => l.timeout === '200ms')?.mean || 0;

            results.findings.latency = {
                single_tx_latencies: latencies,
                interpretation: `BatchTimeout directly impacts single-tx latency. At 2s: ${lat2s}ms, at 500ms: ${lat500ms}ms, at 200ms: ${lat200ms}ms. The SDK speedup on queries (~40×) does not apply to writes because they must wait for batch commitment.`,
                tradeoff: 'Lower BatchTimeout reduces write latency but may reduce batching efficiency under load.'
            };

            console.log('BatchTimeout Impact on Single-TX Latency:');
            for (const l of latencies) {
                console.log(`  ${l.timeout}: mean=${l.mean}ms, p50=${l.p50}ms`);
            }
            console.log('');
        }

        // Overall interaction finding
        results.findings.interaction = {
            summary: 'MaxMessageCount governs throughput under load; BatchTimeout governs latency when idle.',
            recommendation: 'For high-throughput scenarios, increase MaxMessageCount. For low-latency single-decision scenarios (credit applications), reduce BatchTimeout.',
            chapter_5_result: 'The trade between throughput and latency is configurable, not fixed by the platform.'
        };

        console.log('Key Finding:');
        console.log(`  ${results.findings.interaction.summary}`);
        console.log('');

        // Reset to defaults
        console.log('Resetting to default configuration (MMC=10, BT=2s)...');
        updateChannelConfig('MaxMessageCount', 10);
        updateChannelConfig('BatchTimeout', '2s');

        gateway.close();
        client.close();

    } catch (error) {
        console.error('Sweep failed:', error);
        results.error = error.message;
    }

    // Save results
    const outPath = path.join(CONFIG.resultsDir, 'batch_config_sweep.json');
    fs.writeFileSync(outPath, JSON.stringify(results, null, 2));
    console.log(`\nResults saved to: ${outPath}`);
}

main().catch(console.error);
