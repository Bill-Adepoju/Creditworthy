// T31b: Credit Score Commitment Chaincode
// Stores ONLY commitments - never raw scores, features, PII, or model weights
//
// Functions:
// - AnchorCommitment: Store a Poseidon commitment for a borrower
// - GetCommitment: Retrieve commitment by DID
// - RecordLoanEvent: Record loan events (verification, approval, etc.)
// - GetCreditHistory: Get all events for a DID
// - RevokeCommitment: Mark a commitment as revoked

package main

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// CreditContract provides functions for managing credit score commitments
type CreditContract struct {
	contractapi.Contract
}

// Commitment represents a Poseidon commitment to a credit score
// On-chain: commitment hash, DID, model version, issuer, timestamp
// NEVER on-chain: raw scores, behavioural features, PII, model weights
type Commitment struct {
	CommitmentHash   string `json:"commitmentHash"`   // Poseidon(score, salt)
	DID              string `json:"did"`              // Borrower's decentralized identifier
	ModelVersionHash string `json:"modelVersionHash"` // Hash of model used
	IssuerMSP        string `json:"issuerMSP"`        // MSP ID of issuing org
	Timestamp        string `json:"timestamp"`        // ISO8601 timestamp
	Status           string `json:"status"`           // "active" or "revoked"
	TxID             string `json:"txId"`             // Transaction ID
}

// LoanEvent represents an on-chain record of a loan-related event
// T31d: Each verification is recorded for audit trail
type LoanEvent struct {
	EventID       string `json:"eventId"`       // Unique event identifier
	DID           string `json:"did"`           // Borrower's DID
	EventType     string `json:"eventType"`     // "verification", "approval", "rejection", "default", "repayment"
	ProofHash     string `json:"proofHash"`     // Hash of the ZK proof (if verification)
	ThresholdUsed int    `json:"thresholdUsed"` // Threshold band used in verification
	IssuerMSP     string `json:"issuerMSP"`     // MSP ID of org recording event
	Timestamp     string `json:"timestamp"`     // ISO8601 timestamp
	TxID          string `json:"txId"`          // Transaction ID
}

// QueryResult structure for paginated queries
type QueryResult struct {
	Key    string `json:"key"`
	Record string `json:"record"`
}

// T43: List of MSPs that can endorse write operations
// RegulatoryObserver is explicitly excluded - read-only access enforced at chaincode level
var endorsingMSPs = map[string]bool{
	"CommercialBankAMSP": true,
	"MicrofinanceBMSP":   true,
	"FintechCMSP":        true,
}

// checkWriteAccess verifies the caller is an endorsing org (not RegulatoryObserver)
// T43: Enforces read-only status through access control, not just policy arithmetic
func checkWriteAccess(ctx contractapi.TransactionContextInterface) error {
	mspID, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return fmt.Errorf("failed to get MSP ID: %v", err)
	}
	if !endorsingMSPs[mspID] {
		return fmt.Errorf("access denied: %s is not authorized to perform write operations", mspID)
	}
	return nil
}

// AnchorCommitment stores a new commitment for a borrower
// Only endorsing orgs can call this (RegulatoryObserver excluded by chaincode ACL)
func (c *CreditContract) AnchorCommitment(ctx contractapi.TransactionContextInterface,
	commitmentHash string, did string, modelVersionHash string) error {

	// T43: Check write access - reject RegulatoryObserver
	if err := checkWriteAccess(ctx); err != nil {
		return err
	}

	// Validate inputs
	if commitmentHash == "" || did == "" || modelVersionHash == "" {
		return fmt.Errorf("commitmentHash, did, and modelVersionHash are required")
	}

	// Check if commitment already exists for this DID
	existingBytes, err := ctx.GetStub().GetState(did)
	if err != nil {
		return fmt.Errorf("failed to read state: %v", err)
	}
	if existingBytes != nil {
		// Check if existing commitment is revoked
		var existing Commitment
		err = json.Unmarshal(existingBytes, &existing)
		if err != nil {
			return fmt.Errorf("failed to unmarshal existing commitment: %v", err)
		}
		if existing.Status == "active" {
			return fmt.Errorf("active commitment already exists for DID %s - revoke first", did)
		}
	}

	// Get caller's MSP ID
	mspID, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return fmt.Errorf("failed to get MSP ID: %v", err)
	}

	// Get deterministic timestamp from transaction (consistent across endorsers)
	txTimestamp, err := ctx.GetStub().GetTxTimestamp()
	if err != nil {
		return fmt.Errorf("failed to get transaction timestamp: %v", err)
	}
	timestamp := time.Unix(txTimestamp.Seconds, int64(txTimestamp.Nanos)).UTC().Format(time.RFC3339)

	// Create commitment
	commitment := Commitment{
		CommitmentHash:   commitmentHash,
		DID:              did,
		ModelVersionHash: modelVersionHash,
		IssuerMSP:        mspID,
		Timestamp:        timestamp,
		Status:           "active",
		TxID:             ctx.GetStub().GetTxID(),
	}

	commitmentBytes, err := json.Marshal(commitment)
	if err != nil {
		return fmt.Errorf("failed to marshal commitment: %v", err)
	}

	// Store commitment
	err = ctx.GetStub().PutState(did, commitmentBytes)
	if err != nil {
		return fmt.Errorf("failed to put state: %v", err)
	}

	// Emit event
	err = ctx.GetStub().SetEvent("CommitmentAnchored", commitmentBytes)
	if err != nil {
		return fmt.Errorf("failed to emit event: %v", err)
	}

	return nil
}

// GetCommitment retrieves a commitment by DID
// All orgs including RegulatoryObserver can read
func (c *CreditContract) GetCommitment(ctx contractapi.TransactionContextInterface,
	did string) (*Commitment, error) {

	commitmentBytes, err := ctx.GetStub().GetState(did)
	if err != nil {
		return nil, fmt.Errorf("failed to read state: %v", err)
	}
	if commitmentBytes == nil {
		return nil, fmt.Errorf("commitment not found for DID %s", did)
	}

	var commitment Commitment
	err = json.Unmarshal(commitmentBytes, &commitment)
	if err != nil {
		return nil, fmt.Errorf("failed to unmarshal commitment: %v", err)
	}

	return &commitment, nil
}

// RecordLoanEvent records a loan event for audit trail
// T31d: Each verification recorded - enables detecting repeated probing
func (c *CreditContract) RecordLoanEvent(ctx contractapi.TransactionContextInterface,
	did string, eventType string, proofHash string, thresholdUsed int) error {

	// T43: Check write access - reject RegulatoryObserver
	if err := checkWriteAccess(ctx); err != nil {
		return err
	}

	// Validate inputs
	if did == "" || eventType == "" {
		return fmt.Errorf("did and eventType are required")
	}

	validEventTypes := map[string]bool{
		"verification": true,
		"approval":     true,
		"rejection":    true,
		"default":      true,
		"repayment":    true,
	}
	if !validEventTypes[eventType] {
		return fmt.Errorf("invalid eventType: %s", eventType)
	}

	// Get caller's MSP ID
	mspID, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return fmt.Errorf("failed to get MSP ID: %v", err)
	}

	// Create event ID
	txID := ctx.GetStub().GetTxID()
	eventID := fmt.Sprintf("event_%s_%s", did, txID[:8])

	// Get deterministic timestamp from transaction
	txTimestamp, err := ctx.GetStub().GetTxTimestamp()
	if err != nil {
		return fmt.Errorf("failed to get transaction timestamp: %v", err)
	}
	timestamp := time.Unix(txTimestamp.Seconds, int64(txTimestamp.Nanos)).UTC().Format(time.RFC3339)

	// Create loan event
	event := LoanEvent{
		EventID:       eventID,
		DID:           did,
		EventType:     eventType,
		ProofHash:     proofHash,
		ThresholdUsed: thresholdUsed,
		IssuerMSP:     mspID,
		Timestamp:     timestamp,
		TxID:          txID,
	}

	eventBytes, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("failed to marshal event: %v", err)
	}

	// Store event with composite key for efficient querying
	compositeKey, err := ctx.GetStub().CreateCompositeKey("event", []string{did, eventID})
	if err != nil {
		return fmt.Errorf("failed to create composite key: %v", err)
	}

	err = ctx.GetStub().PutState(compositeKey, eventBytes)
	if err != nil {
		return fmt.Errorf("failed to put state: %v", err)
	}

	// Emit chaincode event
	err = ctx.GetStub().SetEvent("LoanEventRecorded", eventBytes)
	if err != nil {
		return fmt.Errorf("failed to emit event: %v", err)
	}

	return nil
}

// GetCreditHistory retrieves all events for a DID
// Demonstrates T31d: 40 queries leave permanent audit trail
func (c *CreditContract) GetCreditHistory(ctx contractapi.TransactionContextInterface,
	did string) ([]*LoanEvent, error) {

	// Query all events for this DID using composite key
	iterator, err := ctx.GetStub().GetStateByPartialCompositeKey("event", []string{did})
	if err != nil {
		return nil, fmt.Errorf("failed to get state by partial composite key: %v", err)
	}
	defer iterator.Close()

	var events []*LoanEvent
	for iterator.HasNext() {
		result, err := iterator.Next()
		if err != nil {
			return nil, fmt.Errorf("failed to iterate: %v", err)
		}

		var event LoanEvent
		err = json.Unmarshal(result.Value, &event)
		if err != nil {
			return nil, fmt.Errorf("failed to unmarshal event: %v", err)
		}

		events = append(events, &event)
	}

	return events, nil
}

// RevokeCommitment marks a commitment as revoked
// Only the original issuer or an admin can revoke
func (c *CreditContract) RevokeCommitment(ctx contractapi.TransactionContextInterface,
	did string) error {

	// T43: Check write access - reject RegulatoryObserver
	if err := checkWriteAccess(ctx); err != nil {
		return err
	}

	// Get existing commitment
	commitmentBytes, err := ctx.GetStub().GetState(did)
	if err != nil {
		return fmt.Errorf("failed to read state: %v", err)
	}
	if commitmentBytes == nil {
		return fmt.Errorf("commitment not found for DID %s", did)
	}

	var commitment Commitment
	err = json.Unmarshal(commitmentBytes, &commitment)
	if err != nil {
		return fmt.Errorf("failed to unmarshal commitment: %v", err)
	}

	if commitment.Status == "revoked" {
		return fmt.Errorf("commitment already revoked")
	}

	// Get caller's MSP ID
	mspID, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return fmt.Errorf("failed to get MSP ID: %v", err)
	}

	// Only original issuer can revoke (could add admin override)
	if mspID != commitment.IssuerMSP {
		return fmt.Errorf("only the original issuer can revoke this commitment")
	}

	// Update status
	commitment.Status = "revoked"
	commitment.TxID = ctx.GetStub().GetTxID()

	updatedBytes, err := json.Marshal(commitment)
	if err != nil {
		return fmt.Errorf("failed to marshal updated commitment: %v", err)
	}

	err = ctx.GetStub().PutState(did, updatedBytes)
	if err != nil {
		return fmt.Errorf("failed to put state: %v", err)
	}

	// Emit event
	err = ctx.GetStub().SetEvent("CommitmentRevoked", updatedBytes)
	if err != nil {
		return fmt.Errorf("failed to emit event: %v", err)
	}

	return nil
}

// CountVerifications counts verification events for a DID
// Useful for detecting repeated probing attempts
func (c *CreditContract) CountVerifications(ctx contractapi.TransactionContextInterface,
	did string) (int, error) {

	events, err := c.GetCreditHistory(ctx, did)
	if err != nil {
		return 0, err
	}

	count := 0
	for _, event := range events {
		if event.EventType == "verification" {
			count++
		}
	}

	return count, nil
}

func main() {
	chaincode, err := contractapi.NewChaincode(&CreditContract{})
	if err != nil {
		fmt.Printf("Error creating credit chaincode: %v", err)
		return
	}

	if err := chaincode.Start(); err != nil {
		fmt.Printf("Error starting credit chaincode: %v", err)
	}
}
