#!/usr/bin/env python3
"""Post-process one finished case: time histories, melt-pool metrics and
field sections.

Writes to results/<case name>/:
    history.png     T_max, |U|_max and pool length/width/depth vs time
    3d_<t>s.png     mirrored full-block 3D view (scripts/export_3d.py, which
                    also writes cases/<case>/VTK_full/*.vtu for ParaView)
    sections_<t>.png   longitudinal (y = 0) and cross-section (x = beam)
                    cuts: temperature, solidus/liquidus, liquid fraction 0.5
                    and velocity vectors, mirrored to the full width
    contours_<t>s.png  pool close-up: 10 labelled isotherms with velocity
                    vectors, and velocity-magnitude contours in the melt
    velocity_profiles_<t>s.png  surface velocity along and across the pool,
                    horizontal velocity vs depth, vertical velocity under the beam
    summary.json    melting onset, quasi-steady averages, solidification time

Needs a reconstructed case (Allrun does this) and OpenFOAM in the
environment (source setup/env.sh) for the field sections.

Usage:
    python scripts/analyze_case.py cases/R01
    python scripts/analyze_case.py cases/R01 --no-sections     # history and summary only
    python scripts/analyze_case.py cases/R01 --sections-only   # only the 2D plots
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def read_dat(case, name):
    """volFieldValue output, concatenated over restart directories."""
    rows = []
    for f in sorted((case/"postProcessing"/name).glob("*/volFieldValue.dat"),
                    key=lambda p: float(p.parent.name)):
        rows.append(np.loadtxt(f, comments="#"))
    data = np.vstack(rows)
    return data[:, 0], data[:, 1]


def read_pool(case, iso):
    f = case/"postProcessing"/"meltPoolDimensions"/f"{iso:g}.csv"
    d = np.loadtxt(f, delimiter=",", skiprows=1)
    # columns: time, length, half width, depth
    return d[:, 0], d[:, 1], 2.0*d[:, 2], d[:, 3]


def solidus_liquidus(case):
    text = (case/"constant"/"transportProperties").read_text()
    body = re.search(r"^thermoPath\s*\((.*?)^\);", text, re.M | re.S).group(1)
    pts = np.array(re.findall(r"\(\s*([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*\)", body), float)
    return pts[:, 0].min(), pts[:, 0].max()


def scan(case):
    """Laser line segment from constant/scanPath: (x0, x1, speed, t_off)."""
    rows = [l.split() for l in (case/"constant"/"scanPath").read_text().splitlines()[1:] if l.strip()]
    x0 = float(rows[0][1])
    line = next(r for r in rows if r[0] == "0")
    x1, v = float(line[1]), float(line[5])
    return x0, x1, v, (x1 - x0)/v


def first(t, mask):
    i = np.flatnonzero(mask)
    return float(t[i[0]]) if i.size else None


def inputs(case):
    """Run inputs, read back from the case files themselves."""
    hs = (case/"constant"/"heatSourceDict").read_text()
    tp = (case/"constant"/"transportProperties").read_text()
    info = json.loads((case/"case_info.json").read_text())
    x0, x1, v, t_off = scan(case)
    power = float(next(l.split()[4] for l in (case/"constant"/"scanPath").read_text().splitlines()
                       if l.split()[:1] == ["0"]))

    def num(text, key):
        return float(re.search(rf"^\s*{key}\s+(?:\[[^\]]*\]\s+)?\(?([0-9.eE+-]+)", text, re.M).group(1))

    eta = num(hs, "eta")
    return {
        "cell_size_m": info["cell_size"],
        "n_cells": info["mesh"]["n_cells"],
        "laser_power_W": power,
        "absorptivity": eta,
        "absorbed_power_W": power*eta,
        "beam_radius_m": num(hs, "radius"),
        "source_depth_m": num(hs, "depth"),
        "scan_speed_m_s": v,
        "track_start_m": x0,
        "track_end_m": x1,
        "line_energy_J_m": power*eta/v,
        "dSigmadT_N_mK": num(tp, "dSigmadT"),
        "mu_Pa_s": num(tp, "mu"),
        "rho_kg_m3": num(tp, "rho"),
        "DAS_m": info["DAS"],
    }


def event_stats(d):
    """Median/p10/p90 of cooling rate, G, R, G/R, G*R and the pool bottom on
    the centreline, for solidification events d (columns x,y,z,ts,cr,gx,gy,gz,v)."""
    if len(d) == 0:
        return None
    G = np.linalg.norm(d[:, 5:8], axis=1)
    R = d[:, 8]
    ok = R > 0

    def q(a):
        return {"median": float(np.median(a)), "p10": float(np.percentile(a, 10)),
                "p90": float(np.percentile(a, 90))}

    # Pool bottom on the centreline: deepest events within one cell of y = 0
    centre = d[:, 1] < d[:, 1].min() + 1e-4
    bottom = centre & (d[:, 2] < d[centre, 2].min() + 1e-4) if centre.any() else centre
    return {
        "n_events": int(len(d)),
        "cooling_rate_K_s": q(d[:, 4]),
        "G_K_m": q(G),
        "R_m_s": q(R[ok]) if ok.any() else None,
        "G_over_R_Ks_m2": q(G[ok]/R[ok]) if ok.any() else None,
        "GR_K_s": q(G[ok]*R[ok]) if ok.any() else None,
        "pool_bottom_centreline": {
            "z_m": float(d[bottom, 2].mean()),
            "cooling_rate_K_s": float(d[bottom, 4].mean()),
            "G_K_m": float(G[bottom].mean()),
            "R_m_s": float(R[bottom].mean()),
        } if bottom.any() else None,
    }


def solidification(case, t_off):
    """AdditiveFOAM's solidification events, split by when they solidified:
    while the laser was on (the track behind the moving pool; the top-level
    statistics) and after it switched off (the end crater freezing at once,
    much faster R and lower G; under "crater"). Events are written only when
    a run ends, so a run resumed after an interruption keeps the earlier
    segment only if it was saved (solidification-data_part*.csv)."""
    files = sorted(case.glob("solidificationData/solidification-data*.csv")) \
        or sorted(case.glob("solidificationData/data_*.csv"))
    if not files:
        return None
    d = np.vstack([np.atleast_2d(np.loadtxt(f, delimiter=",", skiprows=1)) for f in files])
    on = d[:, 3] <= t_off
    track = event_stats(d[on]) or {}
    track["n_events_total"] = int(len(d))
    track["crater"] = event_stats(d[~on])
    return track


def run_name(case):
    """cases/mesh_200um -> mesh_200um; elsewhere prefix the parent folder."""
    return case.name if case.parent.name == "cases" else f"{case.parent.name}_{case.name}"


def history(case, out):
    Ts, Tl = solidus_liquidus(case)
    x0, x1, v, t_off = scan(case)
    tT, Tmax = read_dat(case, "Tmax")
    tU, Umax = read_dat(case, "Umax")
    tp, L, W, D = read_pool(case, Tl)
    tps, Ls, Ws, Ds = read_pool(case, Ts)

    # Quasi-steady window: last 40% of the time the laser was on (runs may
    # end before the laser stops, or have been stopped early)
    t_ref = min(t_off, tT[-1])
    lo = 0.6*t_ref
    win = (tp > lo) & (tp <= t_ref)
    winT = (tT > lo) & (tT <= t_ref)
    winU = (tU > lo) & (tU <= t_ref)

    def stat(a, m):
        return {"mean": float(a[m].mean()), "std": float(a[m].std())} if m.any() else None

    # Time series on the pool-dimension time base, for later fitting/optimisation
    np.savetxt(out/"timeseries.csv",
               np.column_stack([tp, np.interp(tp, tT, Tmax), np.interp(tp, tU, Umax),
                                L, W, D, np.interp(tp, tps, Ls),
                                np.interp(tp, tps, Ws), np.interp(tp, tps, Ds)]),
               delimiter=",", comments="",
               header="time_s,T_max_K,U_max_m_s,length_liq_m,width_full_liq_m,depth_liq_m,"
                      "length_sol_m,width_full_sol_m,depth_sol_m")

    after = tps > t_off
    summary = {
        "case": run_name(case),
        "case_path": str(case),
        "inputs": inputs(case),
        "solidus_K": Ts, "liquidus_K": Tl,
        "laser_off_s": t_off,
        "run_end_s": float(tT[-1]),
        "laser_on_at_end": bool(t_off > tT[-1]),
        "first_melting_s": first(tT, Tmax >= Ts),
        "fully_liquid_surface_s": first(tT, Tmax >= Tl),
        "pool_fully_solidified_s": first(tps[after], Ls[after] <= 0.0),
        "peak_T_K": float(Tmax.max()),
        "peak_U_m_s": float(Umax.max()),
        "quasi_steady_window_s": [lo, t_ref],
        "quasi_steady": {
            "T_max_K": stat(Tmax, winT),
            "U_max_m_s": stat(Umax, winU),
            "pool_length_mm": stat(L*1e3, win),
            "pool_width_full_mm": stat(W*1e3, win),
            "pool_depth_mm": stat(D*1e3, win),
        },
        "solidification": solidification(case, t_off),
    }

    fig, ax = plt.subplots(3, 1, figsize=(8, 9), sharex=True)
    ax[0].plot(tT, Tmax, lw=1)
    for T, name in ((Ts, "solidus"), (Tl, "liquidus")):
        ax[0].axhline(T, ls=":", lw=0.8, c="k")
        ax[0].text(tT[-1], T, f" {name}", va="center", fontsize=8)
    ax[0].set_ylabel("T_max [K]")
    ax[1].plot(tU, Umax, lw=1)
    ax[1].set_ylabel("|U|_max [m/s]")
    ax[2].plot(tp, L*1e3, label="length", lw=1)
    ax[2].plot(tp, W*1e3, label="width (full)", lw=1)
    ax[2].plot(tp, D*1e3, label="depth", lw=1)
    ax[2].set_ylabel(f"pool at liquidus {Tl:g} K [mm]")
    ax[2].set_xlabel("time [s]")
    ax[2].legend(fontsize=8)
    for a in ax:
        if t_off <= tT[-1]:
            a.axvline(t_off, c="r", lw=0.8, ls="--")
        a.axvspan(lo, t_ref, color="0.9", zorder=0)
        a.grid(alpha=0.3)
    ax[0].set_title(f"{run_name(case)}: laser off at {t_off:g} s (red), "
                    "quasi-steady window shaded", fontsize=9)
    fig.tight_layout()
    fig.savefig(out/"history.png", dpi=150)
    plt.close(fig)
    return summary


SECTIONS = """FoamFile {{ format ascii; class dictionary; object sections; }}
sections
{{
    type            surfaces;
    libs            ("libsampling.so");
    surfaceFormat   raw;
    interpolationScheme cellPoint;
    fields          (T U alpha.solid);
    surfaces
    {{
        longitudinal {{ type cutPlane; point (0 1e-6 0); normal (0 1 0); interpolate false; }}
        crossSection {{ type cutPlane; point ({x:.6g} 0 0); normal (1 0 0); interpolate false; }}
    }}
}}
"""


def arrows(ax, x, z, u, w, sel, max_len_mm=0.35, n_max=120, color="w"):
    """Velocity arrows in the melt, at most n_max of them, the fastest
    max_len_mm long (in plot units, mm), so they stay inside small pools."""
    idx = np.flatnonzero(sel)
    if idx.size == 0:
        return
    idx = idx[::max(1, idx.size//n_max)]
    vmax = float(np.hypot(u[idx], w[idx]).max()) or 1.0
    ax.quiver(x[idx], z[idx], u[idx], w[idx], color=color, angles="xy",
              scale_units="xy", scale=vmax/max_len_mm, width=0.003)
    ax.text(0.99, 0.02, f"longest arrow = {vmax:.2f} m/s", color=color, fontsize=7,
            ha="right", va="bottom", transform=ax.transAxes)


def read_raw(f):
    cols = open(f).readline().lstrip("#").split()
    return dict(zip(cols, np.loadtxt(f, comments="#").T))


def panel(ax, h, z, T, alpha, uh, uz, levels, Ts, Tl, lims, with_arrows):
    """One section: temperature, solidus/liquidus, 50 % liquid, arrows."""
    tri = mtri.Triangulation(h, z)
    c = ax.tricontourf(tri, T, levels=levels, cmap="inferno")
    ax.tricontour(tri, T, levels=[Ts, Tl], colors=["c", "w"], linewidths=0.8)
    if alpha is not None:
        ax.tricontour(tri, alpha, levels=[0.5], colors="lime", linewidths=0.6)
    if with_arrows:
        (h_lo, h_hi), (z_lo, _) = lims
        sel = (T > Ts) & (h > h_lo) & (h < h_hi) & (z > z_lo)
        arrows(ax, h, z, uh, uz, sel, max_len_mm=0.12*(h_hi - h_lo))
    ax.set_xlim(*lims[0])
    ax.set_ylim(*lims[1])
    ax.set_aspect("equal")
    return c


def frame(h, z, mask, margin_h, margin_z, h_rng, z_min, fallback):
    """Axis limits around the cells in mask, clipped to the section."""
    if not mask.any():
        return fallback
    return ((max(h_rng[0], h[mask].min() - margin_h), min(h_rng[1], h[mask].max() + margin_h)),
            (max(z_min, z[mask].min() - margin_z), 0.0))


def sections(case, out, times):
    """2 x 2 figure per time: longitudinal cut (y = 0) and cross-section at
    the beam (mirrored to the full width); left column the whole heated zone
    (T > 500 K, gradient fading to ambient), right column the melt pool close
    up (T > solidus) with velocity arrows."""
    Ts, Tl = solidus_liquidus(case)
    x0, x1, v, t_off = scan(case)
    for t in times:
        xb = x0 + v*min(t, t_off)
        x_cut = xb if t <= t_off else x1 - 1e-3
        (case/"system"/"sections").write_text(SECTIONS.format(x=x_cut))
        subprocess.run(["foamPostProcess", "-case", str(case), "-dict", "system/sections",
                        "-time", t_name(case, t)], check=True, capture_output=True)
        d = case/"postProcessing"/"sections"/t_name(case, t)
        lon, crs = read_raw(d/"longitudinal.xy"), read_raw(d/"crossSection.xy")

        xl, zl = lon["face_x"]*1e3, lon["face_z"]*1e3
        y = np.concatenate([crs["face_y"], -crs["face_y"]])*1e3
        zc = np.concatenate([crs["face_z"], crs["face_z"]])*1e3
        Tc = np.concatenate([crs["T"], crs["T"]])
        Uy = np.concatenate([crs["U_y"], -crs["U_y"]])
        Uz = np.concatenate([crs["U_z"], crs["U_z"]])
        al = lon.get("alpha.solid")
        ac = np.concatenate([crs["alpha.solid"]]*2) if "alpha.solid" in crs else None
        levels = np.linspace(293, max(Tl + 50, lon["T"].max(), Tc.max()), 30)
        x_rng, y_rng = (xl.min(), xl.max()), (-np.abs(y).max(), np.abs(y).max())

        fallback_l = ((xb*1e3 - 3, xb*1e3 + 3), (-2.0, 0.0))
        fallback_c = ((-3.0, 3.0), (-2.0, 0.0))
        lims = {
            "lon_hot": frame(xl, zl, lon["T"] > 500, 1.0, 0.5, x_rng, zl.min(), fallback_l),
            "crs_hot": frame(y, zc, Tc > 500, 1.0, 0.5, y_rng, zc.min(), fallback_c),
            "lon_pool": frame(xl, zl, lon["T"] > Ts, 0.4, 0.25, x_rng, zl.min(), fallback_l),
            "crs_pool": frame(y, zc, Tc > Ts, 0.4, 0.25, y_rng, zc.min(), fallback_c),
        }
        fig, ax = plt.subplots(2, 2, figsize=(14, 7.5),
                               gridspec_kw={"width_ratios": [1.3, 1]})
        state = f"t = {t:g} s, beam at x = {xb*1e3:.1f} mm{' (laser off)' if t > t_off else ''}"
        for row, (h, z, T, a, uh, uz, key, name) in enumerate((
                (xl, zl, lon["T"], al, lon["U_x"], lon["U_z"], "lon", "symmetry plane y = 0"),
                (y, zc, Tc, ac, Uy, Uz, "crs", f"cross-section x = {x_cut*1e3:.1f} mm"))):
            c = panel(ax[row, 0], h, z, T, a, uh, uz, levels, Ts, Tl, lims[key + "_hot"], False)
            panel(ax[row, 1], h, z, T, a, uh, uz, levels, Ts, Tl, lims[key + "_pool"], True)
            ax[row, 0].set_title(f"{name}: heated zone", fontsize=9)
            ax[row, 1].set_title(f"{name}: melt pool and flow", fontsize=9)
            for col in (0, 1):
                ax[row, col].set_ylabel("z [mm]")
                ax[row, col].set_xlabel("x [mm]" if row == 0
                                        else "y [mm] (mirrored about y = 0)")
            fig.colorbar(c, ax=ax[row, :].tolist(), label="T [K]", shrink=0.9)
        fig.suptitle(f"{state}   (cyan solidus, white liquidus, green 50 % liquid)",
                     fontsize=10)
        fig.savefig(out/f"sections_{t:g}s.png", dpi=150)
        plt.close(fig)

        if max(lon["T"].max(), Tc.max()) > Tl:          # only while there is a pool
            sec = {"lon": (xl, zl, lon["T"], lon["U_x"], lon["U_z"]),
                   "crs": (y, zc, Tc, Uy, Uz)}
            contours(sec, Ts, Tl, state, x_cut, out/f"contours_{t:g}s.png")
            velocity_profiles(sec, Ts, xb*1e3, state, x_cut, out/f"velocity_profiles_{t:g}s.png")


def contours(sec, Ts, Tl, state, x_cut, png, n_levels=10):
    """Melt-pool close-up, symmetry plane (top) and cross-section through the
    beam (bottom). Left: n_levels labelled isotherms between the coolest
    point in the window and the peak temperature, solidus and liquidus,
    velocity vectors. Right: velocity magnitude contours in the melt, vectors."""
    fig, axs = plt.subplots(2, 2, figsize=(16, 6.5), layout="constrained")
    U_hi = max(np.hypot(sec[k][3], sec[k][4])[sec[k][2] > Ts].max(initial=0.0) for k in sec) or 1.0
    u_levels = np.linspace(0.0, U_hi, n_levels + 1)
    for row, key, name in ((0, "lon", "symmetry plane y = 0"),
                           (1, "crs", f"cross-section x = {x_cut*1e3:.1f} mm")):
        h, z, T, uh, uz = sec[key]
        tri = mtri.Triangulation(h, z)
        pool = T > Ts
        span_h = np.ptp(h[pool]) if pool.any() else 2.0
        lims = frame(h, z, pool, 0.25*span_h, 0.6*np.ptp(z[pool]) if pool.any() else 0.5,
                     (h.min(), h.max()), z.min(), ((h.min(), h.max()), (-2.0, 0.0)))
        (h_lo, h_hi), (z_lo, _) = lims
        win = (h > h_lo) & (h < h_hi) & (z > z_lo)
        t_levels = np.linspace(T[win].min(), T[win].max(), n_levels + 2)[1:-1]
        sel = pool & win
        U = np.hypot(uh, uz)

        ax = axs[row, 0]
        cf = ax.tricontourf(tri, T, levels=np.linspace(T[win].min(), T[win].max(), 41), cmap="inferno")
        cl = ax.tricontour(tri, T, levels=t_levels, colors="k", linewidths=0.6)
        ax.clabel(cl, fmt="%.0f", fontsize=7, inline=True)
        ax.tricontour(tri, T, levels=[Ts, Tl], colors=["c", "w"], linewidths=1.2)
        arrows(ax, h, z, uh, uz, sel, max_len_mm=0.06*(h_hi - h_lo), n_max=70)
        fig.colorbar(cf, ax=ax, label="T [K]", format="%.0f", fraction=0.04)
        ax.set_title(f"{name}: {n_levels} isotherms ({t_levels[1] - t_levels[0]:.0f} K apart)", fontsize=9)

        ax = axs[row, 1]
        tri_u = mtri.Triangulation(h, z)
        tri_u.set_mask(~pool[tri_u.triangles].all(axis=1))       # melt only
        cf = ax.tricontourf(tri_u, U, levels=u_levels, cmap="viridis")
        ax.tricontour(tri, T, levels=[Ts], colors="k", linewidths=1.0)
        arrows(ax, h, z, uh, uz, sel, max_len_mm=0.06*(h_hi - h_lo), n_max=70, color="k")
        fig.colorbar(cf, ax=ax, label="|U| [m/s]", format="%.3g", fraction=0.04)
        ax.set_title(f"{name}: melt velocity (black: solidus)", fontsize=9)

        for ax in axs[row]:
            ax.set_xlim(*lims[0])
            ax.set_ylim(*lims[1])
            ax.set_aspect("equal")
            ax.set_facecolor("#d9d9d9")
            ax.set_ylabel("z [mm]")
            ax.set_xlabel("x [mm]" if key == "lon" else "y [mm] (mirrored about y = 0)")
    fig.suptitle(f"{state}: temperature (cyan solidus, white liquidus) and velocity in the melt pool",
                 fontsize=10)
    fig.savefig(png, dpi=150)
    plt.close(fig)


def velocity_profiles(sec, Ts, xb_mm, state, x_cut, png, n=200):
    """Velocity along lines through the pool, interpolated from the section
    data: surface velocity along the centreline and across the track,
    horizontal velocity against depth at 25/50/75 % of the half width, and
    vertical velocity against depth under the beam. Only molten points."""
    def sampler(key):
        h, z, T, uh, uz = sec[key]
        tri = mtri.Triangulation(h, z)
        f = {k: mtri.LinearTriInterpolator(tri, v) for k, v in (("T", T), ("uh", uh), ("uz", uz))}
        return lambda hh, zz: {k: np.ma.filled(g(hh, zz), np.nan) for k, g in f.items()}

    lon, crs = sampler("lon"), sampler("crs")
    z_top = min(sec["lon"][1].max(), sec["crs"][1].max())     # first cell centre below the surface
    pool_l = sec["lon"][2] > Ts
    pool_c = sec["crs"][2] > Ts
    if not (pool_l.any() and pool_c.any()):
        return
    x_lo, x_hi = sec["lon"][0][pool_l].min(), sec["lon"][0][pool_l].max()
    half_w = np.abs(sec["crs"][0][pool_c]).max()
    depth = -sec["crs"][1][pool_c].min()
    fig, axs = plt.subplots(2, 2, figsize=(11, 7.5))

    xs = np.linspace(x_lo - 0.1, x_hi + 0.1, n)
    s = lon(xs, np.full(n, z_top))
    m = s["T"] > Ts
    ax = axs[0, 0]
    ax.plot(xs[m], s["uh"][m], color="#2a78d6")
    ax.axhline(0, color="#52514e", linewidth=0.8)
    ax.axvline(xb_mm, color="#e34948", linestyle="--", linewidth=1)
    ax.set(xlabel="x [mm] (dashed: beam centre)", ylabel="u_x [m/s]",
           title="Surface velocity along the centreline (y = 0)")

    ys = np.linspace(-half_w - 0.1, half_w + 0.1, n)
    s = crs(ys, np.full(n, z_top))
    m = s["T"] > Ts
    ax = axs[0, 1]
    ax.plot(ys[m], s["uh"][m], color="#2a78d6")
    ax.axhline(0, color="#52514e", linewidth=0.8)
    ax.set(xlabel="y [mm]", ylabel="u_y [m/s]",
           title=f"Surface velocity across the pool (x = {x_cut*1e3:.1f} mm)")

    zs = np.linspace(z_top, -depth - 0.05, n)
    ax = axs[1, 0]
    for frac, color in ((0.25, "#86b6ef"), (0.5, "#2a78d6"), (0.75, "#0d366b")):
        s = crs(np.full(n, frac*half_w), zs)
        m = s["T"] > Ts
        ax.plot(s["uh"][m], zs[m], color=color, label=f"y = {frac*half_w:.2f} mm ({frac:.0%} of half width)")
    ax.axvline(0, color="#52514e", linewidth=0.8)
    ax.set(xlabel="u_y (outward +) [m/s]", ylabel="z [mm]",
           title="Horizontal velocity against depth")
    ax.legend(fontsize=8, loc="lower right")

    s = crs(np.zeros(n), zs)
    m = s["T"] > Ts
    ax = axs[1, 1]
    ax.plot(s["uz"][m], zs[m], color="#2a78d6")
    ax.axvline(0, color="#52514e", linewidth=0.8)
    ax.set(xlabel="u_z (upward +) [m/s]", ylabel="z [mm]",
           title=f"Vertical velocity on the centreline (x = {x_cut*1e3:.1f} mm)")
    fig.suptitle(f"{state}: velocity profiles in the melt pool (T > solidus)", fontsize=10)
    fig.tight_layout()
    fig.savefig(png, dpi=150)
    plt.close(fig)


def written_times(case):
    ts = []
    for p in case.iterdir():
        try:
            if p.is_dir() and float(p.name) > 0 and (p/"T").exists():
                ts.append(float(p.name))
        except ValueError:
            pass
    return sorted(ts)


def t_name(case, t):
    return next(p.name for p in case.iterdir() if p.is_dir() and _isfloat(p.name) and float(p.name) == t)


def _isfloat(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("case", type=Path)
    p.add_argument("--no-sections", action="store_true", help="skip the field sections")
    p.add_argument("--no-3d", action="store_true",
                   help="skip the mirrored full-block 3D export (scripts/export_3d.py)")
    p.add_argument("--times", type=float, nargs="*", help="section times (default: all written)")
    p.add_argument("--sections-only", action="store_true",
                   help="only redraw the sections, isotherm contours and velocity profiles")
    args = p.parse_args()

    case = args.case.resolve()
    out = ROOT/"results"/run_name(case)
    out.mkdir(parents=True, exist_ok=True)

    if args.sections_only:
        sections(case, out, args.times or written_times(case))
        print(f"wrote {out.relative_to(ROOT)}")
        return

    summary = history(case, out)
    (out/"summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))

    if not args.no_sections:
        sections(case, out, args.times or written_times(case))
    if not (args.no_sections or args.no_3d):
        cmd = [sys.executable, str(ROOT/"scripts"/"export_3d.py"), str(case)]
        if args.times:
            cmd += ["--times"] + [f"{t:g}" for t in args.times]
        subprocess.run(cmd, check=True)
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
