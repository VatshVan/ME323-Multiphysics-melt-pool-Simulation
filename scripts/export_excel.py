#!/usr/bin/env python3
"""Export the scan-speed runs as an Excel workbook for machine learning.

Reads the analysed runs (results/<case>/summary.json and timeseries.csv,
written by analyze_case.py) and each case's solidification events, and
writes results/melt_pool_dataset.xlsx with the sheets:

    runs            one row per run: inputs + quasi-steady outputs
    timeseries      every run sampled every --dt seconds: time, beam position,
                    laser on/off, T_max, |U|_max, pool length/width/depth
    solidification  every solidification event in the fine region: position,
                    time, cooling rate, G, R, G/R, G*R (inputs repeated)
    columns         description and unit of every column

Input columns are repeated on every row so each sheet can be used on its own.

Usage:
    python scripts/export_excel.py              # all analysed cases/v*mmps
    python scripts/export_excel.py --dt 0.005
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

INPUTS = {
    "scan_speed_mm_s": ("Laser scan speed", "mm/s"),
    "laser_power_W": ("Laser power", "W"),
    "absorptivity": ("Absorptivity", "-"),
    "absorbed_power_W": ("Absorbed power = laser power x absorptivity", "W"),
    "beam_radius_mm": ("Beam radius (1/e^2)", "mm"),
    "line_energy_J_mm": ("Absorbed power / scan speed", "J/mm"),
    "cell_size_um": ("Grid size in the fine region", "um"),
}

COLUMNS = {
    **INPUTS,
    "case": ("Case directory name", "-"),
    "first_melting_s": ("Time T_max first reaches the solidus", "s"),
    "fully_liquid_surface_s": ("Time T_max first reaches the liquidus", "s"),
    "laser_off_s": ("Time the laser switches off", "s"),
    "pool_fully_solidified_s": ("Time the pool (solidus) has fully solidified after laser off", "s"),
    "peak_T_K": ("Highest temperature in the run", "K"),
    "peak_U_m_s": ("Highest melt velocity in the run", "m/s"),
    "qs_T_max_K": ("Quasi-steady peak temperature (mean over 40-90% of the track)", "K"),
    "qs_U_max_m_s": ("Quasi-steady peak velocity", "m/s"),
    "qs_depth_mm": ("Quasi-steady pool depth (liquidus)", "mm"),
    "qs_width_mm": ("Quasi-steady pool full width (liquidus)", "mm"),
    "qs_length_mm": ("Quasi-steady pool length (liquidus)", "mm"),
    "cooling_rate_median_K_s": ("Median cooling rate at solidification", "K/s"),
    "G_median_K_mm": ("Median temperature gradient at solidification", "K/mm"),
    "R_median_mm_s": ("Median solidification rate", "mm/s"),
    "G_over_R_median_Ks_mm2": ("Median G/R", "K s/mm^2"),
    "GR_median_K_s": ("Median G*R", "K/s"),
    "time_s": ("Simulation time", "s"),
    "beam_x_mm": ("Beam centre position along the track", "mm"),
    "laser_on": ("1 while the laser is on, 0 after", "-"),
    "T_max_K": ("Peak temperature at this time", "K"),
    "U_max_m_s": ("Peak melt velocity at this time", "m/s"),
    "depth_mm": ("Pool depth at the liquidus", "mm"),
    "width_mm": ("Pool full width at the liquidus", "mm"),
    "length_mm": ("Pool length at the liquidus", "mm"),
    "depth_solidus_mm": ("Pool depth at the solidus (incl. mushy zone)", "mm"),
    "width_solidus_mm": ("Pool full width at the solidus", "mm"),
    "length_solidus_mm": ("Pool length at the solidus", "mm"),
    "x_mm": ("Position along the track", "mm"),
    "y_mm": ("Distance from the track centreline (half model, y >= 0)", "mm"),
    "z_mm": ("Height (top surface z = 0, negative into the part)", "mm"),
    "solidification_time_s": ("Time the location solidified", "s"),
    "cooling_rate_K_s": ("Cooling rate at solidification", "K/s"),
    "G_K_mm": ("Temperature gradient magnitude at solidification", "K/mm"),
    "R_mm_s": ("Solidification rate (interface speed)", "mm/s"),
    "G_over_R_Ks_mm2": ("G/R (morphology)", "K s/mm^2"),
    "GR_K_s": ("G*R (= cooling rate, scale of microstructure)", "K/s"),
}


def get(d, *keys):
    for k in keys:
        if d is None:
            return None
        d = d.get(k)
    return d


def run_inputs(s):
    i = s["inputs"]
    return {
        "scan_speed_mm_s": i["scan_speed_m_s"]*1e3,
        "laser_power_W": i["laser_power_W"],
        "absorptivity": i["absorptivity"],
        "absorbed_power_W": i["absorbed_power_W"],
        "beam_radius_mm": i["beam_radius_m"]*1e3,
        "line_energy_J_mm": i["line_energy_J_m"]*1e-3,
        "cell_size_um": i["cell_size_m"]*1e6,
    }


def run_row(s):
    q, sol = s["quasi_steady"], s.get("solidification")
    row = {"case": s["case"], **run_inputs(s)}
    row.update({
        "first_melting_s": s["first_melting_s"],
        "fully_liquid_surface_s": s["fully_liquid_surface_s"],
        "laser_off_s": s["laser_off_s"],
        "pool_fully_solidified_s": s["pool_fully_solidified_s"],
        "peak_T_K": s["peak_T_K"],
        "peak_U_m_s": s["peak_U_m_s"],
        "qs_T_max_K": get(q, "T_max_K", "mean"),
        "qs_U_max_m_s": get(q, "U_max_m_s", "mean"),
        "qs_depth_mm": get(q, "pool_depth_mm", "mean"),
        "qs_width_mm": get(q, "pool_width_full_mm", "mean"),
        "qs_length_mm": get(q, "pool_length_mm", "mean"),
        "cooling_rate_median_K_s": get(sol, "cooling_rate_K_s", "median"),
        "G_median_K_mm": (get(sol, "G_K_m", "median") or np.nan)*1e-3,
        "R_median_mm_s": (get(sol, "R_m_s", "median") or np.nan)*1e3,
        "G_over_R_median_Ks_mm2": (get(sol, "G_over_R_Ks_m2", "median") or np.nan)*1e-6,
        "GR_median_K_s": get(sol, "GR_K_s", "median"),
    })
    return row


def timeseries(s, out, dt):
    ts = pd.read_csv(out/"timeseries.csv")
    grid = np.arange(0.0, ts["time_s"].iloc[-1] + 0.5*dt, dt)
    i = s["inputs"]
    v, x0, t_off = i["scan_speed_m_s"], i["track_start_m"], s["laser_off_s"]
    df = pd.DataFrame({"time_s": grid})
    df["beam_x_mm"] = (x0 + v*np.minimum(grid, t_off))*1e3
    df["laser_on"] = (grid <= t_off).astype(int)
    for col, src, scale in (("T_max_K", "T_max_K", 1), ("U_max_m_s", "U_max_m_s", 1),
                            ("depth_mm", "depth_liq_m", 1e3), ("width_mm", "width_full_liq_m", 1e3),
                            ("length_mm", "length_liq_m", 1e3), ("depth_solidus_mm", "depth_sol_m", 1e3),
                            ("width_solidus_mm", "width_full_sol_m", 1e3),
                            ("length_solidus_mm", "length_sol_m", 1e3)):
        df[col] = np.interp(grid, ts["time_s"], ts[src])*scale
    return df


def solidification(case_dir):
    files = sorted(case_dir.glob("solidificationData/solidification-data*.csv")) \
        or sorted(case_dir.glob("solidificationData/data_*.csv"))
    if not files:
        return None
    d = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    G = np.sqrt(d["gx"]**2 + d["gy"]**2 + d["gz"]**2)
    R = d["v"].where(d["v"] > 0)
    return pd.DataFrame({
        "x_mm": d["x"]*1e3, "y_mm": d["y"]*1e3, "z_mm": d["z"]*1e3,
        "solidification_time_s": d["ts"],
        "cooling_rate_K_s": d["cr"],
        "G_K_mm": G*1e-3,
        "R_mm_s": R*1e3,
        "G_over_R_Ks_mm2": G/R*1e-6,
        "GR_K_s": G*R,
    })


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dt", type=float, default=0.01, help="time-series sampling interval [s]")
    p.add_argument("--out", type=Path, default=ROOT/"results"/"melt_pool_dataset.xlsx")
    args = p.parse_args()

    runs, series, events = [], [], []
    for f in sorted((ROOT/"results").glob("v*mmps/summary.json")):
        s = json.loads(f.read_text())
        inp = run_inputs(s)
        runs.append(run_row(s))
        ts = timeseries(s, f.parent, args.dt)
        series.append(pd.concat([pd.DataFrame([inp]*len(ts)), ts], axis=1))
        sol = solidification(ROOT/"cases"/s["case"])
        if sol is not None:
            events.append(pd.concat([pd.DataFrame([inp]*len(sol)), sol], axis=1))
    if not runs:
        raise SystemExit("no results/v*mmps/summary.json; run analyze_case.py on each case first")

    sheets = {"runs": pd.DataFrame(runs), "timeseries": pd.concat(series, ignore_index=True)}
    if events:
        sheets["solidification"] = pd.concat(events, ignore_index=True)
    used = [c for df in sheets.values() for c in df.columns]
    sheets["columns"] = pd.DataFrame(
        [{"column": c, "description": COLUMNS[c][0], "unit": COLUMNS[c][1]}
         for c in dict.fromkeys(used) if c in COLUMNS])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(args.out, engine="openpyxl") as xw:
        for name, df in sheets.items():
            if len(df) > 1_048_575:
                raise SystemExit(f"sheet {name} has {len(df)} rows, over Excel's limit")
            df.to_excel(xw, sheet_name=name, index=False)
    print(", ".join(f"{k}: {len(v)} rows" for k, v in sheets.items()), f"-> {args.out}")


if __name__ == "__main__":
    main()
