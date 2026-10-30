#!/bin/bash
# One-off watcher (2026-10-31): the TA's uniform-beam set (run_all.sh, pid
# 165143) runs first while the 50 um run V1000_v6_50um is paused; then the
# 50 um run continues, and once its Allrun (pid 157880) has finished it is
# analysed (no .vtu, processor copies removed to save disk).
cd "$(dirname "$0")/.." || exit 1
set +u
. setup/env.sh > /dev/null
while kill -0 165143 2>/dev/null; do sleep 60; done
kill -CONT 157915 157916 157917 157918 157919 157920 157921 157922 157908  && echo "$(date '+%F %T')  TA set done; resumed V1000_v6_50um"
while kill -0 157880 2>/dev/null; do sleep 60; done
c=V1000_v6_50um
if tail -1 cases/$c/log.additiveFoam | grep -q "Finalising parallel run" && tail -3 cases/$c/log.reconstructPar | grep -q "^End"; then
    rm -rf cases/$c/processor*
    python scripts/analyze_case.py cases/$c --no-vtu > cases/$c/log.analyze 2>&1 && echo "$(date '+%F %T')  $c: analysed"
    python scripts/export_excel.py
else
    echo "$(date '+%F %T')  $c: did not finish, see cases/$c/log.*"
fi
echo "$(date '+%F %T')  all done"
