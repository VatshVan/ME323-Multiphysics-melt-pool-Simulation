#!/usr/bin/env python3
"""Export the scan-speed runs as an Excel workbook for machine learning.

Reads the analysed runs (results/<case>/summary.json and timeseries.csv,
written by analyze_case.py) and each case's solidification events, and
writes results/melt_pool_dataset.xlsx with the sheets:

    runs            one row per run: inputs + quasi-steady outputs, incl.
                    Marangoni stress, surface flow and Ma, Gr, Ma/Gr, Pe, Re
    marangoni       every field snapshot: Marangoni shear stress, surface
                    temperature gradient and speed, flow direction, Ma, Pe ...
    timeseries      every run sampled every --dt seconds: time, beam position,
                    laser on/off, T_max, |U|_max, pool length/width/depth,
                    Ma, Gr, Ma/Gr, Pe, Re (Farzadi 2008 definitions)
    solidification  every solidification event in the fine region: position,
                    time, cooling rate, G, R, G/R, G*R (inputs repeated)
    columns         description and unit of every column

Input columns are repeated on every row so each sheet can be used on its own.

Usage:
    python scripts/export_excel.py              # every analysed run in results/
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
    "dSigmadT_N_mK": ("Temperature coefficient of surface tension (0 = no Marangoni)", "N/(m K)"),
}

COLUMNS = {
    **INPUTS,
    "case": ("Case directory name", "-"),
    "first_melting_s": ("Time T_max first reaches the solidus", "s"),
    "fully_liquid_surface_s": ("Time T_max first reaches the liquidus", "s"),
    "laser_off_s": ("Time the laser switches off (may be after run_end_s)", "s"),
    "run_end_s": ("Last simulated time of the run", "s"),
    "laser_on_at_end": ("1 if the laser was still on when the run ended", "-"),
    "pool_fully_solidified_s": ("Time the pool (solidus) has fully solidified after laser off", "s"),
    "peak_T_K": ("Highest temperature in the run", "K"),
    "peak_U_m_s": ("Highest melt velocity in the run", "m/s"),
    "qs_T_max_K": ("Quasi-steady peak temperature (mean over the last 40% of laser-on time)", "K"),
    "qs_U_max_m_s": ("Quasi-steady peak velocity", "m/s"),
    "qs_depth_mm": ("Quasi-steady pool depth (liquidus)", "mm"),
    "qs_width_mm": ("Quasi-steady pool full width (liquidus)", "mm"),
    "qs_length_mm": ("Quasi-steady pool length (liquidus)", "mm"),
    "qs_marangoni_snapshots_s": ("Snapshot times averaged for the qs_ Marangoni columns (the steady window, "
                                 "or the last snapshot with a pool before it ends)", "s"),
    **{f"qs_{k}": (f"Quasi-steady (snapshot mean in the steady window): {v[0]}", v[1]) for k, v in {
        "gradT_surface_max_K_mm": ("max surface temperature gradient", "K/mm"),
        "gradT_surface_mean_K_mm": ("mean surface temperature gradient", "K/mm"),
        "marangoni_stress_max_Pa": ("max Marangoni shear stress", "Pa"),
        "marangoni_stress_mean_Pa": ("mean Marangoni shear stress", "Pa"),
        "U_surface_max_m_s": ("max surface speed", "m/s"),
        "U_surface_mean_m_s": ("mean surface speed", "m/s"),
        "surface_flow_direction": ("surface flow direction (+1 outward, -1 inward)", "-"),
        "surface_liquid_area_mm2": ("molten surface area", "mm^2"),
        "Ma": ("Marangoni number (Farzadi Eq. 17)", "-"),
        "Gr": ("Grashof number (Farzadi Eq. 15)", "-"),
        "R_SB": ("Marangoni/buoyancy ratio Ma/Gr (Farzadi Eq. 18)", "-"),
        "Pe": ("Peclet number with mean surface speed (Farzadi Eq. 14)", "-"),
        "Re": ("Reynolds number with mean surface speed", "-"),
        "u_m_Farzadi_m_s": ("Marangoni velocity scale (Farzadi Eq. 20)", "m/s"),
    }.items()},
    "cooling_rate_median_K_s": ("Median cooling rate at solidification along the track (laser on)", "K/s"),
    "G_median_K_mm": ("Median temperature gradient at solidification along the track", "K/mm"),
    "R_median_mm_s": ("Median solidification rate along the track", "mm/s"),
    "G_over_R_median_Ks_mm2": ("Median G/R along the track", "K s/mm^2"),
    "GR_median_K_s": ("Median G*R along the track", "K/s"),
    "bottom_cooling_rate_K_s": ("Cooling rate at the pool bottom on the centreline (track)", "K/s"),
    "bottom_G_K_mm": ("G at the pool bottom on the centreline (track)", "K/mm"),
    "bottom_R_mm_s": ("R at the pool bottom on the centreline (track)", "mm/s"),
    "crater_cooling_rate_median_K_s": ("Median cooling rate of the end crater (after laser off)", "K/s"),
    "crater_R_median_mm_s": ("Median solidification rate of the end crater", "mm/s"),
    "time_s": ("Simulation time", "s"),
    "beam_x_mm": ("Beam centre position along the track", "mm"),
    "T_max_K": ("Peak temperature at this time", "K"),
    "U_max_m_s": ("Peak melt velocity at this time", "m/s"),
    "depth_mm": ("Pool depth at the liquidus", "mm"),
    "width_mm": ("Pool full width at the liquidus", "mm"),
    "length_mm": ("Pool length at the liquidus", "mm"),
    "depth_solidus_mm": ("Pool depth at the solidus (incl. mushy zone)", "mm"),
    "width_solidus_mm": ("Pool full width at the solidus", "mm"),
    "length_solidus_mm": ("Pool length at the solidus", "mm"),
    "dSigmadT_N_mK": ("Temperature coefficient of surface tension used in the run (0 = no Marangoni)", "N/(m K)"),
    "Ma": ("Marangoni (surface tension Reynolds) number rho L_R dT |dSigma/dT| / mu^2, L_R = half width, dT = T_max - T_sol (Farzadi 2008 Eq. 17)", "-"),
    "Gr": ("Grashof number g beta L_B^3 dT rho^2 / mu^2, L_B = width/8 (Farzadi Eq. 15)", "-"),
    "R_SB": ("Marangoni / buoyancy force ratio Ma/Gr (Farzadi Eq. 18)", "-"),
    "Pe": ("Peclet number u rho cp L_R / k (Farzadi Eq. 14); u = U_max in timeseries, mean surface speed in marangoni/runs", "-"),
    "Re": ("Reynolds number rho u L_R / mu", "-"),
    "u_m_Farzadi_m_s": ("Marangoni velocity scale from Farzadi Eq. 20 (compare with U_max)", "m/s"),
    "surface_liquid_area_mm2": ("Molten top-surface area (full width)", "mm^2"),
    "gradT_surface_max_K_mm": ("Max surface temperature gradient |grad_s T| on the molten surface", "K/mm"),
    "gradT_surface_mean_K_mm": ("Mean surface temperature gradient on the molten surface", "K/mm"),
    "marangoni_stress_max_Pa": ("Max thermocapillary shear |dSigma/dT| fL |grad_s T| (the solver's Marangoni BC)", "Pa"),
    "marangoni_stress_mean_Pa": ("Mean thermocapillary shear on the molten surface", "Pa"),
    "U_surface_max_m_s": ("Max surface melt speed", "m/s"),
    "U_surface_mean_m_s": ("Mean surface melt speed", "m/s"),
    "surface_flow_direction": ("+1 surface flow all outward from the hottest point, -1 all inward", "-"),
    "x_mm": ("Position along the track", "mm"),
    "y_mm": ("Distance from the track centreline (half model, y >= 0)", "mm"),
    "z_mm": ("Height (top surface z = 0, negative into the part)", "mm"),
    "solidification_time_s": ("Time the location solidified", "s"),
    "cooling_rate_K_s": ("Cooling rate at solidification", "K/s"),
    "G_K_mm": ("Temperature gradient magnitude at solidification", "K/mm"),
    "R_mm_s": ("Solidification rate (interface speed)", "mm/s"),
    "G_over_R_Ks_mm2": ("G/R (morphology)", "K s/mm^2"),
    "GR_K_s": ("G*R (= cooling rate, scale of microstructure)", "K/s"),
    "laser_on": ("1 while the laser is on (track / time series), 0 after (end crater / cooling)", "-"),
}


G_ACC = 9.81


def liquid_props(case_dir):
    """Liquid properties as the solver uses them (transportProperties):
    rho, mu, beta, dSigmadT, and kappa, Cp of the liquid at the liquidus."""
    import re
    text = (case_dir/"constant"/"transportProperties").read_text()

    def num(key):
        return float(re.search(rf"^{key}\s+(?:\[[^\]]*\]\s+)?([0-9.eE+-]+);", text, re.M).group(1))

    def poly(key, T):
        block = re.search(r"^liquid\s*\{(.*?)\}", text, re.M | re.S).group(1)
        a = [float(x) for x in re.search(rf"{key}\s+\(([^)]*)\)", block).group(1).split()]
        return a[0] + a[1]*T + a[2]*T**2

    body = re.search(r"^thermoPath\s*\((.*?)^\);", text, re.M | re.S).group(1)
    T = [float(x) for x, _ in re.findall(r"\(\s*([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*\)", body)]
    Ts, Tl = min(T), max(T)
    return {"rho": num("rho"), "mu": num("mu"), "beta": num("beta"),
            "dSigmadT": num("dSigmadT"), "k": poly("kappa", Tl), "cp": poly("Cp", Tl),
            "T_sol": Ts}


def dimensionless(m, T_max, width_m, u):
    """Farzadi et al. (2008) Eqs. 14, 15, 17, 18, 20 with L_R = pool radius at
    the top surface (half width), L_B = width/8, dT = T_max - T_sol.
    Arrays allowed; zero where there is no pool."""
    T_max, width_m, u = (np.asarray(a, float) for a in (T_max, width_m, u))
    L_R, L_B = width_m/2, width_m/8
    dT = np.clip(T_max - m["T_sol"], 0, None)
    rho, mu = m["rho"], m["mu"]
    Ma = rho*L_R*dT*abs(m["dSigmadT"])/mu**2
    Gr = G_ACC*m["beta"]*L_B**3*dT*rho**2/mu**2
    with np.errstate(divide="ignore", invalid="ignore"):
        R_SB = np.where(Gr > 0, Ma/Gr, 0.0)
        u_m = np.where(L_R > 0, (abs(m["dSigmadT"])*dT/np.where(L_R > 0, L_R, 1)*np.sqrt(L_R)
                                 /(0.664*np.sqrt(rho*mu)))**(2/3), 0.0)
    return {"Ma": Ma, "Gr": Gr, "R_SB": R_SB,
            "Pe": u*rho*m["cp"]*L_R/m["k"], "Re": rho*u*L_R/mu, "u_m_Farzadi_m_s": u_m}


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
        "dSigmadT_N_mK": i["dSigmadT_N_mK"],
    }


def run_row(s, mg=None):
    q, sol = s["quasi_steady"], s.get("solidification")
    row = {"case": s["case"], **run_inputs(s)}
    row.update({
        "first_melting_s": s["first_melting_s"],
        "fully_liquid_surface_s": s["fully_liquid_surface_s"],
        "laser_off_s": s["laser_off_s"],
        "run_end_s": s.get("run_end_s"),
        "laser_on_at_end": int(s.get("laser_on_at_end", False)),
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
        "bottom_cooling_rate_K_s": get(sol, "pool_bottom_centreline", "cooling_rate_K_s"),
        "bottom_G_K_mm": (get(sol, "pool_bottom_centreline", "G_K_m") or np.nan)*1e-3,
        "bottom_R_mm_s": (get(sol, "pool_bottom_centreline", "R_m_s") or np.nan)*1e3,
        "crater_cooling_rate_median_K_s": get(sol, "crater", "cooling_rate_K_s", "median"),
        "crater_R_median_mm_s": (get(sol, "crater", "R_m_s", "median") or np.nan)*1e3,
    })
    # Marangoni: steady values = mean over snapshots in the quasi-steady window;
    # if no snapshot falls in it (e.g. 9 mm/s: window 0.27-0.44 s, snapshots
    # every 0.25 s), the last snapshot with a pool before the window ends
    if mg is not None:
        lo, hi = s["quasi_steady_window_s"]
        pool = mg[(mg["time_s"] <= hi) & (mg["surface_liquid_area_mm2"] > 0)]
        w = pool[pool["time_s"] >= lo]
        if w.empty:
            w = pool.tail(1)
        row["qs_marangoni_snapshots_s"] = " ".join(f"{t:g}" for t in w["time_s"])
        for k in ("gradT_surface_max_K_mm", "gradT_surface_mean_K_mm", "marangoni_stress_max_Pa",
                  "marangoni_stress_mean_Pa", "U_surface_max_m_s", "U_surface_mean_m_s",
                  "surface_flow_direction", "surface_liquid_area_mm2",
                  "Ma", "Gr", "R_SB", "Pe", "Re", "u_m_Farzadi_m_s"):
            row[f"qs_{k}"] = float(w[k].mean()) if len(w) else np.nan
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
    m = liquid_props(Path(s.get("case_path", ROOT/"cases"/s["case"])))
    d = dimensionless(m, df["T_max_K"], df["width_mm"]*1e-3, df["U_max_m_s"])
    for k in ("Ma", "Gr", "R_SB", "Pe", "Re", "u_m_Farzadi_m_s"):
        df[k] = d[k]
    return df


def marangoni(s, out):
    """Per-snapshot surface Marangoni quantities (export_3d.py) plus Pe/Re
    with the mean surface speed (Farzadi's average velocity u_R)."""
    f = out/"marangoni_snapshots.csv"
    if not f.exists():
        return None
    mg = pd.read_csv(f).drop(columns=["dSigmadT_N_mK"], errors="ignore")
    ts = pd.read_csv(out/"timeseries.csv")
    m = liquid_props(Path(s.get("case_path", ROOT/"cases"/s["case"])))
    T = np.interp(mg["time_s"], ts["time_s"], ts["T_max_K"])
    W = np.interp(mg["time_s"], ts["time_s"], ts["width_full_liq_m"])
    d = dimensionless(m, T, W, mg["U_surface_mean_m_s"])
    for k in ("Ma", "Gr", "R_SB", "Pe", "Re", "u_m_Farzadi_m_s"):
        mg[k] = d[k]
    return mg


def solidification(case_dir, t_off):
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
        "laser_on": (d["ts"] <= t_off).astype(int),
    })


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dt", type=float, default=0.01, help="time-series sampling interval [s]")
    p.add_argument("--out", type=Path, default=ROOT/"results"/"melt_pool_dataset.xlsx")
    args = p.parse_args()

    runs, series, events, marang = [], [], [], []
    for f in sorted((ROOT/"results").glob("*/summary.json")):
        s = json.loads(f.read_text())
        inp = run_inputs(s)
        mg = marangoni(s, f.parent)
        runs.append(run_row(s, mg))
        if mg is not None:
            marang.append(pd.concat([pd.DataFrame([{"case": s["case"], **inp}]*len(mg)), mg], axis=1))
        ts = timeseries(s, f.parent, args.dt)
        series.append(pd.concat([pd.DataFrame([{"case": s["case"], **inp}]*len(ts)), ts], axis=1))
        sol = solidification(Path(s.get("case_path", ROOT/"cases"/s["case"])), s["laser_off_s"])
        if sol is not None:
            events.append(pd.concat([pd.DataFrame([{"case": s["case"], **inp}]*len(sol)), sol], axis=1))
    if not runs:
        raise SystemExit("no results/*/summary.json; run analyze_case.py on each case first")

    sheets = {"runs": pd.DataFrame(runs), "timeseries": pd.concat(series, ignore_index=True)}
    if marang:
        sheets["marangoni"] = pd.concat(marang, ignore_index=True)
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
