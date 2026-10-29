#!/usr/bin/env python3
"""Order-of-magnitude checks before running AdditiveFOAM.

1. Rosenthal moving point source (conduction only, no latent heat, no
   Marangoni flow) -> melt-pool width/depth/length for a range of absorbed
   powers, and how many cells of each mesh-study size span the pool.
2. Marangoni surface-velocity scale, Farzadi et al. (2008) Eq. 20:
       u_max = [ |dSigma/dT| (dT/dR) R^0.5 / (0.664 sqrt(rho mu)) ]^(2/3)
3. Peclet and Marangoni numbers (Farzadi Eqs. 14, 17).

Rosenthal is only a sizing estimate: real pools with Marangoni flow
(dSigma/dT < 0) come out wider and shallower.

Usage:  python scripts/estimate_pool.py
"""

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
    cfg = json.loads((ROOT/"config"/"baseline.json").read_text())
    m = material(cfg)
    las, bc = cfg["laser"], cfg["thermal_bc"]
    v = las["speed"]["value"]
    T0 = bc["T_initial"]["value"]
    sizes = cfg["mesh_study"]["cell_sizes"]["value"]
    q_cfg = las["power"]["value"]*las["absorptivity"]["value"]

    print(f"Material {cfg['material']['file']}: k_s={m['k_s']:.1f} W/mK, cp={m['cp']:.0f} J/kgK, "
          f"T_liq={m['T_liq']} K, scan speed {v*1e3:g} mm/s\n")
    print("Rosenthal (conduction only)      full width  depth   length  "
          + "  ".join(f"depth/{d*1e6:g}um" for d in sizes))
    for q in sorted({50, 100, 250, 500, 1000, 1500, 2000, q_cfg}):
        w, d, L = rosenthal_pool(q, v, m["k_s"], m["rho"], m["cp"], m["T_liq"], T0)
        tag = "  <- config" if q == q_cfg else ""
        cells = "  ".join(f"{d/dx:11.1f}" for dx in sizes)
        print(f"  absorbed {q:6.0f} W             {w*1e3:7.2f} mm {d*1e3:5.2f} mm "
              f"{L*1e3:6.2f} mm {cells}{tag}")

    w, d, _ = rosenthal_pool(q_cfg, v, m["k_s"], m["rho"], m["cp"], m["T_liq"], T0)
    if w > 0:
        R = w/2
        dT = 2.0*m["T_liq"] - m["T_liq"]   # assume peak ~2x liquidus (rough)
        u = (abs(m["dSigmadT"])*(dT/R)*R**0.5/(0.664*np.sqrt(m["rho"]*m["mu"])))**(2/3)
        alpha_l = m["k_l"]/(m["rho"]*m["cp"])
        Pe = u*R/alpha_l
        Ma = m["rho"]*R*dT*abs(m["dSigmadT"])/m["mu"]**2
        print(f"\nConfig case (absorbed {q_cfg:g} W): pool radius ~{R*1e3:.2f} mm")
        print(f"  Marangoni velocity scale (Farzadi Eq. 20): ~{u:.2f} m/s")
        print(f"  Peclet number ~{Pe:.0f}  (>>1: convection dominates heat transport)")
        print(f"  Marangoni number ~{Ma:.2e}")
        for dx in sizes:
            dt = cfg["numerics"]["maxCo"]["value"]*dx/u
            print(f"  {dx*1e6:5.0f} um mesh: Courant-limited dt ~{dt:.1e} s, "
                  f"~{las['cooling_time']['value']/dt + (las['x_end']['value']-las['x_start']['value'])/v/dt:,.0f} steps")


if __name__ == "__main__":
    main()
