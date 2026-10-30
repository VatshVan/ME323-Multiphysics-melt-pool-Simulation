#!/usr/bin/env python3
"""Full-block 3D snapshots: mirror the half-model fields at the symmetry
plane y = 0 and write them for ParaView, plus a rendered 3D image.

For every selected write time of a reconstructed case:
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


def render(full, png, t, xb, laser_on, T_sol, T_liq):
    """Cut-away 3D view around the melt pool: the quadrant in front of the
    viewer (y < 0, x > beam) is removed, so the cross-section through the
    beam and the symmetry plane show the temperature inside the part."""
    pv.OFF_SCREEN = True
    b = full.bounds
    lo_x, hi_x = max(b[0], xb - 12e-3), min(b[1], xb + 6e-3)
    roi = full.clip_box((lo_x, hi_x, -7e-3, 7e-3, -5e-3, b[5]), invert=False)
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
                                "position_x": 0.9, "position_y": 0.25,
                                "width": 0.05, "height": 0.5, "fmt": "%.0f",
                                "title_font_size": 14, "label_font_size": 12})
    if pool.n_points:
        p.add_mesh(pool, color="cyan", opacity=0.45, smooth_shading=True)
    if outlines.n_points:
        p.add_mesh(outlines, color="cyan", line_width=3,
                   label="melt pool edge")
    if laser_on:
        p.add_mesh(pv.Cone(center=(xb, 0, 2e-3), direction=(0, 0, -1),
                           height=4e-3, radius=0.5e-3), color="red", label="laser")
    if laser_on or outlines.n_points:      # nothing labelled once all is solid
        p.add_legend(bcolor="white", face=None, size=(0.16, 0.07), loc="lower center")
    p.add_text(f"t = {t:g} s, beam at x = {xb*1e3:.1f} mm"
               f"{'' if laser_on else ' (laser off)'}\n"
               "full width (mirrored at y = 0), front quadrant cut away",
               font_size=11)
    p.camera_position = [(xb + 10e-3, -24e-3, 14e-3), (xb - 3e-3, 0, -1.5e-3), (0, 0, 1)]
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

    names = written_times(case)
    if args.times:
        want = {float(t) for t in args.times}
        names = [n for n in names if float(n) in want]
    for tname in names:
        t = float(tname)
        full = mirror(half_mesh(case, tname))
        if not args.no_vtu:
            vtu_dir.mkdir(exist_ok=True)
            full.save(vtu_dir/f"{run_name(case)}_{tname}.vtu")
        render(full, out/f"3d_{t:g}s.png", t, x0 + v*min(t, t_off), t <= t_off, T_sol, T_liq)
        print(f"{tname}: {full.n_cells} cells")
    print(f"images -> {out.relative_to(ROOT)}" + ("" if args.no_vtu else f", VTK -> {vtu_dir}"))


if __name__ == "__main__":
    main()
