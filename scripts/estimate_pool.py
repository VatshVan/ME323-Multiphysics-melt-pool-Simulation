#!/usr/bin/env python3
"""Order-of-magnitude checks before running AdditiveFOAM.

1. Rosenthal moving point source (conduction only, no latent heat, no
   Marangoni flow) -> melt-pool width/depth/length for every run in the run
   table, with warnings if a setting will not melt, if the pool may leave the
   fine region, or if end_time is shorter than the track.
2. Marangoni surface-velocity scale, Farzadi et al. (2008) Eq. 20:
       u_max = [ |dSigma/dT| (dT/dR) R^0.5 / (0.664 sqrt(rho mu)) ]^(2/3)
3. Peclet and Marangoni numbers (Farzadi Eqs. 14, 17).

Rosenthal is only a sizing estimate: real pools with Marangoni flow
(dSigma/dT < 0) come out wider and shallower.

Usage:
    python scripts/estimate_pool.py                 # every run in config/baseline.json
    python scripts/estimate_pool.py --only R02 V1   # selected runs
"""

import argparse
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def material(cfg):
    """Constant properties for the estimates. Polynomial k and Cp are
    evaluated at the mean solid temperature (T0 + T_sol)/2 for the solid and
    at T_liq for the liquid."""
    text = (ROOT/cfg["material"]["file"]).read_text()

    def scalar(key):
        return float(re.search(rf"^{key}\s+(?:\[[^\]]*\]\s+)?([0-9.eE+-]+);", text, re.M).group(1))

    def poly(phase, key, T):
        block = re.search(rf"^{phase}\s*\{{(.*?)\}}", text, re.M | re.S).group(1)
        a = re.search(rf"{key}\s+\(\s*([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)", block).groups()
        return float(a[0]) + float(a[1])*T + float(a[2])*T**2

    path = re.findall(r"\(\s*([0-9.eE+-]+)\s+([01])\s*\)", text)
    temps = {int(a): float(T) for T, a in path}
    T_s = 0.5*(cfg["thermal_bc"]["T_initial"]["value"] + temps[1])
    return {
        "k_s": poly("solid", "kappa", T_s), "k_l": poly("liquid", "kappa", temps[0]),
        "cp": poly("solid", "Cp", T_s), "rho": scalar("rho"), "mu": scalar("mu"),
        "dSigmadT": scalar("dSigmadT"), "T_sol": temps[1], "T_liq": temps[0],
    }


def rosenthal_pool(q, v, k, rho, cp, Tm, T0):
    a = k/(rho*cp)
    x = np.linspace(-20e-3, 4e-3, 4801)
    y = np.linspace(1e-7, 8e-3, 1601)
    X, Y = np.meshgrid(x, y)
    R = np.hypot(X, Y)
    T = T0 + q/(2*np.pi*k*R)*np.exp(-v*(X + R)/(2*a))
    melt = T >= Tm
    if not melt.any():
        return 0.0, 0.0, 0.0
    half_width = Y[melt].max()          # point source: depth == half width
    return 2*half_width, half_width, X[melt].max() - X[melt].min()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=ROOT/"config"/"baseline.json")
    ap.add_argument("--only", nargs="+", metavar="NAME", help="only these runs (by name)")
    args = ap.parse_args()
    cfg = json.loads(args.config.read_text())
    m = material(cfg)
    las, bc, geo = cfg["laser"], cfg["thermal_bc"], cfg["geometry"]
    T0 = bc["T_initial"]["value"]
    dx = cfg["mesh"]["cell_size"]["value"]
    track = las["x_end"]["value"] - las["x_start"]["value"]
    runs = [r for r in cfg["runs"]["value"] if not args.only or r["name"] in args.only]

    print(f"Material {cfg['material']['file']}: k_s={m['k_s']:.1f} W/mK, cp={m['cp']:.0f} J/kgK, "
          f"T_liq={m['T_liq']} K; fine region {geo['roi_y']['value']*1e3:g} mm half width, "
          f"{geo['roi_z']['value']*1e3:g} mm deep, cells {dx*1e6:g} um\n")
    print("Rosenthal is conduction only: with Marangoni flow (dSigma/dT < 0) real pools come out\n"
          "wider and shallower. Use it to see whether a setting melts and fits, not as a result.\n")
    print(f"{'run':10s} {'v mm/s':>6s} {'P_abs W':>8s} {'q0 W/mm2':>9s} {'width mm':>9s} {'depth mm':>9s} "
          f"{'length mm':>9s} {'laser-on s':>10s}  simulated width/depth (if run)")
    for r in runs:
        v, q = r["speed"], r["laser_power"]*r["absorptivity"]
        q0 = 2*q/(np.pi*r["radius"]**2)*1e-6          # peak intensity of the Gaussian, W/mm^2
        w, d, L = rosenthal_pool(q, v, m["k_s"], m["rho"], m["cp"], m["T_liq"], T0)
        notes = []
        if w == 0:
            notes.append("NO MELTING expected")
        if w/2 > geo["roi_y"]["value"] or d > geo["roi_z"]["value"]:
            notes.append("pool may leave the fine region")
        if track/v > cfg["numerics"]["end_time"]["value"]:
            notes.append("end_time shorter than the track")
        sim = ROOT/"results"/r["name"]/"summary.json"
        if sim.exists():
            qs = json.loads(sim.read_text()).get("quasi_steady", {})
            if "pool_width_full_mm" in qs:
                notes.insert(0, f"{qs['pool_width_full_mm']['mean']:.2f} / {qs['pool_depth_mm']['mean']:.2f} mm")
        print(f"{r['name']:10s} {v*1e3:6.1f} {q:8.0f} {q0:9.0f} {w*1e3:9.2f} {d*1e3:9.2f} "
              f"{L*1e3:9.2f} {track/v:10.2f}  {'; '.join(notes)}")

    print("\nMarangoni velocity scale (Farzadi Eq. 20, peak T taken as 2 x liquidus):")
    for r in runs:
        w, _, _ = rosenthal_pool(r["laser_power"]*r["absorptivity"], r["speed"], m["k_s"], m["rho"],
                                 m["cp"], m["T_liq"], T0)
        if w == 0:
            continue
        R, dT = w/2, m["T_liq"]
        u = (abs(m["dSigmadT"])*(dT/R)*R**0.5/(0.664*np.sqrt(m["rho"]*m["mu"])))**(2/3)
        dt = cfg["numerics"]["maxCo"]["value"]*dx/u
        print(f"  {r['name']:10s} u ~ {u:.2f} m/s, Pe ~ {u*R/(m['k_l']/(m['rho']*m['cp'])):.0f}, "
              f"Courant-limited dt ~ {dt:.1e} s")


if __name__ == "__main__":
    main()
