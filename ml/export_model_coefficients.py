"""
Export LogisticRegression model coefficients for use in JavaScript.

This allows the integration demo to use REAL ML inference instead of simulated.
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

# Paths
DATA_DIR = Path(__file__).parent.parent / 'data'
RESULTS_DIR = Path(__file__).parent.parent / 'results'

def main():
    # Load data
    features = pd.read_csv(DATA_DIR / 'features_processed.csv')
    canonical = json.loads((RESULTS_DIR / 'canonical_split.json').read_text())

    train_idx = canonical['indices']['train']
    test_idx = canonical['indices']['test']

    X = features.drop(columns=['customerid', 'target', 'good_bad_flag'])
    y = features['target']

    X_train = X.iloc[train_idx]
    y_train = y.iloc[train_idx]

    # Fit scaler
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    # Train model
    model = LogisticRegression(
        class_weight='balanced',
        solver='lbfgs',
        max_iter=1000,
        random_state=42
    )
    model.fit(X_train_scaled, y_train)

    # Export coefficients
    coefficients = {
        'feature_names': list(X.columns),
        'intercept': float(model.intercept_[0]),
        'coefficients': [float(c) for c in model.coef_[0]],
        'scaler_mean': [float(m) for m in scaler.mean_],
        'scaler_scale': [float(s) for s in scaler.scale_],
        'description': 'LogisticRegression with balanced class weights, trained on canonical split',
        'score_formula': 'score = round(1000 * (1 - P(default)))',
        'positive_class': 'default (target=1)',
        'n_train': len(train_idx),
        'n_test': len(test_idx)
    }

    # Save
    output_path = RESULTS_DIR / 'lr_model_coefficients.json'
    with open(output_path, 'w') as f:
        json.dump(coefficients, f, indent=2)

    print(f"Model coefficients exported to {output_path}")
    print(f"Features: {len(coefficients['feature_names'])}")
    print(f"Intercept: {coefficients['intercept']:.4f}")
    print(f"First 5 coefficients: {coefficients['coefficients'][:5]}")

    # Verify: predict on first few test samples
    X_test = X.iloc[test_idx[:5]]
    X_test_scaled = scaler.transform(X_test)
    probs = model.predict_proba(X_test_scaled)[:, 1]  # P(default)
    scores = np.round(1000 * (1 - probs)).astype(int)

    print(f"\nVerification (first 5 test samples):")
    for i, (p, s) in enumerate(zip(probs, scores)):
        print(f"  Sample {i}: P(default)={p:.3f}, score={s}")

if __name__ == '__main__':
    main()
