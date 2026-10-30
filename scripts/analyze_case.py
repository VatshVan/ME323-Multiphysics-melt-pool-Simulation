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
    summary.json    melting onset, quasi-steady averages, solidification time

Needs a reconstructed case (Allrun does this) and OpenFOAM in the
environment (source setup/env.sh) for the field sections.

Usage:
    python scripts/analyze_case.py cases/mesh_200um
    python scripts/analyze_case.py cases/mesh_200um --no-sections
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


def solidification(case, x_lo, x_hi):
    """Statistics of AdditiveFOAM's solidification events (x,y,z,ts,cr,G,v)
    for x_lo < x < x_hi. Written only when a run ends, so a run that was
    resumed after an interruption has events from its last segment only."""
    files = sorted(case.glob("solidificationData/solidification-data*.csv")) \
        or sorted(case.glob("solidificationData/data_*.csv"))
    if not files:
        return None
    d = np.vstack([np.atleast_2d(np.loadtxt(f, delimiter=",", skiprows=1)) for f in files])
    d = d[(d[:, 0] > x_lo) & (d[:, 0] < x_hi)]
    if d.size == 0:
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
        # events along the part of the track the beam covered
        "solidification": solidification(case, x0, x0 + v*t_ref),
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


def read_raw(f):
    cols = open(f).readline().lstrip("#").split()
    return dict(zip(cols, np.loadtxt(f, comments="#").T))


def sections(case, out, times):
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

        fig, ax = plt.subplots(2, 1, figsize=(9, 7.5))
        levels = np.linspace(293, max(Tl + 50, lon["T"].max()), 30)
        # longitudinal y = 0: x along track, z depth
        tri = mtri.Triangulation(lon["face_x"]*1e3, lon["face_z"]*1e3)
        c = ax[0].tricontourf(tri, lon["T"], levels=levels, cmap="inferno")
        ax[0].tricontour(tri, lon["T"], levels=[Ts, Tl], colors=["c", "w"], linewidths=0.8)
        if "alpha.solid" in lon:
            ax[0].tricontour(tri, lon["alpha.solid"], levels=[0.5], colors="lime", linewidths=0.6)
        sel = lon["T"] > Ts
        ax[0].quiver(lon["face_x"][sel]*1e3, lon["face_z"][sel]*1e3,
                     lon["U_x"][sel], lon["U_z"][sel], color="w", scale=3, width=0.002)
        # frame the heated zone (T > 500 K) plus a margin, so the gradient
        # is seen fading out to cold material
        hot = lon["T"] > 500.0
        if hot.any():
            x_lo, x_hi = lon["face_x"][hot].min()*1e3 - 1, lon["face_x"][hot].max()*1e3 + 1
            z_lo = lon["face_z"][hot].min()*1e3 - 0.5
        else:
            x_lo, x_hi, z_lo = xb*1e3 - 3, xb*1e3 + 3, -2
        ax[0].set_xlim(max(lon["face_x"].min()*1e3, x_lo), min(lon["face_x"].max()*1e3, x_hi))
        ax[0].set_ylim(max(lon["face_z"].min()*1e3, z_lo), 0)
        ax[0].set_aspect("equal")
        ax[0].set_xlabel("x [mm]")
        ax[0].set_ylabel("z [mm]")
        ax[0].set_title(f"t = {t:g} s, beam at x = {xb*1e3:.1f} mm"
                        f"{' (laser off)' if t > t_off else ''}: symmetry plane y = 0", fontsize=9)
        fig.colorbar(c, ax=ax[0], label="T [K]")

        # cross-section at the beam, mirrored to the full width
        y = np.concatenate([crs["face_y"], -crs["face_y"]])*1e3
        z = np.concatenate([crs["face_z"], crs["face_z"]])*1e3
        T = np.concatenate([crs["T"], crs["T"]])
        Uy = np.concatenate([crs["U_y"], -crs["U_y"]])
        Uz = np.concatenate([crs["U_z"], crs["U_z"]])
        tri = mtri.Triangulation(y, z)
        c = ax[1].tricontourf(tri, T, levels=levels, cmap="inferno")
        ax[1].tricontour(tri, T, levels=[Ts, Tl], colors=["c", "w"], linewidths=0.8)
        if "alpha.solid" in crs:
            ax[1].tricontour(tri, np.concatenate([crs["alpha.solid"]]*2), levels=[0.5],
                             colors="lime", linewidths=0.6)
        sel = T > Ts
        ax[1].quiver(y[sel], z[sel], Uy[sel], Uz[sel], color="w", scale=3, width=0.002)
        hot = T > 500.0
        y_hi = (np.abs(y[hot]).max() + 1) if hot.any() else 3
        z_lo = (z[hot].min() - 0.5) if hot.any() else -2
        ax[1].set_xlim(-min(y_hi, np.abs(y).max()), min(y_hi, np.abs(y).max()))
        ax[1].set_ylim(max(z.min(), z_lo), 0)
        ax[1].set_aspect("equal")
        ax[1].set_xlabel("y [mm] (mirrored about the symmetry plane)")
        ax[1].set_ylabel("z [mm]")
        ax[1].set_title(f"cross-section x = {x_cut*1e3:.1f} mm "
                        "(cyan solidus, white liquidus, green 50% liquid)", fontsize=9)
        fig.colorbar(c, ax=ax[1], label="T [K]")
        fig.tight_layout()
        fig.savefig(out/f"sections_{t:g}s.png", dpi=150)
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
    args = p.parse_args()

    case = args.case.resolve()
    out = ROOT/"results"/run_name(case)
    out.mkdir(parents=True, exist_ok=True)

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
