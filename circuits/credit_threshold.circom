pragma circom 2.1.6;

include "../node_modules/circomlib/circuits/poseidon.circom";
include "../node_modules/circomlib/circuits/comparators.circom";
include "../node_modules/circomlib/circuits/bitify.circom";

/*
 * CreditThresholdProof
 * --------------------
 * Proves: "I know a credit score S and salt r such that
 *          Poseidon(S, r) == C  (the commitment anchored on the ledger)
 *          AND S >= T           (the lender's eligibility threshold)"
 * ...without revealing S or r.
 *
 * PRIVATE inputs : score, salt
 * PUBLIC  inputs : commitment, threshold
 *
 * Design notes:
 *  - The Poseidon binding is what makes this non-trivial. Without it a
 *    borrower could prove "I know SOME number >= T", which is worthless.
 *    Binding to the on-chain commitment proves it is THE score the
 *    ML layer computed and the consortium ledger anchored.
 *  - ge.out === 1 is a hard constraint, not an output flag. An ineligible
 *    borrower cannot produce a proof at all. The existence of a valid
 *    proof IS the attestation.
 *  - Num2Bits range checks prevent field-wraparound: without them a
 *    malicious prover could supply score = p - k (a huge field element
 *    that behaves like a negative number) and defeat the comparator.
 */
template CreditThresholdProof(nBits) {
    signal input score;        // private
    signal input salt;         // private
    signal input commitment;   // public
    signal input threshold;    // public

    signal output eligible;

    // --- 1. Bind the private score to the public on-chain commitment ---
    component hasher = Poseidon(2);
    hasher.inputs[0] <== score;
    hasher.inputs[1] <== salt;
    commitment === hasher.out;

    // --- 2. Range-check both operands into nBits ---
    component scoreBits = Num2Bits(nBits);
    scoreBits.in <== score;

    component thrBits = Num2Bits(nBits);
    thrBits.in <== threshold;

    // --- 3. Threshold comparison ---
    component ge = GreaterEqThan(nBits);
    ge.in[0] <== score;
    ge.in[1] <== threshold;

    ge.out === 1;
    eligible <== ge.out;
}

component main {public [commitment, threshold]} = CreditThresholdProof(16);
