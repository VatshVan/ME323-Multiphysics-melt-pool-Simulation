#!/usr/bin/env python3
"""Figures and tables for the uniform-beam study (the U* runs) in docs/REPORT.md.

18 runs: absorbed 350/700 W (1000/2000 W at absorptivity 0.35), 3/6/9 mm/s,
3 mm uniform beam, each with three sets of driving forces:
    MaB   Marangoni + buoyancy  (dSigma/dT = -2.6e-4, beta = 1.6e-4)
    B     buoyancy only         (dSigma/dT = 0)
    none  neither               (dSigma/dT = 0, beta = 0, conduction only)

Reads results/U*/summary.json, results/U*/timeseries.csv,
results/U*/marangoni_snapshots.csv, cases/U*/postProcessing/sections/ and
cases/U*/solidificationData/. Writes docs/figures/ta/*.png,
results/ta_summary.csv (one row per run) and results/ta_fits.csv (power laws).

    python scripts/ta_figures.py
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"docs"/"figures"/"ta"
sys.path.insert(0, str(ROOT/"scripts"))
from analyze_case import arrows, read_raw  # noqa: E402

POWERS = (1000, 2000)
SPEEDS = (3, 6, 9)
MODES = ("MaB", "B", "none")
LABEL = {"MaB": "Marangoni + buoyancy", "B": "buoyancy only", "none": "neither (conduction)"}
COLOR = {"MaB": "#2a78d6", "B": "#eb6834", "none": "#1baf7a"}
MARK = {1000: "o", 2000: "s"}
LINE = {1000: "--", 2000: "-"}
INK, MUTED, GRID, BG = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
TS, TL, T_BOIL = 1878.0, 1928.0, 3533.0
RHO, CP_L, K_L, MU, DSDT, BETA, G0 = 4428.0, 1130.0, 28.2, 3.5e-3, 2.6e-4, 1.6e-4, 9.81
# melted enthalpy per kg, 293 K -> liquidus (same as report_figures.py)
H_MELT = 427.91*(1878 - 293.15) + 0.39895/2*(1878**2 - 293.15**2) + 2.9e5 + 1130*50
# section time per speed: the last write with the laser on and the pool steady
T_SEC = {3: 1.0, 6: 0.5, 9: 0.25}
X_SLAB = 10.05          # mm, mid-track cell layer for the fusion-zone cross-section

plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "axes.edgecolor": MUTED,
    "axes.labelcolor": INK, "text.color": INK, "xtick.color": MUTED,
    "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 10, "lines.linewidth": 2, "legend.frameon": False,
})


def name(P, v, m):
    return f"U{P}_v{v}_{m}"


def events(case):
    f = ROOT/"cases"/case/"solidificationData"/"solidification-data.csv"
    d = np.atleast_2d(np.loadtxt(f, delimiter=",", skiprows=1))
    return pd.DataFrame({"x": d[:, 0]*1e3, "y": d[:, 1]*1e3, "z": d[:, 2]*1e3, "t": d[:, 3],
                         "cr": d[:, 4], "G": np.linalg.norm(d[:, 5:8], axis=1)*1e-3,
                         "R": d[:, 8]*1e3})


def fusion_zone(ev, dx=0.1):
    """Cells of the mid-track layer x = X_SLAB that melted and solidified."""
    s = ev[np.abs(ev.x - X_SLAB) < dx/2]
    return s[["y", "z"]].drop_duplicates()


def load():
    rows, ts, ma, ev = [], {}, {}, {}
    for P in POWERS:
        for v in SPEEDS:
            for m in MODES:
                c = name(P, v, m)
                f = ROOT/"results"/c/"summary.json"
                if not f.exists():
                    continue
                s = json.loads(f.read_text())
                q, so = s["quasi_steady"], s["solidification"]
                ts[c] = pd.read_csv(ROOT/"results"/c/"timeseries.csv")
                mf = ROOT/"results"/c/"marangoni_snapshots.csv"
                ma[c] = pd.read_csv(mf) if mf.exists() else None
                ev[c] = events(c)
                fz = fusion_zone(ev[c])
                area = 2*len(fz)*0.01                                   # mm^2, full width
                on = ev[c][ev[c].t <= s["laser_off_s"]]
                bottom = on[(on.y < 0.1) & (np.abs(on.x - X_SLAB) < 1.0)]
                bottom = bottom[bottom.z <= bottom.z.min() + 1e-6]
                top = on[(on.z > -0.1) & (np.abs(on.x - X_SLAB) < 1.0) & (on.y < 0.1)]
                d, w, L = (q["pool_depth_mm"]["mean"], q["pool_width_full_mm"]["mean"],
                           q["pool_length_mm"]["mean"])
                Tm, Um = q["T_max_K"]["mean"], q["U_max_m_s"]["mean"]
                Pabs = s["inputs"]["absorbed_power_W"]
                vv = v*1e-3
                dT = Tm - TS
                row = dict(
                    case=c, power_W=P, absorbed_W=Pabs, speed_mm_s=v, mode=m,
                    line_energy_J_mm=Pabs/v,
                    first_melting_ms=s["first_melting_s"]*1e3,
                    solidified_s=s["pool_fully_solidified_s"],
                    laser_off_s=s["laser_off_s"],
                    depth_mm=d, width_mm=w, length_mm=L, aspect_w_d=w/d,
                    depth_sd=q["pool_depth_mm"]["std"], width_sd=q["pool_width_full_mm"]["std"],
                    T_max_K=Tm, T_peak_K=s["peak_T_K"], superheat_K=Tm - TL,
                    U_max_m_s=Um, U_peak_m_s=s["peak_U_m_s"],
                    fz_area_mm2=area, fz_depth_mm=-fz.z.min() + 0.05 if len(fz) else np.nan,
                    fz_width_mm=2*(fz.y.max() + 0.05) if len(fz) else np.nan,
                    eta_melt=RHO*vv*area*1e-6*H_MELT/Pabs,
                    n_events=so["n_events"],
                    cr_med=so["cooling_rate_K_s"]["median"],
                    cr_p10=so["cooling_rate_K_s"]["p10"], cr_p90=so["cooling_rate_K_s"]["p90"],
                    G_med=so["G_K_m"]["median"]*1e-3, G_p10=so["G_K_m"]["p10"]*1e-3,
                    G_p90=so["G_K_m"]["p90"]*1e-3,
                    R_med=so["R_m_s"]["median"]*1e3, R_p10=so["R_m_s"]["p10"]*1e3,
                    R_p90=so["R_m_s"]["p90"]*1e3,
                    GR_med=so["G_over_R_Ks_m2"]["median"]*1e-6,
                    bottom_G=bottom.G.mean(), bottom_R=bottom.R.mean(),
                    bottom_cr=bottom.cr.mean(),
                    top_G=top.G.median() if len(top) else np.nan,
                    top_R=top.R.median() if len(top) else np.nan,
                    crater_cr=so["crater"]["cooling_rate_K_s"]["median"] if so.get("crater") else np.nan,
                    crater_R=so["crater"]["R_m_s"]["median"]*1e3 if so.get("crater") else np.nan,
                    crater_G=so["crater"]["G_K_m"]["median"]*1e-3 if so.get("crater") else np.nan,
                )
                # dimensionless groups (Farzadi 2008 Eqs. 15, 17), half width as L_R,
                # w/8 for buoyancy
                LR = w/2*1e-3
                row["Ma"] = RHO*LR*dT*DSDT/MU**2
                row["Gr"] = G0*BETA*(w/8*1e-3)**3*dT*RHO**2/MU**2
                row["Ma_over_Gr"] = row["Ma"]/row["Gr"]
                row["Pe_scan"] = vv*RHO*CP_L*1.5e-3/K_L      # scan speed against diffusion over r
                if ma[c] is not None and len(ma[c]):
                    on_m = ma[c][ma[c].laser_on == 1]
                    last = on_m.iloc[-1] if len(on_m) else ma[c].iloc[0]
                    row.update(gradT_max_K_mm=last.gradT_surface_max_K_mm,
                               gradT_mean_K_mm=last.gradT_surface_mean_K_mm,
                               stress_max_Pa=last.marangoni_stress_max_Pa,
                               Us_max=last.U_surface_max_m_s, Us_mean=last.U_surface_mean_m_s,
                               surf_area_mm2=last.surface_liquid_area_mm2,
                               ma_snapshot_s=last.time_s)
                    # flow Peclet and Reynolds numbers on the mean surface speed (as in §8.7 of
                    # the Gaussian study)
                    row["Pe"] = last.U_surface_mean_m_s*RHO*CP_L*LR/K_L
                    row["Re"] = RHO*last.U_surface_mean_m_s*LR/MU
                rows.append(row)
    df = pd.DataFrame(rows).set_index("case")
    return df, ts, ma, ev


def fits(df):
    """y = C P_abs^a v^b over the 6 runs of each mode."""
    out = []
    for m in MODES:
        g = df[df["mode"] == m]
        if len(g) < 4:
            continue
        X = np.column_stack([np.ones(len(g)), np.log(g.absorbed_W), np.log(g.speed_mm_s)])
        for col in ["depth_mm", "width_mm", "length_mm", "aspect_w_d", "fz_area_mm2", "superheat_K",
                    "U_max_m_s", "cr_med", "G_med", "R_med", "GR_med", "eta_melt"]:
            y = g[col]
            if (y <= 0).any():
                continue
            y = np.log(y)
            b = np.linalg.lstsq(X, y, rcond=None)[0]
            r2 = 1 - np.sum((y - X@b)**2)/np.sum((y - y.mean())**2)
            out.append(dict(mode=m, quantity=col, C=np.exp(b[0]), a_power=b[1], b_speed=b[2], R2=r2))
    return pd.DataFrame(out)


def by_speed(ax, df, col, modes=MODES, err=None, logy=False):
    for m in modes:
        for P in POWERS:
            g = df[(df["mode"] == m) & (df.power_W == P)].sort_values("speed_mm_s")
            if g.empty:
                continue
            kw = dict(color=COLOR[m], linestyle=LINE[P], marker=MARK[P], markersize=7,
                      markerfacecolor=COLOR[m] if P == 2000 else BG, markeredgewidth=1.8)
            if err:
                lo, hi = g[col] - g[err[0]], g[err[1]] - g[col]
                ax.errorbar(g.speed_mm_s, g[col], yerr=[lo, hi], capsize=3, elinewidth=1, **kw)
            else:
                ax.plot(g.speed_mm_s, g[col], **kw)
    ax.set_xticks(SPEEDS)
    ax.set_xlabel("scan speed [mm/s]")
    if logy:
        ax.set_yscale("log")


def legend(fig, modes=MODES, y=1.0):
    h = [plt.Line2D([], [], color=COLOR[m], linewidth=2.5, label=LABEL[m]) for m in modes]
    h += [plt.Line2D([], [], color=MUTED, linestyle=LINE[P], marker=MARK[P],
                     markerfacecolor=MUTED if P == 2000 else BG, label=f"{P} W") for P in POWERS]
    fig.legend(handles=h, loc="upper center", ncol=len(h), bbox_to_anchor=(0.5, y), fontsize=9)


def fig_geometry(df):
    fig, axs = plt.subplots(2, 2, figsize=(11, 8))
    for ax, col, lab in [(axs[0, 0], "depth_mm", "pool depth [mm]"),
                         (axs[0, 1], "width_mm", "pool full width [mm]"),
                         (axs[1, 0], "length_mm", "pool length [mm]"),
                         (axs[1, 1], "aspect_w_d", "aspect ratio width / depth")]:
        by_speed(ax, df, col)
        ax.set_ylabel(lab)
        ax.set_ylim(bottom=0)
    axs[0, 1].axhline(3.0, color=MUTED, linewidth=1, linestyle=":")
    axs[0, 1].text(8.9, 3.05, "beam diameter", color=MUTED, fontsize=8, ha="right")
    fig.suptitle("Quasi-steady melt-pool geometry (liquidus surface)", y=0.995)
    legend(fig, y=0.965)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(OUT/"geometry_vs_speed.png", dpi=150)
    plt.close(fig)


def fig_temperature(df):
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.6))
    by_speed(axs[0], df, "T_max_K")
    axs[0].axhline(T_BOIL, color="#d03b3b", linewidth=1, linestyle=":")
    axs[0].text(3.1, T_BOIL + 30, "boiling point 3533 K", color="#d03b3b", fontsize=8)
    axs[0].axhline(TL, color=MUTED, linewidth=1, linestyle=":")
    axs[0].text(3.1, TL + 30, "liquidus", color=MUTED, fontsize=8)
    axs[0].set(ylabel="quasi-steady peak temperature [K]", title="Peak temperature")
    by_speed(axs[1], df, "U_max_m_s", modes=("MaB", "B"), logy=True)
    axs[1].set(ylabel="quasi-steady peak melt speed [m/s] (log)", title="Peak melt speed")
    by_speed(axs[2], df, "first_melting_ms")
    axs[2].set(ylabel="time to first melting [ms]", title="Melting onset after laser on")
    axs[2].set_ylim(bottom=0)
    legend(fig, y=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    fig.savefig(OUT/"temperature_flow_vs_speed.png", dpi=150)
    plt.close(fig)


def fig_ratios(df):
    """Effect of each force: value with Marangoni + buoyancy, and with
    buoyancy only, divided by the conduction-only value."""
    qty = [("depth_mm", "depth"), ("width_mm", "width"), ("length_mm", "length"),
           ("aspect_w_d", "width/depth"), ("fz_area_mm2", "melted area"),
           ("superheat_K", "superheat T−Tl"), ("cr_med", "cooling rate"),
           ("G_med", "G"), ("R_med", "R"), ("GR_med", "G/R")]
    conds = [(P, v) for P in POWERS for v in SPEEDS if name(P, v, "none") in df.index]
    fig, axs = plt.subplots(1, 2, figsize=(15, 4.8), sharey=True)
    for ax, m in zip(axs, ("MaB", "B")):
        x = np.arange(len(qty))
        w = 0.8/len(conds)
        # one hue per power, light -> dark with speed
        shades ={1000: ["#a9d4bf", "#5fb08a", "#2f7d59"], 2000: ["#b5c9ee", "#6f95dd", "#2f5fb5"]}
        for i, (P, v) in enumerate(conds):
            r = [df.loc[name(P, v, m), q]/df.loc[name(P, v, "none"), q] for q, _ in qty]
            ax.bar(x - 0.4 + w*(i + 0.5), r, w*0.92, color=shades[P][SPEEDS.index(v)],
                   label=f"{P} W, {v} mm/s")
        ax.axhline(1, color=INK, linewidth=1)
        ax.set_xticks(x, [l for _, l in qty], rotation=30, ha="right")
        ax.grid(axis="x", visible=False)
        ax.set_title(f"{LABEL[m]} ÷ neither")
    axs[0].set_ylabel("ratio to the conduction-only run")
    axs[0].set_yscale("log")
    axs[0].set_yticks([0.3, 0.5, 1, 2, 3, 5], ["0.3", "0.5", "1", "2", "3", "5"])
    axs[0].minorticks_off()
    axs[1].legend(fontsize=8, ncol=2, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT/"force_effect_ratios.png", dpi=150)
    plt.close(fig)


def fig_histories(df, ts):
    for col, lab, fn in [("depth_liq_m", "pool depth [mm]", "history_depth.png"),
                         ("width_full_liq_m", "pool full width [mm]", "history_width.png"),
                         ("T_max_K", "peak temperature [K]", "history_Tmax.png"),
                         ("U_max_m_s", "peak melt speed [m/s]", "history_Umax.png")]:
        fig, axs = plt.subplots(2, 3, figsize=(15, 7.5), sharey=(col != "U_max_m_s"))
        for i, P in enumerate(POWERS):
            for j, v in enumerate(SPEEDS):
                ax = axs[i, j]
                for m in MODES:
                    c = name(P, v, m)
                    if c not in ts:
                        continue
                    t = ts[c]
                    y = t[col]*(1e3 if col.endswith("_m") else 1)
                    if col == "U_max_m_s" and m == "none":
                        continue
                    ax.plot(t.time_s, y, color=COLOR[m], linewidth=1.6, label=LABEL[m])
                off = 4.0/v
                ax.axvline(off, color=MUTED, linewidth=1, linestyle=":")
                ax.text(off, ax.get_ylim()[1] if False else 0, " laser off", color=MUTED,
                        fontsize=8, va="bottom", transform=ax.get_xaxis_transform())
                if col == "T_max_K":
                    ax.axhline(T_BOIL, color="#d03b3b", linewidth=0.8, linestyle=":")
                if col == "U_max_m_s":
                    ax.set_yscale("log")
                    ax.set_ylim(1e-4, 1)
                ax.set_title(f"{P} W, {v} mm/s", fontsize=10)
                ax.set_xlim(0, max(1.5, off + 0.4))
                if i == 1:
                    ax.set_xlabel("time [s]")
                if j == 0:
                    ax.set_ylabel(lab)
        axs[0, 0].legend(fontsize=8, loc="upper right" if col != "T_max_K" else "center right")
        fig.tight_layout()
        fig.savefig(OUT/fn, dpi=150)
        plt.close(fig)


def section(c, t, which):
    d = ROOT/"cases"/c/"postProcessing"/"sections"
    tn = next(p for p in d.iterdir() if float(p.name) == t)
    r = read_raw(tn/("crossSection.xy" if which == "crs" else "longitudinal.xy"))
    if which == "crs":
        h = np.concatenate([r["face_y"], -r["face_y"]])*1e3
        z = np.concatenate([r["face_z"]]*2)*1e3
        T = np.concatenate([r["T"]]*2)
        uh = np.concatenate([r["U_y"], -r["U_y"]])
        uz = np.concatenate([r["U_z"]]*2)
    else:
        h, z, T, uh, uz = r["face_x"]*1e3, r["face_z"]*1e3, r["T"], r["U_x"], r["U_z"]
    return h, z, T, uh, uz


def fig_pool_overlay(df):
    """Liquidus outline of the three force sets, cross-section at the beam
    and symmetry plane, at the section time of each speed."""
    for which, fn, xl in [("crs", "pool_outline_cross.png", "y [mm]"),
                          ("lon", "pool_outline_longitudinal.png", "x [mm]")]:
        fig, axs = plt.subplots(2, 3, figsize=(15, 5.4))
        for i, P in enumerate(POWERS):
            for j, v in enumerate(SPEEDS):
                ax = axs[i, j]
                t = T_SEC[v]
                xb = 8 + v*t
                for m in MODES:
                    c = name(P, v, m)
                    if c not in df.index:
                        continue
                    h, z, T, _, _ = section(c, t, which)
                    tri = mtri.Triangulation(h, z)
                    ax.tricontour(tri, T, levels=[TL], colors=[COLOR[m]], linewidths=2)
                    ax.tricontour(tri, T, levels=[1000], colors=[COLOR[m]], linewidths=0.8,
                                  linestyles=":")
                ax.set_aspect("equal")
                if which == "crs":
                    ax.set_xlim(-3.6, 3.6)
                    ax.axvspan(-1.5, 1.5, ymin=0.96, color="#d03b3b", alpha=0.35, lw=0)
                else:
                    ax.set_xlim(xb - 6.5, xb + 2)
                    ax.axvspan(xb - 1.5, xb + 1.5, ymin=0.96, color="#d03b3b", alpha=0.35, lw=0)
                ax.set_ylim(-2.0, 0)
                ax.set_title(f"{P} W, {v} mm/s, t = {t:g} s", fontsize=10)
                ax.set_xlabel(xl)
                if j == 0:
                    ax.set_ylabel("z [mm]")
        h = [plt.Line2D([], [], color=COLOR[m], linewidth=2, label=LABEL[m]) for m in MODES]
        h += [plt.Line2D([], [], color=MUTED, linewidth=0.8, linestyle=":", label="1000 K isotherm"),
              plt.Rectangle((0, 0), 1, 1, color="#d03b3b", alpha=0.35, label="beam footprint")]
        fig.legend(handles=h, loc="upper center", ncol=5, fontsize=9)
        fig.suptitle("solid line: liquidus (1928 K) = melt-pool boundary", y=0.935, fontsize=9,
                     color=MUTED)
        fig.tight_layout(rect=(0, 0, 1, 0.92))
        fig.savefig(OUT/fn, dpi=150)
        plt.close(fig)


def fig_fusion_zone(df, ev):
    """Final melted (fusion-zone) cross-section at x = 10 mm: the cells that
    melted and re-solidified, i.e. what a polished and etched cut would show."""
    fig, axs = plt.subplots(2, 3, figsize=(15, 6.2))
    for i, P in enumerate(POWERS):
        for j, v in enumerate(SPEEDS):
            ax = axs[i, j]
            for k, m in enumerate(MODES):
                c = name(P, v, m)
                if c not in ev:
                    continue
                fz = fusion_zone(ev[c])
                # outline: deepest melted cell in each y column, mirrored
                col = fz.groupby("y").z.min().sort_index()
                y = np.concatenate([[col.index.max() + 0.05], col.index[::-1] + 0.05,
                                    -(col.index + 0.05), [-(col.index.max() + 0.05)]])
                zz = np.concatenate([[0], col.values[::-1] - 0.05, col.values - 0.05, [0]])
                ax.step(y, zz, where="mid", color=COLOR[m], linewidth=2,
                        label=f"{LABEL[m]}: {df.loc[c, 'fz_area_mm2']:.2f} mm²")
            ax.set_aspect("equal")
            ax.set_xlim(-3.2, 3.2)
            ax.set_ylim(-2.7, 0.05)
            ax.set_title(f"{P} W, {v} mm/s", fontsize=10)
            ax.legend(fontsize=7.5, loc="lower center")
            if i == 1:
                ax.set_xlabel("y [mm]")
            if j == 0:
                ax.set_ylabel("z [mm]")
    fig.suptitle(f"Fusion zone (melted and re-solidified metal) in the cross-section x = {X_SLAB - 0.05:g}–"
                 f"{X_SLAB + 0.05:g} mm", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT/"fusion_zone_cross_sections.png", dpi=150)
    plt.close(fig)


def fig_isotherms(df):
    """Ten isotherms and velocity arrows, cross-section and symmetry plane,
    the three force sets side by side, one figure per (power, speed)."""
    for P in POWERS:
        for v in SPEEDS:
            cs = [name(P, v, m) for m in MODES if name(P, v, m) in df.index]
            if len(cs) < 2:
                continue
            t = T_SEC[v]
            xb = 8 + v*t
            data = {c: {w: section(c, t, w) for w in ("crs", "lon")} for c in cs}
            Tmax = max(d[w][2].max() for d in data.values() for w in d)
            levels = np.round(np.linspace(1000, Tmax - 50, 10), -1)
            fig, axs = plt.subplots(2, len(cs), figsize=(5.4*len(cs), 4.6), layout="constrained")
            for k, c in enumerate(cs):
                m = c.rsplit("_", 1)[1]
                for row, w in enumerate(("crs", "lon")):
                    ax = axs[row, k]
                    h, z, T, uh, uz = data[c][w]
                    tri = mtri.Triangulation(h, z)
                    cf = ax.tricontourf(tri, T, levels=np.concatenate([[293], levels, [Tmax + 1]]),
                                        cmap="inferno")
                    cl = ax.tricontour(tri, T, levels=levels, colors="w", linewidths=0.5)
                    ax.clabel(cl, fmt="%d", fontsize=6)
                    ax.tricontour(tri, T, levels=[TL], colors="c", linewidths=1.4)
                    lims = ((-3.2, 3.2), (-1.9, 0)) if w == "crs" else ((xb - 5.5, xb + 2.0), (-1.9, 0))
                    sel = (T > TS) & (h > lims[0][0]) & (h < lims[0][1])
                    arrows(ax, h, z, uh, uz, sel, max_len_mm=0.35, n_max=150, color="#9ff3ff")
                    ax.set_xlim(*lims[0])
                    ax.set_ylim(*lims[1])
                    ax.set_aspect("equal")
                    ax.grid(False)
                    ax.set_title(f"{LABEL[m]}: {'cross-section x = %.2f mm' % xb if w == 'crs' else 'symmetry plane y = 0'}",
                                 fontsize=9)
                    ax.set_xlabel("y [mm]" if w == "crs" else "x [mm]")
                    if k == 0:
                        ax.set_ylabel("z [mm]")
            fig.colorbar(cf, ax=axs.ravel().tolist(), label="T [K]", shrink=0.9)
            fig.suptitle(f"{P} W, {v} mm/s, t = {t:g} s: 10 isotherms (white, labelled), liquidus (cyan), "
                         f"velocity arrows (light blue)", fontsize=10)
            fig.savefig(OUT/f"isotherms_U{P}_v{v}.png", dpi=150)
            plt.close(fig)


def fig_surface_profile(df):
    """Top-surface temperature along the centreline and across the pool."""
    fig, axs = plt.subplots(2, 3, figsize=(15, 7.2), sharey="row")
    for j, v in enumerate(SPEEDS):
        t = T_SEC[v]
        xb = 8 + v*t
        for P, ls in [(1000, "--"), (2000, "-")]:
            for m in MODES:
                c = name(P, v, m)
                if c not in df.index:
                    continue
                for row, w in enumerate(("lon", "crs")):
                    h, z, T, _, _ = section(c, t, w)
                    top = z == z.max()
                    o = np.argsort(h[top])
                    hh = h[top][o] - (xb if w == "lon" else 0)
                    axs[row, j].plot(hh, T[top][o], color=COLOR[m], linestyle=ls, linewidth=1.5)
        for row in range(2):
            ax = axs[row, j]
            ax.axhline(TL, color=MUTED, linewidth=0.8, linestyle=":")
            ax.axhline(T_BOIL, color="#d03b3b", linewidth=0.8, linestyle=":")
            ax.axvspan(-1.5, 1.5, color="#d03b3b", alpha=0.06, lw=0)
        axs[0, j].set(xlim=(-6, 2.5), title=f"{v} mm/s, t = {t:g} s",
                      xlabel="x − x_beam [mm] (laser moves to +x)")
        axs[1, j].set(xlim=(-4, 4), xlabel="y [mm] (across the track)")
    axs[0, 0].set_ylabel("surface T on the centreline [K]")
    axs[1, 0].set_ylabel("surface T across the beam [K]")
    legend(fig, y=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT/"surface_temperature_profiles.png", dpi=150)
    plt.close(fig)


def fig_solidification(df):
    fig, axs = plt.subplots(2, 2, figsize=(11, 8))
    by_speed(axs[0, 0], df, "G_med", err=("G_p10", "G_p90"), logy=True)
    axs[0, 0].set(ylabel="G [K/mm] (median, p10–p90)", title="Temperature gradient G")
    by_speed(axs[0, 1], df, "R_med", err=("R_p10", "R_p90"), logy=True)
    axs[0, 1].set(ylabel="R [mm/s] (median, p10–p90)", title="Solidification rate R")
    by_speed(axs[1, 0], df, "cr_med", err=("cr_p10", "cr_p90"), logy=True)
    axs[1, 0].set(ylabel="G·R = cooling rate [K/s]", title="Cooling rate G·R (sets grain size)")
    by_speed(axs[1, 1], df, "GR_med", logy=True)
    axs[1, 1].set(ylabel="G/R [K·s/mm²] (median)", title="G/R (sets grain morphology)")
    for ax in axs.ravel():
        ax.minorticks_off()
    legend(fig, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT/"G_R_vs_speed.png", dpi=150)
    plt.close(fig)


def fig_gr_map(df, ev):
    fig, axs = plt.subplots(1, 2, figsize=(14, 5.6))
    for ax, P in zip(axs, POWERS):
        for m in MODES:
            for v in SPEEDS:
                c = name(P, v, m)
                if c not in ev:
                    continue
                e = ev[c][(ev[c].t <= df.loc[c, "laser_off_s"]) & (ev[c].R > 0)]
                ax.scatter(e.R, e.G, s=2, color=COLOR[m], alpha=0.12, lw=0, rasterized=True)
            g = df[(df["mode"] == m) & (df.power_W == P)].sort_values("speed_mm_s")
            ax.plot(g.R_med, g.G_med, color=COLOR[m], marker="o", markersize=7,
                    markeredgecolor=BG, label=f"{LABEL[m]} (median, 3 → 9 mm/s)")
            for _, r in g.iterrows():
                ax.annotate(f"{r.speed_mm_s:g}", (r.R_med, r.G_med), xytext=(5, 4),
                            textcoords="offset points", fontsize=8, color=COLOR[m])
        Rr = np.logspace(-2, 2.3, 50)
        for gr in (1e2, 1e3, 1e4):
            ax.plot(Rr, gr*Rr, color=MUTED, linewidth=0.8, linestyle="--")
            ax.text(4000/gr, 4000, f"G/R = {gr:g} K·s/mm²", color=MUTED, fontsize=7, ha="right", va="top")
        for cr in (1e2, 1e3, 1e4):
            ax.plot(Rr, cr/Rr, color=MUTED, linewidth=0.8, linestyle=":")
            ax.text(cr/220, 220, f"G·R = {cr:g} K/s", color=MUTED, fontsize=7, va="bottom")
        ax.set(xscale="log", yscale="log", xlim=(0.03, 60), ylim=(200, 5e3),
               xlabel="solidification rate R [mm/s]", ylabel="temperature gradient G [K/mm]",
               title=f"{P} W: every solidification event while the laser is on")
        ax.minorticks_off()
        ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(OUT/"G_R_map.png", dpi=150)
    plt.close(fig)


def fig_gr_depth(df, ev):
    """G and R along the fusion boundary: binned by the angle of the boundary
    normal, from the pool bottom (0°) to the surface edge (90°), mid-track."""
    for col, lab, fn in [("G", "G [K/mm]", "G_along_boundary.png"),
                         ("R", "R [mm/s]", "R_along_boundary.png")]:
        fig, axs = plt.subplots(2, 3, figsize=(15, 7), sharey=True)
        for i, P in enumerate(POWERS):
            for j, v in enumerate(SPEEDS):
                ax = axs[i, j]
                for m in MODES:
                    c = name(P, v, m)
                    if c not in ev:
                        continue
                    e = ev[c][(np.abs(ev[c].x - X_SLAB) < 1.0) & (ev[c].t <= df.loc[c, "laser_off_s"])]
                    fz = fusion_zone(ev[c])
                    d, hw = -fz.z.min() + 0.05, fz.y.max() + 0.05
                    # position along the fusion boundary as the elliptic angle
                    ang = np.degrees(np.arctan2(e.y/hw, (-e.z)/d))
                    bins = np.linspace(0, 90, 10)
                    k = np.digitize(ang, bins)
                    med = [e[col][k == b].median() if (k == b).sum() > 2 else np.nan
                           for b in range(1, len(bins))]
                    ax.plot(0.5*(bins[1:] + bins[:-1]), med, color=COLOR[m], marker="o",
                            markersize=4, label=LABEL[m])
                ax.set_yscale("log")
                tk = [0.1, 0.2, 0.5, 1, 2, 5, 10] if col == "R" else [200, 500, 1000, 2000, 5000]
                ax.set_yticks(tk, [f"{t:g}" for t in tk])
                ax.set_xticks([0, 30, 60, 90], ["0°\nbottom", "30°", "60°", "90°\nsurface"])
                ax.set_title(f"{P} W, {v} mm/s", fontsize=10)
                if j == 0:
                    ax.set_ylabel(f"{lab} (median per 10° bin)")
                ax.minorticks_off()
        axs[0, 0].legend(fontsize=8)
        fig.suptitle(f"{col} along the fusion boundary in the cross-section (track middle, x = 9–11 mm)",
                     fontsize=11)
        fig.tight_layout()
        fig.savefig(OUT/fn, dpi=150)
        plt.close(fig)


def fig_surface_marangoni(df):
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.4))
    by_speed(axs[0], df, "gradT_max_K_mm")
    axs[0].set(ylabel="max surface |∇T| on the melt [K/mm]", title="Surface temperature gradient")
    by_speed(axs[1], df, "stress_max_Pa", modes=("MaB",))
    axs[1].set(ylabel="max Marangoni shear stress [Pa]", title="Thermocapillary stress (MaB only)")
    by_speed(axs[2], df, "Us_mean", modes=("MaB", "B"), logy=True)
    axs[2].set(ylabel="mean surface melt speed [m/s] (log)", title="Mean surface speed")
    for ax in axs[:2]:
        ax.set_ylim(bottom=0)
    legend(fig, y=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(OUT/"surface_marangoni.png", dpi=150)
    plt.close(fig)


def fig_dimensionless(df):
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.4))
    by_speed(axs[0], df, "Pe", modes=("MaB", "B"), logy=True)
    axs[0].axhline(1, color=MUTED, linewidth=1, linestyle=":")
    axs[0].set(ylabel="Péclet number u ρ c_p L / k (log)", title="Convection vs conduction in the pool")
    by_speed(axs[1], df, "Ma", modes=("MaB",))
    axs[1].set(ylabel="Marangoni number Ma", title="Surface-tension driving (MaB)")
    by_speed(axs[2], df, "Ma_over_Gr", modes=("MaB",))
    axs[2].set(ylabel="Ma / Gr", title="Surface tension vs buoyancy")
    axs[1].set_ylim(bottom=0)
    axs[2].set_ylim(bottom=0)
    legend(fig, modes=("MaB", "B"), y=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(OUT/"dimensionless.png", dpi=150)
    plt.close(fig)


def fig_scaling(df):
    """Depth and width against line energy; superheat against power."""
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.6))
    for m in MODES:
        g = df[df["mode"] == m]
        for P in POWERS:
            h = g[g.power_W == P]
            for ax, col in zip(axs, ("depth_mm", "width_mm", "fz_area_mm2")):
                ax.scatter(h.line_energy_J_mm, h[col], s=50, marker=MARK[P], color=COLOR[m],
                           facecolor=COLOR[m] if P == 2000 else BG, linewidth=1.6, zorder=3)
        for ax, col in zip(axs, ("depth_mm", "width_mm", "fz_area_mm2")):
            x = np.log(g.line_energy_J_mm)
            b = np.polyfit(x, np.log(g[col]), 1)
            xx = np.linspace(x.min(), x.max(), 20)
            ax.plot(np.exp(xx), np.exp(np.polyval(b, xx)), color=COLOR[m], linewidth=1,
                    label=f"{LABEL[m]}: ∝ E^{b[0]:.2f}")
    for ax, lab in zip(axs, ("pool depth [mm]", "pool full width [mm]", "fusion-zone area [mm²]")):
        ax.set(xscale="log", yscale="log", xlabel="line energy P_abs / v [J/mm]", ylabel=lab)
        ax.legend(fontsize=8, loc="upper left")
        ax.minorticks_off()
        ax.set_xticks([40, 60, 100, 150, 250], ["40", "60", "100", "150", "250"])
    fig.suptitle("Pool size against line energy (open markers 1000 W, filled 2000 W)", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT/"scaling_line_energy.png", dpi=150)
    plt.close(fig)


def fig_exponents(fit):
    qty = ["depth_mm", "width_mm", "length_mm", "fz_area_mm2", "superheat_K", "cr_med", "G_med", "R_med"]
    lab = ["depth", "width", "length", "melted area", "superheat", "cooling rate", "G", "R"]
    fig, axs = plt.subplots(1, 2, figsize=(15, 4.4), sharey=True)
    for ax, ex, title in [(axs[0], "a_power", "power exponent a"), (axs[1], "b_speed", "speed exponent b")]:
        x = np.arange(len(qty))
        for i, m in enumerate(MODES):
            f = fit[fit["mode"] == m].set_index("quantity")
            vals = [f.loc[q, ex] if q in f.index else np.nan for q in qty]
            ax.bar(x + (i - 1)*0.27, vals, 0.25, color=COLOR[m], label=LABEL[m])
        ax.axhline(0, color=INK, linewidth=1)
        ax.set_xticks(x, lab, rotation=20)
        ax.grid(axis="x", visible=False)
        ax.set_title(f"{title} in  y = C·P^a·v^b")
    axs[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT/"power_law_exponents.png", dpi=150)
    plt.close(fig)


def fig_efficiency(df):
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.4))
    by_speed(axs[0], df, "fz_area_mm2")
    axs[0].set(ylabel="fusion-zone cross-section [mm²]", title="Melted track cross-section")
    by_speed(axs[1], df, "eta_melt")
    axs[1].set(ylabel="ρ v A H_melt / P_abs", title="Melting efficiency")
    for ax in axs:
        ax.set_ylim(bottom=0)
    legend(fig, y=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(OUT/"melting_efficiency.png", dpi=150)
    plt.close(fig)


def v_runs():
    """The Gaussian 3 mm validation set (V*): quasi-steady values."""
    rows = []
    for f in sorted(ROOT.glob("results/V1*/summary.json")):
        s = json.loads(f.read_text())
        c = s["case"]
        if c.endswith("_flat") or c.endswith("_50um"):
            continue
        q, so = s["quasi_steady"], s["solidification"]
        rows.append(dict(case=c, power_W=int(s["inputs"]["laser_power_W"]),
                         speed_mm_s=round(s["inputs"]["scan_speed_m_s"]*1e3),
                         mode="B" if c.endswith("_noMa") else "MaB",
                         depth_mm=q["pool_depth_mm"]["mean"], width_mm=q["pool_width_full_mm"]["mean"],
                         T_max_K=q["T_max_K"]["mean"], U_max_m_s=q["U_max_m_s"]["mean"],
                         cr_med=so["cooling_rate_K_s"]["median"], R_med=so["R_m_s"]["median"]*1e3,
                         G_med=so["G_K_m"]["median"]*1e-3))
    return pd.DataFrame(rows).set_index("case")


def fig_v_set(v):
    """Gaussian 3 mm beam, 1000/1400 W, 6/9/12 mm/s, with and without Marangoni."""
    fig, axs = plt.subplots(1, 4, figsize=(16, 4.2))
    for ax, col, lab in zip(axs, ("depth_mm", "width_mm", "T_max_K", "cr_med"),
                            ("pool depth [mm]", "pool full width [mm]", "peak temperature [K]",
                             "median cooling rate [K/s]")):
        for m, P in [(m, P) for m in ("MaB", "B") for P in (1000, 1400)]:
            g = v[(v["mode"] == m) & (v.power_W == P)].sort_values("speed_mm_s")
            ax.plot(g.speed_mm_s, g[col], color=COLOR[m], linestyle="--" if P == 1000 else "-",
                    marker="o" if P == 1000 else "s", markerfacecolor=BG if P == 1000 else COLOR[m],
                    markeredgewidth=1.8, label=f"{'with' if m == 'MaB' else 'without'} Marangoni, {P} W")
        ax.set(xlabel="scan speed [mm/s]", ylabel=lab, xticks=(6, 9, 12))
        if col != "T_max_K":
            ax.set_ylim(bottom=0)
    axs[0].legend(fontsize=7.5)
    fig.suptitle("Gaussian beam, 3 mm diameter (D4σ), absorptivity 0.35: quasi-steady values", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT/"gaussian_v_set.png", dpi=150)
    plt.close(fig)


def fig_beam_shape(df, v):
    """Uniform (k = 20) against Gaussian beam of the same 3 mm diameter and
    the same absorbed power (350 W), at 6 and 9 mm/s."""
    qty = [("depth_mm", "depth"), ("width_mm", "width"), ("T_max_K", "peak T"),
           ("U_max_m_s", "peak speed"), ("cr_med", "cooling rate"), ("G_med", "G"), ("R_med", "R")]
    fig, ax = plt.subplots(figsize=(11, 4.2))
    x = np.arange(len(qty))
    pairs = [(sp, m) for m in ("MaB", "B") for sp in (6, 9)]
    shade = {("MaB", 6): "#5c9be8", ("MaB", 9): "#1f5fae", ("B", 6): "#f19a69", ("B", 9): "#c45417"}
    for i, (sp, m) in enumerate(pairs):
        u = df.loc[name(1000, sp, m)]
        g = v.loc[f"V1000_v{sp}" + ("" if m == "MaB" else "_noMa")]
        r = [u[q]/g[q] for q, _ in qty]
        ax.bar(x - 0.3 + 0.2*i, r, 0.18, color=shade[(m, sp)],
               label=f"{LABEL[m]}, {sp} mm/s")
    ax.axhline(1, color=INK, linewidth=1)
    ax.set_xticks(x, [l for _, l in qty])
    ax.grid(axis="x", visible=False)
    ax.set_ylim(0.6, 1.7)
    ax.set_ylabel("uniform ÷ Gaussian")
    ax.set_title("Beam shape at equal diameter (3 mm) and equal absorbed power (350 W)")
    ax.legend(fontsize=8, ncol=2, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT/"uniform_vs_gaussian.png", dpi=150)
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df, ts, ma, ev = load()
    fit = fits(df)
    df.round(6).to_csv(ROOT/"results"/"ta_summary.csv", lineterminator="\n")
    fit.round(4).to_csv(ROOT/"results"/"ta_fits.csv", index=False, lineterminator="\n")
    print(f"{len(df)} runs")
    for f in (fig_geometry, fig_temperature, fig_ratios, fig_solidification, fig_surface_marangoni,
              fig_dimensionless, fig_scaling, fig_efficiency, fig_pool_overlay, fig_surface_profile,
              fig_isotherms):
        f(df)
    fig_histories(df, ts)
    fig_fusion_zone(df, ev)
    fig_gr_map(df, ev)
    fig_gr_depth(df, ev)
    fig_exponents(fit)
    v = v_runs()
    fig_v_set(v)
    fig_beam_shape(df, v)
    print(f"-> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
