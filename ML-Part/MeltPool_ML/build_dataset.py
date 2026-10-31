#!/usr/bin/env python3
"""Build the ML datasets from the analysed melt-pool runs.

Writes, in ML-Part/MeltPool_ML/data/:

    runs.csv        one row per run: process inputs, flow flags and the
                    quasi-steady outputs (same definitions as
                    scripts/export_excel.py)
    events.csv.gz   every solidification event of the laser-on track:
                    run inputs, position scaled by the run's pool size,
                    G, R, G/R, G*R
    liquid.json     liquid properties used for Ma, Pe (identical in all runs)

Runs left out: every *_50um case (not fully simulated) and the
archive_overheated set. Only results/<case>/summary.json with a
quasi-steady window are used.

Usage:
    python ML-Part/MeltPool_ML/build_dataset.py
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
from export_excel import liquid_props, marangoni, run_row  # noqa: E402

OUT = HERE/"data"


def flags(case_dir):
    """Flow switches as the solver sees them: Marangoni (dSigmadT != 0),
    flow solve (nOuterCorrectors > 0), buoyancy (beta > 0 with flow on),
    and the superGaussian exponent k of the beam (2 = Gaussian)."""
    tp = (case_dir/"constant"/"transportProperties").read_text()
    fv = (case_dir/"system"/"fvSolution").read_text()
    hs = (case_dir/"constant"/"heatSourceDict").read_text()
    dsdt = float(re.search(r"^dSigmadT\s+([0-9.eE+-]+);", tp, re.M).group(1))
    beta = float(re.search(r"^beta\s+\[[^\]]*\]\s+([0-9.eE+-]+);", tp, re.M).group(1))
    m = re.search(r"nOuterCorrectors\s+(\d+);", fv)
    flow = int(m.group(1)) > 0 if m else True
    k = float(re.search(r"^\s*k\s+([0-9.eE+-]+);", hs, re.M).group(1))
    return {"marangoni": int(flow and dsdt != 0), "buoyancy": int(flow and beta > 0),
            "flow": int(flow), "beam_k": k}


def mode(f):
    if not f["flow"]:
        return "none"
    return ("Ma" if f["marangoni"] else "") + ("B" if f["buoyancy"] else "")


def case_set(name):
    return {"R": "R", "V": "V", "U": "U"}[name[0]]


def main():
    OUT.mkdir(exist_ok=True)
    runs, events, liquid = [], [], None
    for f in sorted((ROOT/"results").glob("*/summary.json")):
        case = f.parent.name
        if "50um" in case:
            continue
        s = json.loads(f.read_text())
        if not s.get("quasi_steady"):
            print(f"skip {case}: no quasi-steady window")
            continue
        case_dir = ROOT/"cases"/case
        row = run_row(s, marangoni(s, f.parent))
        fl = flags(case_dir)
        row.update(set=case_set(case), mode=mode(fl), **fl)
        i = s["inputs"]
        row["track_start_mm"] = i["track_start_m"]*1e3
        row["track_end_mm"] = i["track_end_m"]*1e3
        runs.append(row)

        m = liquid_props(case_dir)
        # beta is 0 in the conduction-only runs; Ma and Pe do not use it
        props = {k: m[k] for k in ("rho", "mu", "k", "cp", "T_sol")}
        if liquid is None:
            liquid = props
        elif any(not np.isclose(liquid[k], props[k]) for k in props):
            raise SystemExit(f"{case}: liquid properties differ from the other runs")

        ev = events_of(case_dir, row, s["laser_off_s"])
        if ev is not None:
            events.append(ev)

    runs = pd.DataFrame(runs)
    lead = ["case", "set", "mode", "laser_power_W", "absorptivity", "absorbed_power_W",
            "scan_speed_mm_s", "beam_radius_mm", "beam_k", "marangoni", "buoyancy", "flow",
            "dSigmadT_N_mK", "line_energy_J_mm", "cell_size_um"]
    runs = runs[lead + [c for c in runs.columns if c not in lead]]
    runs.to_csv(OUT/"runs.csv", index=False)
    ev = pd.concat(events, ignore_index=True)
    ev.to_csv(OUT/"events.csv.gz", index=False, float_format="%.6g")
    (OUT/"liquid.json").write_text(json.dumps(liquid, indent=2))
    print(f"runs: {len(runs)} ({runs['set'].value_counts().to_dict()}), "
          f"modes {runs['mode'].value_counts().to_dict()}")
    print(f"events: {len(ev)} from {ev['case'].nunique()} runs -> {OUT}")


def events_of(case_dir, row, t_off):
    """Laser-on solidification events of one run. Position is scaled by the
    run's quasi-steady pool: z/depth, y/half-width, and distance from the
    track start in mm (the start transient is kept; the model sees it)."""
    files = sorted(case_dir.glob("solidificationData/solidification-data*.csv"))
    if not files:
        return None
    d = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    d = d[(d["ts"] <= t_off) & (d["v"] > 0)]
    G = np.sqrt(d["gx"]**2 + d["gy"]**2 + d["gz"]**2)*1e-3  # K/mm
    R = d["v"]*1e3                                           # mm/s
    x_mm = d["x"]*1e3
    keep = (G > 0) & np.isfinite(G) & np.isfinite(R)
    inputs = {k: row[k] for k in ("case", "set", "mode", "absorbed_power_W", "scan_speed_mm_s",
                                  "beam_radius_mm", "beam_k", "marangoni", "buoyancy", "flow")}
    ev = pd.DataFrame({
        **inputs,
        "x_mm": x_mm, "y_mm": d["y"]*1e3, "z_mm": d["z"]*1e3,
        "s_track_mm": x_mm - row["track_start_mm"],
        "y_over_halfwidth": d["y"]*1e3/(row["qs_width_mm"]/2),
        "z_over_depth": -d["z"]*1e3/row["qs_depth_mm"],
        "solidification_time_s": d["ts"],
        "cooling_rate_K_s": d["cr"],
        "G_K_mm": G, "R_mm_s": R, "G_over_R_Ks_mm2": G/R, "GR_K_s": G*R,
    })[keep.values]
    return ev


if __name__ == "__main__":
    main()
