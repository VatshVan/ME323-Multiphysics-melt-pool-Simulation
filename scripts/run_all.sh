#!/bin/bash
#------------------------------------------------------------------------------
# Run every case in cases/ one after another, analyse each as it finishes and
# rebuild results/melt_pool_dataset.xlsx after every run.
#
# Safe to re-run: finished cases (results/<case>/summary.json exists) are
# skipped, and an interrupted case resumes from its latest write time.
#
# Usage (from the project root):
#   nohup bash scripts/run_all.sh > run_all.log 2>&1 &
#   bash scripts/run_all.sh R01 R02        # only these cases
#------------------------------------------------------------------------------
cd "$(dirname "$0")/.." || exit 1
set +u
. setup/env.sh > /dev/null

cases=("$@")
[ ${#cases[@]} -eq 0 ] && cases=($(ls -d cases/*/ | xargs -n1 basename))

for c in "${cases[@]}"; do
    if [ -f "results/$c/summary.json" ]; then
        echo "$(date '+%F %T')  $c: already analysed, skipping"
        continue
    fi
    echo "$(date '+%F %T')  $c: running"
    (cd "cases/$c" && ./Allrun > allrun.out 2>&1)
    if ! tail -1 "cases/$c/log.additiveFoam" | grep -q "Finalising parallel run"; then
        echo "$(date '+%F %T')  $c: solver did not finish, see cases/$c/log.additiveFoam"
        continue
    fi
    python scripts/analyze_case.py "cases/$c" > "cases/$c/log.analyze" 2>&1 \
        && echo "$(date '+%F %T')  $c: analysed" \
        || echo "$(date '+%F %T')  $c: analysis failed, see cases/$c/log.analyze"
    python scripts/export_excel.py
done
echo "$(date '+%F %T')  all done"
