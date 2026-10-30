#!/bin/bash
#------------------------------------------------------------------------------
# Run the 50 um grid-study cases one after another (like run_all.sh), with two
# disk savings for the 5x larger meshes: no full-block .vtu export (re-create
# with scripts/export_3d.py if needed) and the processor* copies are removed
# once reconstructPar has merged them (the case can then no longer be resumed,
# but it is finished).
#
# Usage (from the project root):
#   nohup bash scripts/run_grid_study.sh > run_grid_study.log 2>&1 &
#------------------------------------------------------------------------------
cd "$(dirname "$0")/.." || exit 1
set +u
. setup/env.sh > /dev/null

cases=("$@")
[ ${#cases[@]} -eq 0 ] && cases=(V1000_v6_50um V1000_v9_50um V1000_v12_50um)

for c in "${cases[@]}"; do
    if [ -f "results/$c/summary.json" ]; then
        echo "$(date '+%F %T')  $c: already analysed, skipping"
        continue
    fi
    echo "$(date '+%F %T')  $c: running ($(df -h --output=avail /home | tail -1 | tr -d ' ') free)"
    (cd "cases/$c" && ./Allrun > allrun.out 2>&1)
    if ! tail -1 "cases/$c/log.additiveFoam" | grep -q "Finalising parallel run"; then
        echo "$(date '+%F %T')  $c: solver did not finish, see cases/$c/log.additiveFoam"
        continue
    fi
    if tail -3 "cases/$c/log.reconstructPar" | grep -q "^End"; then
        rm -rf "cases/$c"/processor*
    fi
    python scripts/analyze_case.py "cases/$c" --no-vtu > "cases/$c/log.analyze" 2>&1 \
        && echo "$(date '+%F %T')  $c: analysed" \
        || echo "$(date '+%F %T')  $c: analysis failed, see cases/$c/log.analyze"
    python scripts/export_excel.py
done
echo "$(date '+%F %T')  all done"
