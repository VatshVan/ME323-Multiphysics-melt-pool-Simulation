#!/usr/bin/env python3
"""Flatten results/*/summary.json (written by analyze_case.py) into one table,
one row per run: inputs first (in_*), then outputs (out_*).

Writes results/dataset.csv and results/dataset.json. Nested keys are joined
with '.', e.g. out_quasi_steady.pool_depth_mm.mean.

Usage:
    python scripts/collect_dataset.py
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        elif isinstance(v, list):
            for i, x in enumerate(v):
                out[f"{key}.{i}"] = x
        else:
            out[key] = v
    return out


def main():
    rows = []
    for f in sorted((ROOT/"results").glob("*/summary.json")):
        s = json.loads(f.read_text())
        row = {"case": s.pop("case")}
        row.update({f"in_{k}": v for k, v in flatten(s.pop("inputs", {})).items()})
        row.update({f"out_{k}": v for k, v in flatten(s).items()})
        rows.append(row)
    if not rows:
        raise SystemExit("no results/*/summary.json yet; run analyze_case.py first")

    cols = []
    for r in rows:
        cols += [c for c in r if c not in cols]
    with open(ROOT/"results"/"dataset.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    (ROOT/"results"/"dataset.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(f"{len(rows)} runs, {len(cols)} columns -> results/dataset.csv, results/dataset.json")


if __name__ == "__main__":
    main()
