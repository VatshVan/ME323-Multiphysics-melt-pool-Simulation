#!/usr/bin/env python3
"""Summary figures for docs/REPORT.md, from results/melt_pool_dataset.xlsx.

    python scripts/report_figures.py        # -> docs/figures/*.png
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"docs"/"figures"

# ordinal blue ramp for scan speed, blue/orange for with/without Marangoni
SPEED_COLOR = {4: "#86b6ef", 6: "#3987e5", 8: "#1c5cab", 10: "#0d366b"}
SPEED_MARKER = {4: "o", 6: "s", 8: "^", 10: "D"}
MA, NOMA = "#2a78d6", "#eb6834"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
PAIRS = ["R02", "R06", "R11"]
# label offsets (points) where run names would overlap
NUDGE = {"R07": (5, -10), "R08": (6, 2), "R11": (-22, 5), "R02_noMa": (-48, 6),
         "R09": (-12, 7), "R12": (6, 4), "R06_noMa": (6, -9)}

plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.8, "axes.spines.top": False,
    "axes.spines.right": False, "font.size": 10, "lines.linewidth": 2,
    "legend.frameon": False,
})


def load():
    x = pd.read_excel(ROOT/"results"/"melt_pool_dataset.xlsx", sheet_name=None)
    runs = x["runs"].set_index("case")
    ma = runs[runs.dSigmadT_N_mK != 0]
    return runs, ma, x["timeseries"]


def by_speed(ax, ma, xcol, ycol, label_runs=True):
    for v, g in ma.groupby("scan_speed_mm_s"):
        ax.scatter(g[xcol], g[ycol], s=55, color=SPEED_COLOR[v], marker=SPEED_MARKER[v],
                   edgecolor="#fcfcfb", linewidth=1.5, label=f"{v} mm/s", zorder=3)
        if label_runs:
            for name, r in g.iterrows():
                ax.annotate(name, (r[xcol], r[ycol]), xytext=NUDGE.get(name, (5, 3)), textcoords="offset points",
                            fontsize=7.5, color=MUTED)


def fig_pool(ma):
    fig, axs = plt.subplots(1, 2, figsize=(10, 4))
    by_speed(axs[0], ma, "line_energy_J_mm", "qs_depth_mm")
    by_speed(axs[1], ma, "line_energy_J_mm", "qs_width_mm")
    axs[0].set(xlabel="line energy P_abs / v  [J/mm]", ylabel="pool depth [mm]", title="Depth")
    axs[1].set(xlabel="line energy P_abs / v  [J/mm]", ylabel="pool full width [mm]", title="Width")
    axs[0].set_ylim(bottom=0); axs[1].set_ylim(bottom=0)
    axs[1].legend(title="scan speed", loc="lower right")
    fig.suptitle("Quasi-steady melt-pool size vs line energy (with Marangoni flow)")
    fig.tight_layout()
    fig.savefig(OUT/"pool_size_vs_line_energy.png", dpi=150)


def fig_speed(ma):
    fig, axs = plt.subplots(1, 3, figsize=(12, 3.8))
    for ax, col, lab in zip(axs, ["qs_T_max_K", "qs_marangoni_stress_max_Pa", "cooling_rate_median_K_s"],
                            ["peak temperature [K]", "max Marangoni shear stress [Pa]",
                             "median cooling rate along track [K/s]"]):
        by_speed(ax, ma, "scan_speed_mm_s", col, label_runs=False)
        ax.set(xlabel="scan speed [mm/s]", ylabel=lab, xticks=[4, 6, 8, 10])
    axs[0].axhline(3533, color=MUTED, linestyle="--", linewidth=1)
    axs[0].text(4, 3490, "boiling point 3533 K", color=MUTED, fontsize=8, va="top")
    axs[0].axhline(1928, color=MUTED, linestyle=":", linewidth=1)
    axs[0].text(4, 1970, "liquidus 1928 K", color=MUTED, fontsize=8)
    axs[0].set_ylim(1800, 3700)
    axs[2].set_ylim(bottom=0)
    axs[2].legend(title="scan speed", loc="lower right", fontsize=8)
    fig.suptitle("Effect of scan speed (each point one run; 300-800 W absorbed)")
    fig.tight_layout()
    fig.savefig(OUT/"speed_effects.png", dpi=150)


def fig_pairs(runs):
    metrics = [("qs_depth_mm", "depth [mm]"), ("qs_width_mm", "full width [mm]"),
               ("qs_T_max_K", "peak temperature [K]"), ("qs_U_max_m_s", "peak melt speed [m/s]")]
    fig, axs = plt.subplots(1, 4, figsize=(13, 3.6))
    x = np.arange(len(PAIRS))
    w = 0.38
    for ax, (col, lab) in zip(axs, metrics):
        a = [runs.loc[p, col] for p in PAIRS]
        b = [runs.loc[p + "_noMa", col] for p in PAIRS]
        ax.bar(x - w/2 - 0.01, a, w, color=MA, label="with Marangoni")
        ax.bar(x + w/2 + 0.01, b, w, color=NOMA, label="without (dσ/dT = 0)")
        ax.set(xticks=x, xticklabels=PAIRS, title=lab)
        ax.grid(axis="x", visible=False)
    axs[2].axhline(3533, color=MUTED, linestyle="--", linewidth=1)
    axs[2].text(-0.45, 3600, "boiling 3533 K", color=MUTED, fontsize=8)
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=2)
    fig.suptitle("Marangoni flow on vs off (same laser settings)")
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(OUT/"marangoni_on_off.png", dpi=150)


def fig_history(ts):
    fig, axs = plt.subplots(3, 1, figsize=(8, 7.5), sharex=True)
    for name, color, lab in [("R02", MA, "R02 with Marangoni"), ("R02_noMa", NOMA, "R02 without Marangoni")]:
        g = ts[ts.case == name]
        axs[0].plot(g.time_s, g.T_max_K, color=color, label=lab)
        axs[1].plot(g.time_s, g.depth_mm, color=color)
        axs[2].plot(g.time_s, g.width_mm, color=color)
    for ax, lab in zip(axs, ["peak T [K]", "pool depth [mm]", "pool full width [mm]"]):
        ax.set_ylabel(lab)
        ax.axvline(1.0, color=MUTED, linestyle="--", linewidth=1)
    axs[0].text(1.01, 4600, "laser off", color=MUTED, fontsize=8)
    axs[0].legend(loc="center right")
    axs[2].set_xlabel("time [s]")
    fig.suptitle("Time history, R02 (4 mm/s, 500 W absorbed, r = 0.75 mm)")
    fig.tight_layout()
    fig.savefig(OUT/"history_R02_on_off.png", dpi=150)


def fig_solidification(runs):
    fig, ax = plt.subplots(figsize=(7, 5))
    R = np.linspace(0.5, 4.5, 50)
    for gr in (200, 400, 800):
        ax.plot(R, gr*R, color="#c9c8c2", linewidth=1.2, zorder=1)
        ax.text(640/gr + 0.04, 640, f"G/R = {gr} K·s/mm²", color=MUTED, fontsize=8, va="center")
    for noma, color, lab in [(False, MA, "with Marangoni"), (True, NOMA, "without Marangoni")]:
        g = runs[(runs.dSigmadT_N_mK == 0) == noma]
        ax.scatter(g.R_median_mm_s, g.G_median_K_mm, s=55, color=color, edgecolor="#fcfcfb",
                   linewidth=1.5, label=lab, zorder=3)
        for name, r in g.iterrows():
            ax.annotate(name, (r.R_median_mm_s, r.G_median_K_mm), xytext=NUDGE.get(name, (5, 3)),
                        textcoords="offset points", fontsize=7.5, color=MUTED)
    ax.set(xlabel="solidification rate R [mm/s]",
           ylabel="temperature gradient G [K/mm]",
           title="Solidification map (median over the track, laser on)")
    ax.set_xlim(0.5, 4.5); ax.set_ylim(600, 1150)
    ax.legend(loc="lower center", bbox_to_anchor=(0.55, 0.12))
    fig.tight_layout()
    fig.savefig(OUT/"solidification_map.png", dpi=150)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    runs, ma, ts = load()
    fig_pool(ma)
    fig_speed(ma)
    fig_pairs(runs)
    fig_history(ts)
    fig_solidification(runs)
    print("figures ->", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
