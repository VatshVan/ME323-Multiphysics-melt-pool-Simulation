#!/usr/bin/env python3
"""Driving-force check: is all melt flow caused by the Marangoni and buoyancy
terms, or does the solver create flow by itself?

Three short runs of the R02 settings (500 W absorbed, 4 mm/s, r = 0.75 mm)
to t = 0.05 s, identical except for the two driving forces:
    A_marangoni_buoyancy   dSigma/dT = -2.6e-4, beta = 1.6e-4  (normal model)
    B_buoyancy_only        dSigma/dT = 0,       beta = 1.6e-4
    C_no_driving_force     dSigma/dT = 0,       beta = 0
With neither force (C) the velocity must stay at round-off level.

Build and run (OpenFOAM environment loaded):
    python scripts/make_cases.py --only R02 R02_noMa --cases-dir ~/run/check
    (rename to A/B, copy B to C with beta = 0, endTime 0.05, writeInterval 0.025,
     p_rgh maxIter 50 so the pressure solver does not spin on a zero field)
Then:
    python scripts/buoyancy_check.py ~/run/check     # -> results/buoyancy_check/
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"results"/"buoyancy_check"
CASES = [("A_marangoni_buoyancy", "A: Marangoni + buoyancy", "#2a78d6"),
         ("B_buoyancy_only", "B: buoyancy only", "#eb6834"),
         ("C_no_driving_force", "C: no Marangoni, no buoyancy", "#1baf7a")]


def series(case, name):
    f = next((case/"postProcessing"/name).glob("*/*.dat"))
    d = np.loadtxt(f, comments="#")
    return d[:, 0], d[:, 1]


def pool(case):
    d = np.loadtxt(case/"postProcessing"/"meltPoolDimensions"/"1928.csv", delimiter=",", skiprows=1)
    return d[:, 0], d[:, 3]*1e3, 2*d[:, 2]*1e3


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("check_dir", type=Path)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    fig, axs = plt.subplots(1, 3, figsize=(15, 4.2))
    rows = []
    for name, label, color in CASES:
        case = args.check_dir/name
        t, U = series(case, "Umax")
        tT, T = series(case, "Tmax")
        tp, depth, width = pool(case)
        axs[0].semilogy(t*1e3, np.maximum(U, 1e-20), color=color, label=label)
        axs[1].plot(tT*1e3, T, color=color, label=label)
        axs[2].plot(tp*1e3, depth, color=color, label=label)
        rows.append((label, U[-1], T[-1], depth[-1], width[-1]))
    axs[0].set(xlabel="time [ms]", ylabel="peak melt speed [m/s] (log scale)",
               title="Peak melt speed", ylim=(1e-20, 10))
    axs[0].axhspan(1e-20, 1e-12, color="#e4e3df", zorder=0)
    axs[0].text(2, 1e-15, "round-off level (zero)", color="#52514e", fontsize=8)
    axs[1].axhline(1928, color="#52514e", linestyle=":", linewidth=1)
    axs[1].set(xlabel="time [ms]", ylabel="peak temperature [K]", title="Peak temperature")
    axs[2].set(xlabel="time [ms]", ylabel="pool depth at liquidus [mm]", title="Pool depth")
    axs[0].legend(fontsize=8, loc="center right")
    fig.suptitle("Driving-force check, R02 settings (500 W absorbed, 4 mm/s, r = 0.75 mm): "
                 "flow exists only when a driving force is present", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT/"driving_force_check.png", dpi=150)

    lines = ["| Case | Peak melt speed at 0.05 s (m/s) | Peak T (K) | Depth (mm) | Width (mm) |",
             "|---|---|---|---|---|"]
    lines += [f"| {l} | {u:.2e} | {T:.0f} | {d:.2f} | {w:.2f} |" for l, u, T, d, w in rows]
    (OUT/"summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))

    # 2D contours and velocity profiles of each case at 0.025 and 0.05 s
    for name, _, _ in CASES:
        case = args.check_dir/name
        subprocess.run([sys.executable, str(ROOT/"scripts"/"analyze_case.py"), str(case),
                        "--sections-only"], check=True, capture_output=True)
        src = ROOT/"results"/f"{case.parent.name}_{name}"
        dst = OUT/name
        if dst.exists():
            shutil.rmtree(dst)
        src.rename(dst)
    print(f"-> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
