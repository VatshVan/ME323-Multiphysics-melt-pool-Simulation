#!/usr/bin/env python3
"""Summary figures for docs/REPORT.md, from results/melt_pool_dataset.xlsx.

    python scripts/report_figures.py           # -> docs/figures/*.png
    python scripts/report_figures.py --areas   # first (re)measure the melted
        cross-section of each run from its fields (needs OpenFOAM: source
        setup/env.sh) -> results/melted_cross_section.csv
"""

import argparse
import sys
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
# categorical slots 1-3 for the three inputs of the sensitivity chart
INPUT_COLOR = {"absorbed power P": "#2a78d6", "scan speed v": "#eb6834", "beam radius r": "#1baf7a"}
# melted enthalpy per kg, 293 K -> liquidus: solid cp fit (Ghosh 2018) + Lf (Yan 2022)
# + 50 K mushy interval at the liquid cp (Much 2024)
H_MELT = 427.91*(1878 - 293.15) + 0.39895/2*(1878**2 - 293.15**2) + 2.9e5 + 1130*50
RHO = 4428.0
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


def measure_areas(runs):
    """Melted track cross-section [mm^2]: the current pool (liquid fraction
    > 0.5) projected onto the y-z plane at a write time while the laser is on
    and the pool is steady; mirrored to the full width."""
    sys.path.insert(0, str(ROOT/"scripts"))
    import export_3d
    rows = []
    for case, r in runs.iterrows():
        t = max(t for t in (0.25, 0.5, 0.75) if t <= r.laser_off_s)
        half = export_3d.half_mesh(ROOT/"cases"/case, f"{t:g}")
        cc = half.cell_centers().points*1e3
        liq = (1.0 - half.cell_data["alpha.solid"]) > 0.5
        dy = r.cell_size_um*1e-3
        yz = np.unique(np.floor(cc[liq][:, 1:]/dy).astype(int), axis=0)
        rows.append({"case": case, "time_s": t, "melted_area_mm2": round(2*len(yz)*dy**2, 4)})
    pd.DataFrame(rows).to_csv(ROOT/"results"/"melted_cross_section.csv", index=False, lineterminator="\n")


def melting_efficiency(runs):
    """Fraction of the absorbed power that ends up as heat in the melted
    track: rho v A H_melt / P_abs."""
    a = pd.read_csv(ROOT/"results"/"melted_cross_section.csv").set_index("case")
    runs = runs.join(a)
    runs["eta_melt"] = RHO*runs.scan_speed_mm_s*1e-3*runs.melted_area_mm2*1e-6*H_MELT/runs.absorbed_power_W
    return runs


def sensitivities(ma):
    """Least-squares fit y = C P^a v^b r^c over the Marangoni runs."""
    X = np.column_stack([np.ones(len(ma)), np.log(ma.absorbed_power_W),
                         np.log(ma.scan_speed_mm_s), np.log(ma.beam_radius_mm)])
    out = {}
    for col, lab in [("qs_depth_mm", "depth"), ("qs_width_mm", "width"), ("qs_T_max_K", "peak T"),
                     ("qs_U_max_m_s", "peak speed"), ("cooling_rate_median_K_s", "cooling rate"),
                     ("G_over_R_median_Ks_mm2", "G/R")]:
        y = np.log(ma[col])
        b = np.linalg.lstsq(X, y, rcond=None)[0]
        r2 = 1 - np.sum((y - X@b)**2)/np.sum((y - y.mean())**2)
        out[lab] = (*b[1:], r2)
    return out


def fig_sensitivity(ma):
    sens = sensitivities(ma)
    labels = list(sens)
    fig, ax = plt.subplots(figsize=(10, 4))
    x = np.arange(len(labels))
    w = 0.26
    for i, name in enumerate(INPUT_COLOR):
        ax.bar(x + (i - 1)*(w + 0.02), [sens[l][i] for l in labels], w, color=INPUT_COLOR[name], label=name)
    ax.axhline(0, color=MUTED, linewidth=1)
    ax.set_xticks(x, [f"{l}\n(R² = {sens[l][3]:.3f})" for l in labels])
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("exponent in  y ∝ P^a v^b r^c")
    ax.legend(loc="upper left", ncol=3)
    ax.set_title("Power-law sensitivity of each output to each input (12 Marangoni runs)")
    fig.tight_layout()
    fig.savefig(OUT/"sensitivity_exponents.png", dpi=150)


def fig_efficiency(runs):
    fig, axs = plt.subplots(1, 2, figsize=(10, 4))
    ma = runs[runs.dSigmadT_N_mK != 0]
    no = runs[runs.dSigmadT_N_mK == 0]
    by_speed(axs[0], ma, "line_energy_J_mm", "melted_area_mm2")
    axs[0].scatter(no.line_energy_J_mm, no.melted_area_mm2, s=55, color=NOMA, edgecolor="#fcfcfb",
                   linewidth=1.5, label="without Marangoni", zorder=3)
    for name, r in no.iterrows():
        axs[0].annotate(name, (r.line_energy_J_mm, r.melted_area_mm2), xytext=(5, 3),
                        textcoords="offset points", fontsize=7.5, color=MUTED)
    axs[0].set(xlabel="line energy P_abs / v  [J/mm]", ylabel="melted cross-section [mm²]",
               title="Melted track cross-section")
    axs[0].set_ylim(bottom=0)
    axs[0].legend(loc="upper left", fontsize=8)
    by_speed(axs[1], ma, "scan_speed_mm_s", "eta_melt", label_runs=False)
    axs[1].scatter(no.scan_speed_mm_s, no.eta_melt, s=55, color=NOMA, edgecolor="#fcfcfb",
                   linewidth=1.5, zorder=3)
    for name, r in no.iterrows():
        axs[1].annotate(name, (r.scan_speed_mm_s, r.eta_melt), xytext=(6, -3),
                        textcoords="offset points", fontsize=7.5, color=MUTED)
    axs[1].set(xlabel="scan speed [mm/s]", ylabel="melting efficiency  ρ v A H / P_abs",
               title="Share of absorbed power used for melting", xticks=[4, 6, 8, 10])
    axs[1].set_ylim(0, 0.3)
    fig.tight_layout()
    fig.savefig(OUT/"melting_efficiency.png", dpi=150)


def fig_ma_gr(ma):
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    by_speed(ax, ma, "qs_width_mm", "qs_R_SB", label_runs=False)
    w = np.linspace(2.4, 5.4, 20)
    k = np.exp(np.mean(np.log(ma.qs_R_SB) + 2*np.log(ma.qs_width_mm)))
    ax.plot(w, k/w**2, color=MUTED, linestyle="--", linewidth=1, zorder=1)
    ax.text(3.3, k/3.3**2*1.15, "Ma/Gr ∝ width⁻²", color=MUTED, fontsize=8)
    ax.set(xscale="log", yscale="log", xlabel="pool full width [mm]",
           ylabel="Ma / Gr  (surface tension / buoyancy)",
           title="Marangoni dominance falls with pool size")
    ax.set_xticks([2.5, 3, 4, 5], ["2.5", "3", "4", "5"])
    ax.set_yticks([300, 500, 1000, 1500], ["300", "500", "1000", "1500"])
    ax.minorticks_off()
    ax.legend(title="scan speed", loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT/"ma_gr_vs_width.png", dpi=150)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--areas", action="store_true", help="re-measure melted cross-sections from the case fields")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    runs, ma, ts = load()
    if args.areas or not (ROOT/"results"/"melted_cross_section.csv").exists():
        measure_areas(runs)
    runs = melting_efficiency(runs)
    fig_sensitivity(ma)
    fig_efficiency(runs)
    fig_ma_gr(ma)
    fig_pool(ma)
    fig_speed(ma)
    fig_pairs(runs)
    fig_history(ts)
    fig_solidification(runs)
    print("figures ->", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
