pragma circom 2.1.6;

include "../node_modules/circomlib/circuits/poseidon.circom";
include "../node_modules/circomlib/circuits/comparators.circom";
include "../node_modules/circomlib/circuits/bitify.circom";

/*
 * CreditThresholdProofBanded
 * --------------------------
 * Extends CreditThresholdProof with a band-membership constraint.
 *
 * PRIVACY FIX: The unbanded circuit leaks under repeated queries. Because
 * ge.out === 1 is a hard constraint, an ineligible borrower cannot produce
 * a proof at all — and that refusal is perfectly informative. A lender
 * issuing proof requests at chosen thresholds performs a binary search,
 * recovering the exact score in ~10 queries (~9.97 bits, complete disclosure).
 *
 * MITIGATION: Constrain the threshold to a fixed public band set. The
 * constraint is a root-form polynomial, satisfiable only when threshold
 * equals a permitted value:
 *
 *     (T - b0)(T - b1)(T - b2)(T - b3) = 0
 *
 * R1CS is quadratic, so we factor into pairwise products:
 *     lo <== (T - b0) * (T - b1)
 *     hi <== (T - b2) * (T - b3)
 *     lo * hi === 0
 *
 * This adds ~3 non-linear constraints. Proof size and verification time
 * are unchanged (Groth16 proofs are constant-size).
 *
 * With 4 bands, an adversary querying all bands learns at most 2 bits
 * (which band the score falls into), not 10.
 *
 * PRIVATE inputs : score, salt
 * PUBLIC  inputs : commitment, threshold
 */
template CreditThresholdProofBanded(nBits, b0, b1, b2, b3) {
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

    // --- 4. Band-membership constraint ---
    // (threshold - b0)(threshold - b1)(threshold - b2)(threshold - b3) = 0
    // Factored for R1CS quadratic constraint:
    signal lo;
    signal hi;

    lo <== (threshold - b0) * (threshold - b1);
    hi <== (threshold - b2) * (threshold - b3);
    lo * hi === 0;
}

// Default bands: {400, 550, 700, 850}
// These can be changed by recompiling with different parameters
component main {public [commitment, threshold]} = CreditThresholdProofBanded(16, 400, 550, 700, 850);
