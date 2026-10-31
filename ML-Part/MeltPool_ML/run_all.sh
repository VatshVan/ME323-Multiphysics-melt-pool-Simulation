#!/usr/bin/env bash
# Rerun the whole ML pipeline with the saved tuned hyperparameters
# (models/run_params.json, models/event_params.json). To repeat the Optuna
# search (~1.5 h), run steps 2 and 3 by hand with --retune.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p results
for step in build_dataset step1_feature_sets step2_ensemble step3_events step4_experiment step5_shap \
            step6_analysis step7_learning_curve; do
    echo "== $step $(date +%H:%M:%S)"
    python3.11 $step.py > results/$step.log 2>&1 || { echo "FAILED: $step (see results/$step.log)"; exit 1; }
done
echo "== done $(date +%H:%M:%S)"
