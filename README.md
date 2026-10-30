# Transient Laser Melt-Pool Simulation with Marangoni Flow

**ME323 course project.** This is a 3D, transient thermo-fluid simulation of a
moving Gaussian laser melting the surface of a **Ti-6Al-4V** block. It is built
on the open-source finite-volume solver
[AdditiveFOAM](https://github.com/ORNL/AdditiveFOAM) 2.0.0, running on
OpenFOAM-14.

The model covers the whole thermal cycle of a laser track:

**solid heating → melting → Marangoni-driven melt flow → solidification**

It includes:
- heat conduction with temperature-dependent properties;
- latent heat;
- buoyancy;
- surface-tension (Marangoni) shear;
- convection and radiation to room temperature.

A parametric study varies scan speed, laser power, absorptivity and beam
radius. Paired runs with the Marangoni effect switched off show how much it
matters.

📄 **Full report: [docs/REPORT.md](docs/REPORT.md)**

![3D cut-away of a melt pool](results/R02/3d_0.75s.png)

## Key results

| | With Marangoni flow (12 runs) | Without (3 paired runs) |
|---|---|---|
| Pool depth | 0.37–0.60 mm | 2.3–2.4× deeper |
| Pool width | 2.6–5.1 mm (width/depth 6.6–8.8) | 23–27 % narrower (width/depth ≈ 2.7) |
| Peak temperature (quasi-steady) | 2810–3130 K (below boiling, 3533 K) | 4940–5590 K (unphysical: no evaporation in the model) |
| Peak melt speed | 0.41–0.53 m/s | ≈ 0.02 m/s (buoyancy only) |
| Marangoni / buoyancy, Ma/Gr | 365–1384 | — |
| Péclet number | 58–146 (convection dominates) | 2–5 |
| Cooling rate at solidification | 960–4260 K/s, rising with scan speed | — |

**Marangoni flow is the main mechanism in the pool.** For Ti-6Al-4V, dσ/dT is
negative, so the surface flows outward from under the beam. That flow:
- spreads the heat sideways;
- caps the peak temperature;
- turns a deep hemispherical conduction pool into a wide, shallow one.

![Marangoni on vs off](docs/figures/marangoni_on_off.png)

## Model summary

| Item | Choice |
|---|---|
| Domain | 24 × 20 × 8 mm block. Half model (y ≥ 0) with a symmetry plane on the track centreline |
| Mesh | Fixed 100 µm hexahedral cells in the 12 × 4 × 2 mm fine region, graded to 1 mm outside; 288,750 cells |
| Laser | Gaussian (1/e² radius r), absorbed power ηP, moving along x from 8 to 12 mm, then off. 1.5 s simulated per run |
| Phase change | Enthalpy method. Solid fraction from a cosine-smoothed step between solidus 1878 K and liquidus 1928 K |
| Flow | Incompressible laminar Navier–Stokes, Boussinesq buoyancy, Carman–Kozeny mushy-zone damping (A_mush = 10⁸) |
| Marangoni | Top-surface shear μ ∂u/∂n = f_L (dσ/dT) ∇ₛT, applied only where molten. dσ/dT = −2.6 × 10⁻⁴ N/m·K |
| Heat losses | All surfaces: convection h = 25 W/m²K to 293 K. Top and sides also radiate (ε = 0.54) |
| Material data | Ti-6Al-4V, every value from a cited source: [materials/Ti6Al4V_sources.md](materials/Ti6Al4V_sources.md) |

The equations, boundary conditions, solver changes and verification checks are
in the [report](docs/REPORT.md). How each item maps onto AdditiveFOAM's source
code is in [docs/SIMULATION_PLAN.md](docs/SIMULATION_PLAN.md).

## Run matrix

| Run | Speed (mm/s) | Absorbed power (W) | Absorptivity | Beam radius (mm) |
|---|---|---|---|---|
| R01 / R02 / R03 | 4 | 300 / 500 / 700 | 0.30 / 0.35 / 0.40 | 0.50 / 0.75 / 1.00 |
| R04 / R05 / R06 | 6 | 400 / 600 / 800 | 0.40 / 0.30 / 0.35 | 0.50 / 0.75 / 1.00 |
| R07 / R08 / R09 | 8 | 350 / 550 / 750 | 0.35 / 0.40 / 0.30 | 0.60 / 0.75 / 1.00 |
| R10 / R11 / R12 | 10 | 450 / 650 / 800 | 0.30 / 0.35 / 0.40 | 0.50 / 0.75 / 0.90 |
| R02_noMa, R06_noMa, R11_noMa | as R02, R06, R11 | | | |

The `_noMa` runs use **dσ/dT = 0**, so the Marangoni force is off; buoyancy is
still on. The full table, with laser power and line energy, is in
[config/baseline.json](config/baseline.json) and the report.

## Data

All 15 runs are collected in **`results/melt_pool_dataset.xlsx`**, laid out as
machine-learning tables: every row carries the run name and its inputs.

| Sheet | Rows | Content |
|---|---|---|
| `runs` | 15 | One row per run: inputs, quasi-steady pool size, temperatures, speeds, solidification statistics, Marangoni quantities, Ma / Gr / Pe / Re |
| `timeseries` | 2,265 | Every run every 0.01 s |
| `marangoni` | 90 | Surface Marangoni shear, temperature gradient, surface speed and flow direction, every 0.25 s |
| `solidification` | 69,811 | Every solidification event: position, time, cooling rate, G, R, G/R |
| `columns` | 80 | Description and unit of every column |

Each run also has a folder `results/<run>/` holding:
- `summary.json`;
- a time-history plot;
- 2D temperature and velocity sections every 0.25 s;
- 3D cut-away images;
- `marangoni_snapshots.csv`.

## Repository layout

```
config/baseline.json       all physical and numerical inputs, each tagged CONFIRMED / CHOSEN / SOURCED / DERIVED
materials/                 Ti6Al4V.cfg and its cited sources
templates/case/            static OpenFOAM case files (fields, numerics, resumable Allrun)
setup/                     install script, per-terminal environment, solver patches
external/AdditiveFOAM      solver source (git submodule, v2.0.0)
scripts/
  make_cases.py            builds cases/<run> from config/baseline.json (mesh, smoothed step, laser path)
  run_all.sh               runs, analyses and exports every case, skipping finished ones
  analyze_case.py          pool size, time series, solidification statistics, 2D sections
  export_3d.py             full-width 3D fields (ParaView .vtu), 3D images, surface Marangoni metrics
  export_excel.py          results/melt_pool_dataset.xlsx
  report_figures.py        summary figures for the report (docs/figures/)
  estimate_pool.py         Rosenthal pool-size and time-step estimates
docs/
  REPORT.md                project report
  SIMULATION_PLAN.md       physics-to-solver mapping, design history
  SETUP.md                 installation
papers/                    reference papers (Gao 2021, Farzadi 2008, Pariona 2018, Fuhrich 2001)
results/                   per-run outputs and the dataset workbook
```

## Quick start

On Ubuntu 22.04 or 24.04, after the one-time install in
[docs/SETUP.md](docs/SETUP.md):

```bash
source setup/env.sh                                   # in every new terminal
python scripts/make_cases.py                          # cases/R01 ... from config/baseline.json
nohup bash scripts/run_all.sh > run_all.log 2>&1 &    # run + analyse + export (resumable)
python scripts/report_figures.py                      # report figures
```

On 8 cores a run takes 15–33 min with Marangoni flow and 6–8 min without it.
`run_all.sh` resumes an interrupted run from its last saved time.

## Solver modifications

AdditiveFOAM's tutorials solve heat conduction only. To run the full melt flow,
three changes were made:
- the flow solve is switched on (`nOuterCorrectors 1`);
- two small patches in [setup/patches/](setup/patches/), applied automatically
  by the install script:
  - **`marangoni-assignable`:** stops the pressure step from pushing mass
    through the closed top surface;
  - **`marangoni-liquid-fraction`:** scales the Marangoni shear by the liquid
    fraction, so it acts only on molten surface.

## Limitations

- The top surface is flat and fixed: there is no evaporation, recoil pressure
  or keyhole. This is fine below the boiling point, as in all Marangoni runs.
- The grid is fixed at 100 µm, with no mesh-independence study. Pools are 4–6
  cells deep, so trends between runs are more reliable than absolute values.
- The track is short (4 mm). Depth and peak temperature reach steady state,
  but width and length still grow 3–4 %.

## References

- S. Gao et al., *Optics & Laser Technology* 142 (2021) 107215.
- A. Farzadi et al., *Int. J. Adv. Manuf. Technol.* 38 (2008) 258–267.
- M. M. Pariona et al., *Int. J. Heat Mass Transfer* 119 (2018) 10–19.
- T. Fuhrich et al., *J. Laser Appl.* 13 (2001) 178–186.

Material data sources are listed in
[materials/Ti6Al4V_sources.md](materials/Ti6Al4V_sources.md).
