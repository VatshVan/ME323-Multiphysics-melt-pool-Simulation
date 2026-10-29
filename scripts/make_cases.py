#!/usr/bin/env python3
"""Generate the AdditiveFOAM mesh-refinement cases from config/baseline.json.

For every cell size in mesh_study.cell_sizes this writes cases/mesh_<N>um/,
a complete OpenFOAM case: static files are copied from templates/case/ and
the parameter-dependent dictionaries are generated here.

Domain (half workpiece, symmetry plane y = 0 on the track centreline):

    x: 0 .. length_x          laser travels in +x along y = 0, z = 0
    y: 0 .. half_width_y      uniform cells for y < roi_y, graded beyond
    z: -depth_z .. 0          uniform cells for z > -roi_z, graded below

Usage:
    python scripts/make_cases.py            # all cell sizes
    python scripts/make_cases.py --only 200e-6
"""

import argparse
import json
import math
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HEADER = """\
/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  14
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       {cls};
    location    "{loc}";
    object      {obj};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

"""
FOOTER = "\n// ************************************************************************* //\n"


def foam_file(cls, loc, obj, body):
    return HEADER.format(cls=cls, loc=loc, obj=obj) + body.strip("\n") + "\n" + FOOTER


def val(section, key):
    return section[key]["value"]


def check_multiple(length, dx, name):
    """Nearest whole number of cells; the actual cell size may differ from dx
    by a few percent (e.g. 5 mm / 150 um = 33.3 -> 33 cells of 151.5 um)."""
    n = max(1, int(round(length/dx)))
    if abs(length/n - dx)/dx > 0.05:
        raise SystemExit(
            f"{name} = {length*1e3:g} mm gives cells of {length/n*1e6:.1f} um, "
            f"more than 5% off the target {dx*1e6:g} um."
        )
    return n


def smooth_step(x):
    """C1-continuous step: 0 for x < -1/2, 1 for x > 1/2, (1 + sin(pi x))/2
    in between. Same support as Gao et al. (2021) Eq. 8."""
    return 0.5*(1.0 + math.sin(math.pi*min(max(x, -0.5), 0.5)))


def smooth_thermo_path(T_sol, T_liq, n=21):
    """Solid fraction alpha.solid(T) = 1 - H((T - T_m)/(T_liq - T_sol)),
    T_m = (T_sol + T_liq)/2, tabulated for AdditiveFOAM's thermoPath."""
    T_m, dT = 0.5*(T_sol + T_liq), T_liq - T_sol
    rows = []
    for i in range(n):
        T = T_sol + dT*i/(n - 1)
        rows.append(f"    ({T:.6g} {1.0 - smooth_step((T - T_m)/dT):.6f})")
    return "thermoPath\n(\n" + "\n".join(rows) + "\n);"


def graded_segment(length, d_fine, d_coarse):
    """Cell count and blockMesh expansion ratio (last/first cell) for a segment
    that starts at d_fine and grows geometrically towards d_coarse."""
    if length <= 0:
        raise SystemExit("ROI must be smaller than the domain")
    if d_coarse <= d_fine:
        return max(1, round(length/d_fine)), 1.0
    best = None
    for n in range(2, 1000):
        q = (d_coarse/d_fine)**(1.0/(n - 1))
        total = d_fine*(q**n - 1.0)/(q - 1.0)
        err = abs(total - length)
        if best is None or err < best[1]:
            best = (n, err)
        if total > length:
            break
    n = best[0]
    return n, d_coarse/d_fine


def block_mesh_dict(cfg, dx):
    g = cfg["geometry"]
    L, W, D = val(g, "length_x"), val(g, "half_width_y"), val(g, "depth_z")
    ry, rz, dout = val(g, "roi_y"), val(g, "roi_z"), val(g, "outer_cell")

    nx = check_multiple(L, dx, "length_x")
    ny_roi = check_multiple(ry, dx, "roi_y")
    nz_roi = check_multiple(rz, dx, "roi_z")
    ny_out, gy_out = graded_segment(W - ry, dx, dout)
    nz_out, gz_out = graded_segment(D - rz, dx, dout)

    xs, ys, zs = [0.0, L], [0.0, ry, W], [-D, -rz, 0.0]

    def vid(i, j, k):
        return i + 2*(j + 3*k)

    vertices = [
        f"    ({xs[i]:.6g} {ys[j]:.6g} {zs[k]:.6g})    // {vid(i, j, k)}"
        for k in range(3) for j in range(3) for i in range(2)
    ]

    # y segment 0 = ROI, 1 = outer; z segment 0 = outer (bottom), 1 = ROI (top)
    ny = [ny_roi, ny_out]
    gy = [1.0, gy_out]
    nz = [nz_out, nz_roi]
    gz = [1.0/gz_out, 1.0]   # coarse at the bottom, fine towards z = -roi_z

    blocks, hexes = [], {}
    for k in range(2):
        for j in range(2):
            v = [vid(0, j, k), vid(1, j, k), vid(1, j+1, k), vid(0, j+1, k),
                 vid(0, j, k+1), vid(1, j, k+1), vid(1, j+1, k+1), vid(0, j+1, k+1)]
            hexes[(j, k)] = v
            blocks.append(
                f"    hex ({' '.join(map(str, v))}) ({nx} {ny[j]} {nz[k]}) "
                f"simpleGrading (1 {gy[j]:.6g} {gz[k]:.6g})"
            )

    # Outward-pointing faces of OpenFOAM's hex cell model
    face = {
        "xmin": (0, 4, 7, 3), "xmax": (1, 2, 6, 5),
        "ymin": (0, 1, 5, 4), "ymax": (3, 7, 6, 2),
        "zmin": (0, 3, 2, 1), "zmax": (4, 5, 6, 7),
    }

    def faces(selection):
        out = []
        for (j, k), side in selection:
            v = hexes[(j, k)]
            out.append("            (" + " ".join(str(v[i]) for i in face[side]) + ")")
        return "\n".join(out)

    allBlocks = [(j, k) for k in range(2) for j in range(2)]
    patches = {
        "top": ("wall", [((j, 1), "zmax") for j in range(2)]),
        "bottom": ("wall", [((j, 0), "zmin") for j in range(2)]),
        "symmetry": ("symmetryPlane", [((0, k), "ymin") for k in range(2)]),
        "sides": ("wall",
                  [(b, "xmin") for b in allBlocks]
                + [(b, "xmax") for b in allBlocks]
                + [((1, k), "ymax") for k in range(2)]),
    }
    boundary = "\n".join(
        f"    {name}\n    {{\n        type {ptype};\n        faces\n        (\n"
        f"{faces(sel)}\n        );\n    }}"
        for name, (ptype, sel) in patches.items()
    )

    nCells = nx*(ny_roi + ny_out)*(nz_roi + nz_out)
    body = (
        f"// Generated by scripts/make_cases.py: ROI cell {dx*1e6:g} um, "
        f"~{nCells} cells\n\nconvertToMeters 1;\n\n"
        "vertices\n(\n" + "\n".join(vertices) + "\n);\n\n"
        "blocks\n(\n" + "\n".join(blocks) + "\n);\n\n"
        "edges\n(\n);\n\n"
        "boundary\n(\n" + boundary + "\n);\n\n"
        "mergePatchPairs\n(\n);"
    )
    info = {"nx": nx, "ny": [ny_roi, ny_out], "nz": [nz_roi, nz_out],
            "grading_y_outer": gy_out, "grading_z_outer": gz_out, "n_cells": nCells}
    return foam_file("dictionary", "system", "blockMeshDict", body), info


def scan_path(cfg):
    las = cfg["laser"]
    x0, x1 = val(las, "x_start"), val(las, "x_end")
    # Mode 1 = spot/dwell (Param = time [s]); Mode 0 = line (Param = speed [m/s])
    return (
        "Mode    X           Y       Z       Power       Param\n"
        f"1       {x0:.6g}     0.0     0.0     0.0         0.0\n"
        f"0       {x1:.6g}     0.0     0.0     {val(las, 'power'):.6g}      {val(las, 'speed'):.6g}\n"
        f"1       {x1:.6g}     0.0     0.0     0.0         {val(las, 'cooling_time'):.6g}\n"
    )


def heat_source_dict(cfg):
    las = cfg["laser"]
    r = val(las, "radius")
    body = f"""
sources
{{
    beam
    {{
        path            scanPath;
        widthReference  D4Sigma;

        absorption
        {{
            model       constant;
            eta         {val(las, 'absorptivity'):.6g};
        }}

        heatSource
        {{
            model       superGaussian;
            radius      ({r:.6g} {r:.6g});
            definition  secondMoment;
            depth       {val(las, 'depth'):.6g};
            k           {val(las, 'k'):.6g};
            nPoints     (10 10 10);
        }}
    }}
}}
"""
    return foam_file("dictionary", "constant", "heatSourceDict", body)


def transport_properties(cfg):
    text = (ROOT/cfg["material"]["file"]).read_text()
    mu = float(re.search(r"^mu\s+\[[^\]]*\]\s+([0-9.eE+-]+);", text, re.M).group(1))
    A_mush = val(cfg["mushy_zone"], "A_mush")
    DAS = math.sqrt(180.0*mu/A_mush)
    text, n = re.subn(
        r"^DAS(\s+\[[^\]]*\]\s+)[0-9.eE+-]+;",
        rf"DAS\g<1>{DAS:.6g};    // = sqrt(180*mu/A_mush), A_mush = {A_mush:g}",
        text, flags=re.M,
    )
    if n != 1:
        raise SystemExit("could not find DAS entry in material file")

    # Replace the (T_sol 1) (T_liq 0) endpoints with the smoothed solid fraction
    path = re.search(r"^thermoPath(?:\s*//[^\n]*)?\s*\(\s*\(\s*([0-9.eE+-]+)\s+1\s*\)\s*"
                     r"\(\s*([0-9.eE+-]+)\s+0\s*\)\s*\);", text, re.M)
    if path is None:
        raise SystemExit("thermoPath must list exactly (T_sol 1) (T_liq 0)")
    T_sol, T_liq = float(path.group(1)), float(path.group(2))
    text = (text[:path.start()]
            + "// cosine-smoothed solid fraction, scripts/make_cases.py\n"
            + smooth_thermo_path(T_sol, T_liq) + text[path.end():])
    body = f"// Material: {cfg['material']['file']}\n\n" + text
    return foam_file("dictionary", "constant", "transportProperties", body), DAS


def temperature_field(cfg):
    bc = cfg["thermal_bc"]
    Tinf = val(bc, "T_ambient")

    def mixed(h, eps):
        return (f"        type            mixedTemperature;\n"
                f"        h               {h:.6g};\n"
                f"        emissivity      {eps:.6g};\n"
                f"        Tinf            uniform {Tinf:.6g};\n"
                f"        value           uniform {Tinf:.6g};")

    body = f"""
dimensions      [0 0 0 1 0 0 0];

internalField   uniform {val(bc, 'T_initial'):.6g};

// mixedTemperature: -k dT/dn = h (T - Tinf) + emissivity*sigma*(T^4 - Tinf^4)
// (laser power enters as a volumetric source, see constant/heatSourceDict)
boundaryField
{{
    top
    {{
{mixed(val(bc, 'h_top'), val(bc, 'emissivity_top'))}
    }}

    sides
    {{
{mixed(val(bc, 'h_sides'), val(bc, 'emissivity_sides'))}
    }}

    bottom
    {{
{mixed(val(bc, 'h_bottom'), 0.0)}
    }}

    symmetry
    {{
        type            symmetryPlane;
    }}
}}
"""
    return foam_file("volScalarField", "0", "T", body)


def control_dict(cfg, end_time):
    num, g = cfg["numerics"], cfg["geometry"]
    ry, rz, L = val(g, "roi_y"), val(g, "roi_z"), val(g, "length_x")
    body = f"""
application     additiveFoam;

startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {end_time:.6g};
deltaT          1e-07;

writeControl    adjustableRunTime;
writeInterval   {val(num, 'write_interval'):.6g};
purgeWrite      0;
writeFormat     binary;
writePrecision  8;
writeCompression off;
timeFormat      general;
timePrecision   8;
runTimeModifiable yes;

adjustTimeStep  yes;
maxCo           {val(num, 'maxCo'):.6g};
maxDi           {val(num, 'maxDi'):.6g};
maxAlphaCo      {val(num, 'maxAlphaCo'):.6g};

functions
{{
    // Melt-pool length/width/depth vs time at liquidus and solidus isotherms.
    // Width is measured on the half domain: full width = 2 x reported width.
    meltPoolDimensions
    {{
        libs            ("libadditiveFoamFunctionObjects.so");
        type            meltPoolDimensions;
        scanPathAngle   0.0;
    }}

    // Every solidification event in the ROI: x,y,z,ts,cooling rate,G,R
    solidificationData
    {{
        libs            ("libadditiveFoamFunctionObjects.so");
        type            solidificationData;
        box             (0 0 {-rz:.6g}) ({L:.6g} {ry:.6g} 0);
    }}

    // Solid fraction is not written by the solver itself; liquid = 1 - alpha.solid
    writeAlphaSolid
    {{
        libs            ("libutilityFunctionObjects.so");
        type            writeObjects;
        objects         (alpha.solid);
        writeControl    writeTime;
    }}

    // Peak temperature and velocity magnitude vs time (OpenFOAM-14 has no
    // fieldMinMax; volFieldValue replaces it)
    Tmax
    {{
        libs            ("libfieldFunctionObjects.so");
        type            volFieldValue;
        cellZone        all;
        operation       max;
        fields          (T);
        writeFields     false;
        writeControl    timeStep;
        writeInterval   1;
    }}

    Umax
    {{
        libs            ("libfieldFunctionObjects.so");
        type            volFieldValue;
        cellZone        all;
        operation       maxMag;
        fields          (U);
        writeFields     false;
        writeControl    timeStep;
        writeInterval   1;
    }}
}}
"""
    return foam_file("dictionary", "system", "controlDict", body)


def decompose_par_dict(cfg):
    body = f"""
numberOfSubdomains  {val(cfg['numerics'], 'n_procs')};

decomposer          scotch;
"""
    return foam_file("dictionary", "system", "decomposeParDict", body)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="\n") as f:
        f.write(text)


def make_case(cfg, dx, cases_dir=ROOT/"cases"):
    case = cases_dir/f"mesh_{round(dx*1e6)}um"
    if case.exists():
        shutil.rmtree(case)
    shutil.copytree(ROOT/"templates"/"case", case)

    las = cfg["laser"]
    end_time = (val(las, "x_end") - val(las, "x_start"))/val(las, "speed") \
        + val(las, "cooling_time")

    mesh_text, mesh_info = block_mesh_dict(cfg, dx)
    tp_text, DAS = transport_properties(cfg)

    write(case/"system"/"blockMeshDict", mesh_text)
    write(case/"system"/"controlDict", control_dict(cfg, end_time))
    write(case/"system"/"decomposeParDict", decompose_par_dict(cfg))
    write(case/"constant"/"scanPath", scan_path(cfg))
    write(case/"constant"/"heatSourceDict", heat_source_dict(cfg))
    write(case/"constant"/"transportProperties", tp_text)
    write(case/"0"/"T", temperature_field(cfg))

    pending = sorted(
        f"{sec}.{key}" for sec, entries in cfg.items() if isinstance(entries, dict)
        for key, e in entries.items()
        if isinstance(e, dict) and e.get("status") == "PENDING"
    )
    info = {"cell_size": dx, "end_time": end_time, "DAS": DAS,
            "mesh": mesh_info, "pending_parameters": pending}
    write(case/"case_info.json", json.dumps(info, indent=2) + "\n")
    return case, info


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=ROOT/"config"/"baseline.json", type=Path)
    parser.add_argument("--only", type=float, help="generate a single cell size [m]")
    parser.add_argument("--cases-dir", type=Path, default=ROOT/"cases",
                        help="where to write the cases (default: cases/)")
    args = parser.parse_args()

    cfg = json.loads(Path(args.config).read_text())
    sizes = [args.only] if args.only else val(cfg["mesh_study"], "cell_sizes")

    for dx in sizes:
        case, info = make_case(cfg, dx, args.cases_dir.resolve())
        m = info["mesh"]
        print(f"{case}: {m['n_cells']} cells "
              f"(nx={m['nx']}, ny={m['ny']}, nz={m['nz']}), "
              f"endTime={info['end_time']:g} s, DAS={info['DAS']*1e6:.1f} um")
    print(f"PENDING parameters ({len(info['pending_parameters'])}): see config/baseline.json")


if __name__ == "__main__":
    main()
