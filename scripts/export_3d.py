#!/usr/bin/env python3
"""Full-block 3D snapshots: mirror the half-model fields at the symmetry
plane y = 0 and write them for ParaView, plus a rendered 3D image.

For every selected write time of a reconstructed case:
    results/<case>/marangoni_snapshots.csv  surface Marangoni quantities per
                                           snapshot (marangoni_metrics)
    cases/<case>/VTK_full/<case>_<t>.vtu    full block (both halves), cell data
                                           T, U, alpha.solid, liquid_fraction
    results/<case>/3d_<t>s.png              cut-away view: temperature on the
                                           block surfaces and on a cross-section
                                           through the beam, melt-pool surface
                                           (50 % liquid) and the beam position

The .vtu files are large (~25 MB each) and stay in the case directory.
Needs OpenFOAM in the environment (source setup/env.sh) and pyvista.

Usage:
    python scripts/export_3d.py cases/R01                 # every write time
    python scripts/export_3d.py cases/R01 --times 2 5     # selected times
    python scripts/export_3d.py cases/R01 --no-vtu        # images only
"""

import argparse
import subprocess
from pathlib import Path

import numpy as np
import pyvista as pv

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("T", "U", "alpha.solid")


def run_name(case):
    """cases/R01 -> R01; elsewhere prefix the parent folder (as analyze_case)."""
    return case.name if case.parent.name == "cases" else f"{case.parent.name}_{case.name}"


def written_times(case):
    out = []
    for p in case.iterdir():
        try:
            if p.is_dir() and float(p.name) > 0 and (p/"T").exists():
                out.append(p.name)
        except ValueError:
            pass
    return sorted(out, key=float)


def scan(case):
    rows = [l.split() for l in (case/"constant"/"scanPath").read_text().splitlines()[1:] if l.strip()]
    x0 = float(rows[0][1])
    line = next(r for r in rows if r[0] == "0")
    x1, v = float(line[1]), float(line[5])
    return x0, x1, v


def solidus_liquidus(case):
    import re
    text = (case/"constant"/"transportProperties").read_text()
    body = re.search(r"^thermoPath\s*\((.*?)^\);", text, re.M | re.S).group(1)
    T = [float(a) for a, _ in re.findall(r"\(\s*([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*\)", body)]
    return min(T), max(T)


def half_mesh(case, tname):
    """Internal mesh with cell data at one time, via foamToVTK."""
    subprocess.run(["foamToVTK", "-case", str(case), "-time", tname, "-useTimeName",
                    "-fields", "(" + " ".join(FIELDS) + ")", "-noPointValues",
                    "-noFaceZones", "-excludePatches", "(\".*\")"],
                   check=True, capture_output=True)
    f = next((case/"VTK").glob(f"*_{tname}.vtk"))
    mesh = pv.read(f)
    f.unlink()
    return mesh


def mirror(half):
    """Reflect at y = 0 and merge; U_y changes sign in the mirrored half."""
    other = half.reflect((0, 1, 0), point=(0, 0, 0))
    U = other.cell_data["U"].copy()
    U[:, 1] *= -1
    other.cell_data["U"] = U
    full = half.merge(other)
    full.cell_data["liquid_fraction"] = 1.0 - full.cell_data["alpha.solid"]
    return full


def material(case):
    """dSigmadT [N/m K] and mu [Pa s] as the solver reads them."""
    import re
    text = (case/"constant"/"transportProperties").read_text()

    def num(key):
        return float(re.search(rf"^{key}\s+(?:\[[^\]]*\]\s+)?([0-9.eE+-]+);", text, re.M).group(1))
    return num("dSigmadT"), num("mu")


def marangoni_metrics(half, dSigmadT, mu):
    """Marangoni quantities on the molten top surface of the half model:
    surface temperature gradient |grad_s T|, the thermocapillary shear the
    solver applies tau = |dSigma/dT| fL |grad_s T| (Farzadi 2008 Eq. 6;
    marangoni BC with our liquid-fraction patch), surface speed, and the
    flow direction relative to the hottest surface point (+1 all outward,
    -1 all inward)."""
    cc = half.cell_centers().points
    top = np.isclose(cc[:, 2], cc[:, 2].max())
    fL = 1.0 - half.cell_data["alpha.solid"]
    grad = half.cell_data_to_point_data().compute_derivative(scalars="T", gradient="gradT")
    gT = grad.point_data_to_cell_data().cell_data["gradT"]
    liq = top & (fL > 0.5)
    out = {"surface_liquid_area_mm2": 0.0, "gradT_surface_max_K_mm": 0.0,
           "gradT_surface_mean_K_mm": 0.0, "marangoni_stress_max_Pa": 0.0,
           "marangoni_stress_mean_Pa": 0.0, "U_surface_max_m_s": 0.0,
           "U_surface_mean_m_s": 0.0, "surface_flow_direction": 0.0,
           "dSigmadT_N_mK": dSigmadT}
    if not liq.any():
        return out
    gs = np.hypot(gT[liq, 0], gT[liq, 1])
    tau = abs(dSigmadT)*fL[liq]*gs
    U = half.cell_data["U"][liq]
    us = np.hypot(U[:, 0], U[:, 1])
    hot = cc[top][np.argmax(half.cell_data["T"][top])]
    r = cc[liq, :2] - hot[:2]
    rn = np.linalg.norm(r, axis=1)
    m = (rn > 0) & (us > 1e-6)
    direction = float(np.mean(np.sum(U[m, :2]*r[m], axis=1)/(rn[m]*us[m]))) if m.any() else 0.0
    dx = np.cbrt(half.compute_cell_sizes(length=False, area=False).cell_data["Volume"][liq])
    out.update({
        "surface_liquid_area_mm2": float(2*np.sum(dx**2)*1e6),   # both halves
        "gradT_surface_max_K_mm": float(gs.max()*1e-3),
        "gradT_surface_mean_K_mm": float(gs.mean()*1e-3),
        "marangoni_stress_max_Pa": float(tau.max()),
        "marangoni_stress_mean_Pa": float(tau.mean()),
        "U_surface_max_m_s": float(us.max()),
        "U_surface_mean_m_s": float(us.mean()),
        "surface_flow_direction": direction,
    })
    return out


def render(full, png, t, xb, laser_on, T_sol, T_liq):
    """Cut-away 3D view around the melt pool: the quadrant in front of the
    viewer (y < 0, x > beam) is removed, so the cross-section through the
    beam and the symmetry plane show the temperature inside the part."""
    pv.OFF_SCREEN = True
    b = full.bounds
    # frame the heated zone (T > 500 K) plus a margin
    cc_all = full.cell_centers().points
    hot = cc_all[full.cell_data["T"] > 500.0]
    if len(hot):
        lo_x, hi_x = max(b[0], hot[:, 0].min() - 1e-3), min(b[1], hot[:, 0].max() + 1e-3)
        w = min(b[3], np.abs(hot[:, 1]).max() + 1e-3)
        lo_z = max(b[4], hot[:, 2].min() - 1e-3)
    else:
        lo_x, hi_x, w, lo_z = xb - 3e-3, xb + 3e-3, 3e-3, -2e-3
    roi = full.clip_box((lo_x, hi_x, -w, w, lo_z, b[5]), invert=False)
    size = max(hi_x - lo_x, 2*w)
    centre = (0.5*(lo_x + hi_x), 0.0, 0.3*lo_z)
    cc = roi.cell_centers().points
    keep = ~((cc[:, 1] < 0) & (cc[:, 0] > xb))
    block = roi.extract_cells(np.flatnonzero(keep))
    big = 1.0
    cut = (xb, big, -big, 0.0, -big, big)          # removed quadrant
    pool = roi.cell_data_to_point_data().contour([0.5], scalars="liquid_fraction")
    if pool.n_points:
        pool = pool.clip_box(cut, invert=True)
    # solidus / liquidus outlines on the visible faces (incl. the cut faces)
    skin = block.extract_surface().cell_data_to_point_data()
    outlines = skin.contour([T_sol, T_liq], scalars="T")

    T_hi = max(T_liq + 100.0, float(np.nanmax(full.cell_data["T"])))
    p = pv.Plotter(off_screen=True, window_size=(1400, 900))
    p.add_mesh(block, scalars="T", cmap="inferno", clim=(293, T_hi),
               ambient=0.35, diffuse=0.7,
               scalar_bar_args={"title": "Temperature [K]", "vertical": True,
                                "position_x": 0.86, "position_y": 0.25,
                                "width": 0.05, "height": 0.5, "fmt": "%.0f",
                                "title_font_size": 14, "label_font_size": 12})
    if pool.n_points:
        p.add_mesh(pool, color="cyan", opacity=0.45, smooth_shading=True)
    if outlines.n_points:
        p.add_mesh(outlines, color="cyan", line_width=3,
                   label="melt pool edge")
    if laser_on:
        h = 0.2*size
        p.add_mesh(pv.Cone(center=(xb, 0, h/2), direction=(0, 0, -1),
                           height=h, radius=0.12*h), color="red", label="laser")
    if laser_on or outlines.n_points:      # nothing labelled once all is solid
        p.add_legend(bcolor="white", face=None, size=(0.16, 0.07), loc="lower center")
    p.add_text(f"t = {t:g} s, beam at x = {xb*1e3:.1f} mm"
               f"{'' if laser_on else ' (laser off)'}\n"
               "full width (mirrored at y = 0), front quadrant cut away",
               font_size=11)
    p.camera_position = [(centre[0] + 0.9*size, -2.1*size, 1.2*size), centre, (0, 0, 1)]
    p.show_axes()
    p.screenshot(png)
    p.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("case", type=Path)
    ap.add_argument("--times", nargs="*", help="write times (default: all)")
    ap.add_argument("--no-vtu", action="store_true", help="only render images")
    args = ap.parse_args()

    case = args.case.resolve()
    out = ROOT/"results"/run_name(case)
    out.mkdir(parents=True, exist_ok=True)
    vtu_dir = case/"VTK_full"
    T_sol, T_liq = solidus_liquidus(case)
    x0, x1, v = scan(case)
    t_off = (x1 - x0)/v

    dSigmadT, mu = material(case)
    rows = []
    names = written_times(case)
    if args.times:
        want = {float(t) for t in args.times}
        names = [n for n in names if float(n) in want]
    for tname in names:
        t = float(tname)
        half = half_mesh(case, tname)
        rows.append({"time_s": t, "laser_on": int(t <= t_off), **marangoni_metrics(half, dSigmadT, mu)})
        full = mirror(half)
        if not args.no_vtu:
            vtu_dir.mkdir(exist_ok=True)
            full.save(vtu_dir/f"{run_name(case)}_{tname}.vtu")
        render(full, out/f"3d_{t:g}s.png", t, x0 + v*min(t, t_off), t <= t_off, T_sol, T_liq)
        print(f"{tname}: {full.n_cells} cells")
    if rows:
        import csv
        f = out/"marangoni_snapshots.csv"
        old = list(csv.DictReader(open(f))) if f.exists() else []
        keep = {float(r["time_s"]): r for r in old}
        keep.update({r["time_s"]: r for r in rows})
        with open(f, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(keep[k] for k in sorted(keep))
    print(f"images -> {out.relative_to(ROOT)}" + ("" if args.no_vtu else f", VTK -> {vtu_dir}"))


if __name__ == "__main__":
    main()
