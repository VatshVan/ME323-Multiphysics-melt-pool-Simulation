#!/usr/bin/env python3
"""Prediction analysis of the two final models (no retraining).

Run-level model (models/run_composite.pkl, results/run_predictions_oos.csv,
results/run_oos_algorithms.npz):
    fig_data_coverage.png            inputs of the 46 runs and the experiment cases
    fig_parity_by_algorithm.png      out-of-sample parity, every algorithm and the composite
    fig_residuals.png                out-of-sample error against P_abs, v, r, by flow mode
    fig_uncertainty_calibration.png  is sigma (spread across algorithms) a usable error bar?
    fig_process_maps.png             predicted outputs over P_abs x v, experiment beam, 3 flow modes
    fig_marangoni_effect_map.png     MaB / conduction-only ratios, checked against the U runs
    fig_uncertainty_map.png          3 sigma / mu of depth and width over P_abs x v
    fig_experiment_all_outputs.png   every output vs speed for the experiment cases
    fig_dimensionless.png            Ma vs aspect ratio and Pe vs Ma
Event model (models/event_composite.pkl, results/event_predictions_holdout.csv.gz):
    fig_events_cross_section.png     simulated vs predicted G and R in the pool cross-section
    fig_events_error_position.png    where in the pool the G and R errors sit
    fig_experiment_solidification.png  predicted G, R, G*R cross-sections + G-R map, experiment cases

Usage: python step6_analysis.py
"""

import pickle
import warnings

import numpy as np
import pandas as pd
from matplotlib.colors import LogNorm, TwoSlopeNorm
from scipy.stats import norm
from sklearn.metrics import r2_score

from mpml.data import TARGET_NAMES, TARGETS, derived_numbers, load_runs, HERE
from mpml.plots import INK, MODE_STYLE, MUTED, SERIES, plt

OUT, MODELS = HERE/"results", HERE/"models"
UNITS = {n: u for _, n, u in TARGETS}
COL = {n: c for c, n, _ in TARGETS}
SHOW = ["depth", "width", "T_max", "cooling_rate", "G", "R"]
MODES = {"MaB": (1, 1), "B": (1, 0), "none": (0, 0)}
ETA, R_EXP, K_EXP = 0.35, 1.5, 20.0
EXP_P, EXP_V = (1000.0, 1400.0), (6.0, 9.0, 12.0)
SET_STYLE = {"R": (SERIES[0], "o", "R: Gaussian, r 0.5–1 mm"), "V": (SERIES[1], "s", "V: Gaussian r 1.5 (+1 flat k=10)"),
             "U": (SERIES[2], "^", "U: flat top k=20, r 1.5 mm")}
S_STEADY = 1.5   # mm from the track start, used for the experiment cross-sections


def load(name):
    with open(MODELS/name, "rb") as f:
        return pickle.load(f)


def frame(P_abs, v, mode, r=R_EXP, k=K_EXP):
    P_abs, v = np.broadcast_arrays(np.asarray(P_abs, float), np.asarray(v, float))
    fl, ma = MODES[mode]
    return pd.DataFrame({"absorbed_power_W": P_abs.ravel(), "scan_speed_mm_s": v.ravel(), "beam_radius_mm": r,
                         "beam_k": k, "flow": fl, "marangoni": ma})


def run_predict(rm, df):
    """mu, sd in physical units, (n, T)."""
    A = rm["targets"].to_physical(rm["model"].predict(rm["features"](df))[2])
    return A.mean(0), A.std(0)


def event_predict(em, df):
    A = em["targets"].to_physical(em["model"].predict(em["features"](df))[2])
    return np.exp(np.log(A).mean(0))


# ---------------------------------------------------------------- run level
def coverage(runs):
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.8))
    for s, (c, mk, lab) in SET_STYLE.items():
        d = runs[runs["set"] == s]
        axs[0].scatter(d.scan_speed_mm_s, d.absorbed_power_W, c=c, marker=mk, s=45, label=lab,
                       edgecolor="white", lw=0.6, zorder=3)
        axs[1].scatter(d.beam_radius_mm + 0.02*(d.beam_k > 2), d.absorbed_power_W, c=c, marker=mk, s=45,
                       edgecolor="white", lw=0.6, zorder=3)
    ev, ep = np.meshgrid(EXP_V, ETA*np.array(EXP_P))
    for ax, x in ((axs[0], ev.ravel()), (axs[1], np.full(ev.size, R_EXP + 0.04))):
        ax.scatter(x, ep.ravel(), marker="x", s=60, color=INK, lw=1.5, label="planned experiment (η = 0.35)", zorder=4)
    axs[0].set_xlabel("scan speed v [mm/s]")
    axs[0].set_ylabel("absorbed power P_abs [W]")
    axs[0].set_title("Runs in the P_abs–v plane (flow modes overlap)", loc="left")
    axs[0].legend(fontsize=7, loc="upper left")
    axs[1].set_xlabel("beam radius r [mm]")
    axs[1].set_title("Beam radius: r = 1.5 mm only in V and U", loc="left")
    fig.tight_layout()
    fig.savefig(OUT/"fig_data_coverage.png")
    plt.close(fig)


def parity_by_algorithm(runs, oos):
    z = np.load(OUT/"run_oos_algorithms.npz", allow_pickle=True)
    algos, P = list(z["algorithms"]), z["pred"]
    names = list(z["targets"])
    cols = algos + ["composite (no RF)"]
    fig, axs = plt.subplots(len(SHOW), len(cols), figsize=(15, 12.5))
    for i, t in enumerate(SHOW):
        j = names.index(t)
        sim = runs[COL[t]].values
        lo, hi = sim.min(), sim.max()
        for k, a in enumerate(cols):
            ax = axs[i, k]
            pred = oos[f"{t}_pred"].values if a.startswith("composite") else P[algos.index(a), :, j]
            for mode, (c, mk, _) in MODE_STYLE.items():
                s = runs["mode"].values == mode
                ax.scatter(sim[s], pred[s], s=12, color=c, marker=mk, lw=0)
            ax.plot([lo, hi], [lo, hi], color=INK, lw=0.8)
            r2 = r2_score(np.log(sim), np.log(np.clip(pred, 1e-9, None)))
            ax.text(0.04, 0.92, f"R²log {r2:.2f}", transform=ax.transAxes, fontsize=7,
                    color=INK if r2 > 0.9 else SERIES[1])
            ax.tick_params(labelsize=6)
            if i == 0:
                ax.set_title(a.replace("Neural Network", "Neural net").replace("Bayesian Ridge", "Bayes ridge")
                             .replace("Gaussian Process", "GP").replace("Random Forest", "RF (not in comp.)"),
                             fontsize=8)
            if k == 0:
                ax.set_ylabel(f"{t} [{UNITS[t]}]", fontsize=8)
    for mode, (c, mk, lab) in MODE_STYLE.items():
        axs[0, 0].scatter([], [], color=c, marker=mk, label=lab)
    fig.legend(*axs[0, 0].get_legend_handles_labels(), loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.01))
    fig.suptitle("Out-of-sample parity (5-fold over runs): x = simulation, y = prediction", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(OUT/"fig_parity_by_algorithm.png")
    plt.close(fig)


def residuals(runs, oos):
    xs = [("absorbed_power_W", "P_abs [W]"), ("scan_speed_mm_s", "v [mm/s]"), ("beam_radius_mm", "r [mm]")]
    rows = ["depth", "width", "T_max", "G", "R"]
    fig, axs = plt.subplots(len(rows), 3, figsize=(10, 11), sharex="col")
    rng = np.random.RandomState(0)
    for i, t in enumerate(rows):
        err = 100*(oos[f"{t}_pred"]/oos[f"{t}_sim"] - 1)
        for k, (x, lab) in enumerate(xs):
            ax = axs[i, k]
            jit = rng.uniform(-1, 1, len(runs))*0.012*(runs[x].max() - runs[x].min())
            for mode, (c, mk, l) in MODE_STYLE.items():
                s = runs["mode"] == mode
                ax.scatter(runs[x][s] + jit[s], err[s], color=c, marker=mk, s=22, edgecolor="white", lw=0.5, label=l)
            ax.axhline(0, color=INK, lw=0.8)
            ax.axhspan(-10, 10, color=MUTED, alpha=0.1, lw=0)
            if k == 0:
                ax.set_ylabel(f"{t} error [%]")
            if i == len(rows) - 1:
                ax.set_xlabel(lab)
    axs[0, 2].legend(fontsize=7)
    fig.suptitle("Out-of-sample error of the composite vs each input (band ±10 %)", x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT/"fig_residuals.png")
    plt.close(fig)


def calibration(oos):
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.6))
    k = np.linspace(0, 4, 81)
    ax = axs[0]
    ax.plot(k, 2*norm.cdf(k) - 1, color=INK, lw=1.2, ls="--", label="Gaussian, calibrated σ")
    rows = []
    for i, t in enumerate(SHOW):
        zt = np.abs(oos[f"{t}_pred"] - oos[f"{t}_sim"])/oos[f"{t}_sd"]
        ax.plot(k, [(zt <= kk).mean() for kk in k], color=SERIES[i], label=t)
        rows.append({"target": t, "within_1sigma": (zt <= 1).mean(), "within_2sigma": (zt <= 2).mean(),
                     "within_3sigma": (zt <= 3).mean(), "median_abs_z": float(np.median(zt))})
    ax.set_xlabel("k (|prediction − simulation| ≤ k σ)")
    ax.set_ylabel("share of runs")
    ax.set_title("Coverage of the ±kσ band, out-of-sample", loc="left")
    ax.legend(fontsize=7, ncol=2)
    cal = pd.DataFrame(rows)
    cal.to_csv(OUT/"uncertainty_calibration.csv", index=False)
    ax = axs[1]
    x = np.arange(len(SHOW))
    for j, (c, lab) in enumerate([("within_1sigma", "±1σ"), ("within_2sigma", "±2σ"), ("within_3sigma", "±3σ")]):
        ax.bar(x + (j - 1)*0.26, cal[c], width=0.24, color=SERIES[j], label=lab)
    for j, ref in enumerate((0.683, 0.954, 0.997)):
        ax.axhline(ref, color=SERIES[j], lw=0.8, ls="--")
    ax.set_xticks(x, SHOW, rotation=20)
    ax.set_ylim(0, 1.05)
    ax.set_title("Share inside the band (dashed: Gaussian)", loc="left")
    ax.legend(fontsize=7, loc="lower right")
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    fig.savefig(OUT/"fig_uncertainty_calibration.png")
    plt.close(fig)
    print("Uncertainty calibration (out-of-sample):\n" + cal.round(2).to_string(index=False))


def grids(rm, n=45):
    P = np.linspace(300, 800, n)
    V = np.linspace(3, 12, n)
    PP, VV = np.meshgrid(P, V, indexing="ij")
    out = {}
    for mode in MODES:
        mu, sd = run_predict(rm, frame(PP, VV, mode))
        out[mode] = (mu.reshape(n, n, -1), sd.reshape(n, n, -1))
    return P, V, out


def process_maps(runs, P, V, G):
    fig, axs = plt.subplots(len(SHOW), 3, figsize=(11, 16), sharex=True, sharey=True)
    flat = runs[runs.beam_k == K_EXP]
    for i, t in enumerate(SHOW):
        j = TARGET_NAMES.index(t)
        lo = min(G[m][0][..., j].min() for m in MODES)
        hi = max(G[m][0][..., j].max() for m in MODES)
        levels = np.linspace(lo, hi, 13)
        for k, mode in enumerate(MODES):
            ax = axs[i, k]
            cf = ax.contourf(V, P, G[mode][0][..., j], levels=levels, cmap="Blues")
            cs = ax.contour(V, P, G[mode][0][..., j], levels=levels[::3], colors=INK, linewidths=0.5)
            ax.clabel(cs, fontsize=6, fmt="%.3g")
            d = flat[flat["mode"] == mode]
            ax.scatter(d.scan_speed_mm_s, d.absorbed_power_W, s=26, color=SERIES[1], edgecolor="white", lw=0.6,
                       zorder=3, label="simulated flat-top run")
            for vv in EXP_V:
                ax.scatter([vv]*2, ETA*np.array(EXP_P), marker="x", color=INK, s=28, lw=1.2, zorder=4)
            if i == 0:
                ax.set_title(MODE_STYLE[mode][2], loc="left")
            if k == 0:
                ax.set_ylabel(f"{t} [{UNITS[t]}]\nP_abs [W]")
            if i == len(SHOW) - 1:
                ax.set_xlabel("v [mm/s]")
        fig.colorbar(cf, ax=axs[i, :], shrink=0.9, pad=0.01)
    fig.suptitle("Predicted outputs, flat-top r = 1.5 mm (experiment beam). Dots: simulated runs; x: planned "
                 "experiment", x=0.01, ha="left", y=0.995)
    fig.savefig(OUT/"fig_process_maps.png")
    plt.close(fig)


def marangoni_map(runs, P, V, G):
    iw, idp, it = (TARGET_NAMES.index(t) for t in ("width", "depth", "T_max"))
    ma, no = G["MaB"][0], G["none"][0]
    quant = {"depth MaB/none": ma[..., idp]/no[..., idp], "width MaB/none": ma[..., iw]/no[..., iw],
             "T_max MaB/none": ma[..., it]/no[..., it],
             "aspect W/D MaB/none": (ma[..., iw]/ma[..., idp])/(no[..., iw]/no[..., idp])}
    sim = runs[runs.beam_k == K_EXP].pivot_table(index=["absorbed_power_W", "scan_speed_mm_s"], columns="mode",
                                                 values=["qs_depth_mm", "qs_width_mm", "qs_T_max_K"])
    sim_q = {"depth MaB/none": sim["qs_depth_mm"]["MaB"]/sim["qs_depth_mm"]["none"],
             "width MaB/none": sim["qs_width_mm"]["MaB"]/sim["qs_width_mm"]["none"],
             "T_max MaB/none": sim["qs_T_max_K"]["MaB"]/sim["qs_T_max_K"]["none"],
             "aspect W/D MaB/none": (sim["qs_width_mm"]["MaB"]/sim["qs_depth_mm"]["MaB"])
             / (sim["qs_width_mm"]["none"]/sim["qs_depth_mm"]["none"])}
    fig, axs = plt.subplots(1, 4, figsize=(15, 3.8), sharey=True)
    for ax, (name, Z) in zip(axs, quant.items()):
        vmin, vmax = min(Z.min(), 0.99), max(Z.max(), 1.01)
        cf = ax.contourf(V, P, Z, levels=14, cmap="RdBu_r", norm=TwoSlopeNorm(1.0, vmin, vmax))
        cs = ax.contour(V, P, Z, levels=7, colors=INK, linewidths=0.5)
        ax.clabel(cs, fontsize=6, fmt="%.2f")
        for (p, v), val in sim_q[name].items():
            ax.scatter(v, p, s=30, color=INK, zorder=3)
            ax.annotate(f"{val:.2f}", (v, p), textcoords="offset points", xytext=(4, 4), fontsize=7,
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))
        ax.set_title(name, loc="left")
        ax.set_xlabel("v [mm/s]")
        fig.colorbar(cf, ax=ax, shrink=0.85)
    axs[0].set_ylabel("P_abs [W]")
    fig.suptitle("Effect of Marangoni flow, model (colour) vs simulated U runs (labels), flat top r = 1.5 mm",
                 x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT/"fig_marangoni_effect_map.png")
    plt.close(fig)


def uncertainty_map(runs, P, V, G):
    fig, axs = plt.subplots(1, 4, figsize=(15, 3.6), sharey=True)
    flat = runs[runs.beam_k >= 10]
    for col, (t, mode) in enumerate([("depth", "MaB"), ("width", "MaB"), ("depth", "none"), ("width", "none")]):
        j = TARGET_NAMES.index(t)
        rel = 100*3*G[mode][1][..., j]/G[mode][0][..., j]
        ax = axs[col]
        cf = ax.contourf(V, P, rel, levels=12, cmap="Blues")
        d = flat[flat["mode"] == mode]
        ax.scatter(d.scan_speed_mm_s, d.absorbed_power_W, s=26, color=SERIES[1], edgecolor="white", lw=0.6, zorder=3)
        for vv in EXP_V:
            ax.scatter([vv]*2, ETA*np.array(EXP_P), marker="x", color=INK, s=28, lw=1.2, zorder=4)
        ax.set_title(f"3σ/μ of {t}, {mode} [%]", loc="left")
        ax.set_xlabel("v [mm/s]")
        fig.colorbar(cf, ax=ax, shrink=0.85)
    axs[0].set_ylabel("P_abs [W]")
    fig.suptitle("Model uncertainty (spread across algorithms), flat top r = 1.5 mm; dots: flat-top runs, "
                 "x: experiment", x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT/"fig_uncertainty_map.png")
    plt.close(fig)


def experiment_all_outputs(rm, runs):
    vv = np.linspace(3, 12.5, 60)
    fig, axs = plt.subplots(2, len(SHOW), figsize=(17, 6.2), sharex=True)
    for r, Pw in enumerate(EXP_P):
        for mode, (c, mk, lab) in MODE_STYLE.items():
            mu, sd = run_predict(rm, frame(ETA*Pw, vv, mode))
            for k, t in enumerate(SHOW):
                j = TARGET_NAMES.index(t)
                ax = axs[r, k]
                ax.fill_between(vv, mu[:, j] - 3*sd[:, j], mu[:, j] + 3*sd[:, j], color=c, alpha=0.15, lw=0)
                ax.plot(vv, mu[:, j], color=c, label=lab)
                s = runs[(runs.beam_k == K_EXP) & np.isclose(runs.absorbed_power_W, ETA*Pw) & (runs["mode"] == mode)]
                ax.plot(s.scan_speed_mm_s, s[COL[t]], mk, color=c, ms=7, mec=INK, mew=0.8)
        for k, t in enumerate(SHOW):
            axs[r, k].axvspan(5.6, 12.4, color=MUTED, alpha=0.06, lw=0)
            axs[0, k].set_title(f"{t} [{UNITS[t]}]", loc="left")
            axs[1, k].set_xlabel("v [mm/s]")
        axs[r, 0].set_ylabel(f"{Pw:.0f} W (η = 0.35)")
    axs[0, 0].legend(fontsize=7)
    fig.suptitle("Every output vs speed for the experiment beam (flat top r = 1.5 mm), ±3σ; markers with outline: "
                 "simulated U runs (1000 W only); shaded: planned speeds", x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT/"fig_experiment_all_outputs.png")
    plt.close(fig)


def dimensionless(runs, P, V, G):
    iw, idp, it, iu = (TARGET_NAMES.index(t) for t in ("width", "depth", "T_max", "U_surf"))
    mu = G["MaB"][0]
    Ma, Pe = derived_numbers(mu[..., it], mu[..., iw], mu[..., iu], 1)
    asp = mu[..., iw]/mu[..., idp]
    PP = np.broadcast_to(P[:, None], asp.shape)
    m = runs[runs.marangoni == 1]
    Ma_s, Pe_s = derived_numbers(m.qs_T_max_K, m.qs_width_mm, m.qs_U_surface_mean_m_s, 1)
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.8))
    for ax, (x, y, xs, ys, xl, yl) in zip(axs, [
            (Ma, asp, Ma_s, m.qs_width_mm/m.qs_depth_mm, "Ma", "aspect ratio width/depth"),
            (Ma, Pe, Ma_s, Pe_s, "Ma", "Pe (mean surface speed)")]):
        sc = ax.scatter(x.ravel(), y.ravel(), c=PP.ravel(), s=4, cmap="Blues", vmin=150, alpha=0.8, lw=0)
        for s, (c, mk, lab) in SET_STYLE.items():
            sel = m["set"] == s
            ax.scatter(xs[sel], np.asarray(ys)[sel], color=c, marker=mk, s=40, edgecolor=INK, lw=0.6, label=lab)
        ax.set_xscale("log")
        ax.set_xlabel(xl)
        ax.set_ylabel(yl)
        ax.set_yscale("log" if "Pe" in yl else "linear")
    fig.colorbar(sc, ax=axs[1], label="P_abs [W] of the model grid")
    axs[0].legend(fontsize=7)
    axs[0].set_title("Model (flat top, MaB, dots) vs simulated Marangoni runs", loc="left")
    axs[1].set_title("Convection strength vs Marangoni number", loc="left")
    fig.tight_layout()
    fig.savefig(OUT/"fig_dimensionless.png")
    plt.close(fig)


# ---------------------------------------------------------------- events
def events_cross_section(runs):
    ev = pd.read_csv(OUT/"event_predictions_holdout.csv.gz")
    cases = ["R09", "U2000_v6_MaB"]
    fig, axs = plt.subplots(len(cases), 4, figsize=(15, 5.8))
    for i, c in enumerate(cases):
        d = ev[(ev["case"] == c) & (ev.s_track_mm.between(S_STEADY - 0.3, S_STEADY + 0.3))]
        for k, (col, lab, cmap) in enumerate([("G_K_mm", "G sim", "Blues"), ("G_pred", "G pred", "Blues"),
                                              ("R_mm_s", "R sim", "Oranges"), ("R_pred", "R pred", "Oranges")]):
            ax = axs[i, k]
            base = "G_K_mm" if col.startswith("G") else "R_mm_s"
            pr = "G_pred" if base == "G_K_mm" else "R_pred"
            lo = np.percentile(np.r_[d[base], d[pr]], 2)
            hi = np.percentile(np.r_[d[base], d[pr]], 98)
            sc = ax.scatter(d.y_mm, d.z_mm, c=d[col], cmap=cmap, norm=LogNorm(lo, hi), s=14, marker="s", lw=0)
            ax.set_aspect("equal")
            ax.set_title(f"{c}: {lab} [{'K/mm' if base == 'G_K_mm' else 'mm/s'}]", loc="left", fontsize=9)
            fig.colorbar(sc, ax=ax, shrink=0.8)
            if i == len(cases) - 1:
                ax.set_xlabel("y [mm] (half section)")
            if k == 0:
                ax.set_ylabel("z [mm]")
    fig.suptitle(f"Holdout runs, events {S_STEADY - 0.3:.1f}–{S_STEADY + 0.3:.1f} mm from the track start, "
                 "simulated vs predicted", x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT/"fig_events_cross_section.png")
    plt.close(fig)


def events_error_position():
    ev = pd.read_csv(OUT/"event_predictions_holdout.csv.gz")
    eG = np.log10(ev.G_pred/ev.G_K_mm)
    eR = np.log10(ev.R_pred/ev.R_mm_s)
    fig, axs = plt.subplots(1, 3, figsize=(13, 3.6))
    for ax, (x, lab, bins) in zip(axs, [(ev.z_over_depth, "z / depth (0 top, 1 bottom)", np.linspace(0, 1.05, 15)),
                                        (ev.y_over_halfwidth, "y / half-width (0 centre, 1 edge)", np.linspace(0, 1.05, 15)),
                                        (ev.s_track_mm, "distance from track start [mm]", np.linspace(-1.5, 5, 14))]):
        idx = np.digitize(x, bins)
        cen = 0.5*(bins[1:] + bins[:-1])
        for e, c, nm in ((eG, SERIES[0], "G"), (eR, SERIES[1], "R")):
            med = [np.median(e[idx == b]) if (idx == b).sum() > 20 else np.nan for b in range(1, len(bins))]
            q1 = [np.percentile(e[idx == b], 25) if (idx == b).sum() > 20 else np.nan for b in range(1, len(bins))]
            q3 = [np.percentile(e[idx == b], 75) if (idx == b).sum() > 20 else np.nan for b in range(1, len(bins))]
            ax.fill_between(cen, q1, q3, color=c, alpha=0.18, lw=0)
            ax.plot(cen, med, color=c, marker="o", ms=4, label=f"{nm}: median, IQR")
        ax.axhline(0, color=INK, lw=0.8)
        ax.set_xlabel(lab)
    axs[0].set_ylabel("log10(pred / sim)")
    axs[0].legend(fontsize=7)
    fig.suptitle("Where the local G and R errors sit (holdout runs, every event)", x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT/"fig_events_error_position.png")
    plt.close(fig)


def experiment_solidification(rm, em):
    cases = [(Pw, v) for Pw in EXP_P for v in EXP_V[:2]]
    yy, zz = np.meshgrid(np.linspace(0.02, 1.0, 40), np.linspace(0.02, 1.0, 40))
    inside = (yy**2 + zz**2) <= 1.0
    fig, axs = plt.subplots(3, len(cases), figsize=(15, 8.5))
    gr = []
    for k, (Pw, v) in enumerate(cases):
        mu, _ = run_predict(rm, frame(ETA*Pw, v, "MaB"))
        W, D = mu[0, TARGET_NAMES.index("width")], mu[0, TARGET_NAMES.index("depth")]
        df = frame(np.full(inside.sum(), ETA*Pw), np.full(inside.sum(), v), "MaB")
        df["s_track_mm"] = S_STEADY
        df["y_over_halfwidth"] = yy[inside]
        df["z_over_depth"] = zz[inside]
        g = event_predict(em, df)
        gr.append((Pw, v, g, zz[inside]))
        y, z = yy[inside]*W/2, -zz[inside]*D
        for i, (val, lab, cmap) in enumerate([(g[:, 0], "G [K/mm]", "Blues"), (g[:, 1], "R [mm/s]", "Oranges"),
                                             (g[:, 0]*g[:, 1], "G·R [K/s]", "Purples")]):
            ax = axs[i, k]
            sc = ax.scatter(y, z, c=val, cmap=cmap, norm=LogNorm(val.min(), val.max()), s=10, marker="s", lw=0)
            ax.set_aspect("equal")
            fig.colorbar(sc, ax=ax, shrink=0.75)
            if i == 0:
                ax.set_title(f"{Pw:.0f} W, {v:.0f} mm/s\nW {W:.2f} mm, D {D:.2f} mm", loc="left", fontsize=9)
            if k == 0:
                ax.set_ylabel(f"{lab}\nz [mm]")
            if i == 2:
                ax.set_xlabel("y [mm]")
    fig.suptitle(f"Predicted solidification conditions in the pool cross-section, experiment cases (MaB, "
                 f"{S_STEADY} mm from the track start; section scaled by predicted width and depth)", x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT/"fig_experiment_solidification.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.2, 4.6))
    for k, (Pw, v, g, zd) in enumerate(gr):
        ax.scatter(g[:, 1], g[:, 0], s=6, color=SERIES[k], alpha=0.6, lw=0, label=f"{Pw:.0f} W, {v:.0f} mm/s")
    R = np.logspace(-2, 1.5, 50)
    for c in (1e2, 1e3, 1e4):
        ax.plot(R, c/R, color=MUTED, lw=0.7, ls=":")
        ax.text(R[-12], c/R[-12], f"G·R = {c:.0e} K/s", fontsize=6, color=MUTED, rotation=-30)
    for c in (1e2, 1e3, 1e4):
        ax.plot(R, c*R, color=MUTED, lw=0.7, ls="--")
        ax.text(R[8], c*R[8], f"G/R = {c:.0e} K s/mm²", fontsize=6, color=MUTED, rotation=30)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_ylim(2e2, 1e4)
    ax.set_xlim(1e-2, 3e1)
    ax.set_xlabel("R [mm/s]")
    ax.set_ylabel("G [K/mm]")
    ax.set_title("Predicted G–R map of the experiment cases (MaB)", loc="left")
    ax.legend(fontsize=7, markerscale=3)
    fig.savefig(OUT/"fig_experiment_GR_map.png")
    plt.close(fig)


def main():
    warnings.filterwarnings("ignore")
    runs = load_runs()
    oos = pd.read_csv(OUT/"run_predictions_oos.csv")
    rm, em = load("run_composite.pkl"), load("event_composite.pkl")
    coverage(runs)
    parity_by_algorithm(runs, oos)
    residuals(runs, oos)
    calibration(oos)
    P, V, G = grids(rm)
    process_maps(runs, P, V, G)
    marangoni_map(runs, P, V, G)
    uncertainty_map(runs, P, V, G)
    experiment_all_outputs(rm, runs)
    dimensionless(runs, P, V, G)
    events_cross_section(runs)
    events_error_position()
    experiment_solidification(rm, em)
    print("figures written to", OUT)


if __name__ == "__main__":
    main()
