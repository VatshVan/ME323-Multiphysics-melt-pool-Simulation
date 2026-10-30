# Transient Laser Melt-Pool Simulation with Marangoni Flow

## Project Overview

This project aims to build a transient numerical model of a laser-heated
workpiece using **AdditiveFOAM/OpenFOAM**, with code development and
debugging assisted by an AI coding agent such as Codex.

The initial goal is to study the thermal evolution and fluid motion of a
melt pool as a moving Gaussian laser heat source travels along the
workpiece. Particular attention will be paid to Marangoni-driven flow
near the melt-pool surface and to how the predicted results change with
mesh resolution.

This README records the **initial project plan** based on the discussion
notes. Details that are not yet confirmed are explicitly marked as
pending.

## Repository Layout and Quick Start

```
config/baseline.json      all physical/numerical parameters (CONFIRMED / CHOSEN / SOURCED)
materials/                Ti6Al4V.cfg (+ cited sources), pure-Al reference file
templates/case/           static OpenFOAM case files (fields, numerics, Allrun)
scripts/make_cases.py     one case per row of the run table in config/baseline.json (cases/R01 ...)
scripts/estimate_pool.py  Rosenthal pool size, Marangoni velocity, time-step estimates
scripts/analyze_case.py   history plots, pool metrics, time series, field sections -> results/<case>/
scripts/export_excel.py   all runs -> results/melt_pool_dataset.xlsx for the ML model
scripts/export_3d.py      full-block (mirrored) 3D snapshots: VTK for ParaView + 3D images
scripts/run_all.sh        run + analyse + export every case, skipping finished ones
setup/                    install script + per-terminal environment
external/AdditiveFOAM     solver source (git submodule, v2.0.0, OpenFOAM-14)
docs/SETUP.md             installation steps
docs/SIMULATION_PLAN.md   how the physics maps onto AdditiveFOAM, run order, open questions
papers/                   reference papers
```

```bash
# from the project root, on Ubuntu 22.04/24.04 (see docs/SETUP.md for the one-time install)
source setup/env.sh
python scripts/make_cases.py                       # one case per row of the run table
nohup bash scripts/run_all.sh > run_all.log 2>&1 &   # run, analyse, export all (resumable)
# results: results/<case>/ (plots, 3D images, summary.json, timeseries.csv)
#          cases/<case>/VTK_full/*.vtu (full-block 3D fields for ParaView)
#          results/melt_pool_dataset.xlsx (runs / timeseries / solidification / columns)
```

## Initial Scope

The first implementation will focus on:

1.  Transient heat transfer in the workpiece.
2.  A Gaussian laser heat source moving in the (x)-direction.
3.  Melting and solidification, including latent heat where supported by
    the selected model.
4.  Fluid flow in the molten region.
5.  Marangoni surface-tension effects.
6.  Thermal boundary conditions, including convection and radiation as
    specified for the case.
7.  A laser-parameter study (scan speed, power, absorptivity, beam radius)
    on a fixed 200 µm grid. (A 200/150/100 µm mesh study was planned first
    and replaced by this.)
8.  Recording time-dependent fields and quantities that describe
    melt-pool formation, flow, cooling, and solidification.

The initial plan is to use a fixed mesh. Moving-mesh/interface
deformation is outside the first implementation scope unless the TA
later specifies otherwise.

## Geometry and Coordinates

-   **Material:** Ti-6Al-4V (properties and references:
    `materials/Ti6Al4V_sources.md`).
-   **Workpiece:** 50 mm long (x, laser travel) × 20 mm wide (y) × 8 mm
    deep (z, top surface at z = 0).
-   **Symmetry:** half model y ≥ 0 (10 mm), symmetry plane y = 0 on the
    track centreline.
-   **Fine-grid region (ROI):** 5 mm × 5 mm corner at the symmetry plane and
    the top surface, along the whole length; graded to 0.6 mm cells outside.
-   **Laser:** Gaussian beam moving along x on the symmetry plane; speed,
    power, absorptivity and radius vary per run (table below). The trial runs
    showed that a ≥ 2.5 mm deep pool needs slow scans (1 mm/s, 2.5 kW
    absorbed, 2.5 mm radius: 3.4 mm deep; `docs/SIMULATION_PLAN.md` §7).
-   **Dataset runs** use a 24 mm long block (as the trial runs) to fit the
    ~30 min per run budget; the 50 mm block is supported by the same scripts.

## Physics and Model Components

### 1. Transient heat transfer

Solve the transient thermal problem in the workpiece, including
conduction and the moving laser heat input. Thermal boundary conditions
are expected to include convection and radiation where prescribed.

The laser source will be represented as a Gaussian distribution moving
along (x). Its implementation requires the laser power or absorbed
power, beam radius/diameter, scan speed, and the chosen Gaussian
convention.

### 2. Melting and solidification

The model should account for the transition between solid and liquid.
The implementation should use the phase-change treatment supported by
the chosen AdditiveFOAM solver, including latent heat and a
liquid-fraction or equivalent formulation as appropriate.

The notes describe an initial heating period before melting starts,
followed by melt-pool formation and subsequent cooling/solidification
after the beam passes. These stages should be captured in transient
outputs.

### 3. Fluid flow in the melt pool

Use the solver's existing fluid-flow formulation where suitable. The
model should suppress unrealistic flow through solid or partially solid
material using the phase-change resistance treatment provided by the
selected implementation, if applicable.

The flow formulation and its assumptions must be checked against the
selected solver and the TA's requirements before changes are made.

### 4. Marangoni surface-tension model

The discussion notes propose a temperature-dependent surface tension
relation of the form

$$
\sigma = \sigma_0 + \frac{d\sigma}{dT}\,(T - T_{\mathrm{ref}})
$$

where the reference temperature and coefficients must be defined
consistently with the chosen model. The notes appear to refer to a
reference/melting temperature, but the exact symbol should be confirmed.

The corresponding tangential surface stress is driven by the surface
gradient of surface tension. The implementation should be checked to
ensure that the temperature dependence and surface-gradient treatment
match the intended model.

The notes also record two constants, read approximately as:

-   (B = 0.0001)
-   A second constant written as "Aroush" or similar, with a value that
    appears to be (10\^8).

**These readings are provisional, not verified parameter values.**
Working interpretation (see `docs/SIMULATION_PLAN.md` §2): B and
A_mush ("Aroush") of the Carman–Kozeny mushy-zone term
`C(1−fL)²/(fL³+B)` in Farzadi et al. (2008), Eq. 2. In AdditiveFOAM this
maps to `DAS = sqrt(180 μ / A_mush) ≈ 79 µm` for Ti-6Al-4V. The Marangoni shear is applied only on molten surface (× liquid fraction, Farzadi Eq. 6), and the solid–liquid transition uses a cosine-smoothed step (Gao 2021 Eq. 8 form); see `docs/SIMULATION_PLAN.md` §2.
Confirm the exact names, units, meanings, and values with the TA before
using them in a simulation. They may relate to the
mushy-zone/phase-change formulation rather than directly to the
Marangoni coefficient.

## Laser-Parameter Study (dataset)

All runs use the same fixed grid (200 µm in the fine region) and model; only
the laser settings change. Template: 24 × 10 (half) × 8 mm block, laser from
x = 4 mm towards x = 20 mm, 5 s of simulated time per run (~25 min on 8
cores). At 5 mm/s the laser reaches x = 20 mm at 3.2 s and is then off, so
those runs also record cooling and solidification.

| Run | Speed (mm/s) | Laser power (W) | Absorptivity | Absorbed (kW) | Beam radius (mm) |
|---|---|---|---|---|---|
| R01 | 5 | 3333 | 0.30 | 1.0 | 1.5 |
| R02 | 5 | 3750 | 0.40 | 1.5 | 2.0 |
| R03 | 5 | 5714 | 0.35 | 2.0 | 2.0 |
| R04 | 5 | 8571 | 0.35 | 3.0 | 3.0 |
| R05 | 3 | 5000 | 0.30 | 1.5 | 2.0 |
| R06 | 3 | 6250 | 0.40 | 2.5 | 2.5 |
| R07 | 3 | 7500 | 0.40 | 3.0 | 3.0 |
| R08 | 2 | 5714 | 0.35 | 2.0 | 2.5 |
| R09 | 2 | 8333 | 0.30 | 2.5 | 2.5 |
| R10 | 1 | 5000 | 0.30 | 1.5 | 2.0 |
| R11 | 1 | 5000 | 0.40 | 2.0 | 2.0 |
| R12 | 1.5 | 8571 | 0.35 | 3.0 | 3.0 |

In this model only laser power × absorptivity enters, so absorptivity is a
dataset column but not an independent physical input. The seven trial runs
A–G (`docs/SIMULATION_PLAN.md` §7) are extra rows of the same dataset.

## Quantities to Record

The initial plan is to save time-dependent results and compare the
following:

-   Temperature field and maximum temperature.
-   Time at which melting first occurs.
-   Melt-pool dimensions and liquid-fraction distribution.
-   Velocity field, peak velocity, and flow/circulation patterns in the
    molten region.
-   Evolution of the melt pool while the laser is present.
-   Cooling behind the moving laser source.
-   Cooling rate and solidification behaviour.
-   Differences in these quantities across the laser settings.

The primary emphasis is on physical behaviour and its sensitivity to the
laser settings. The recorded data are also exported as an Excel workbook for a
machine-learning model (`scripts/export_excel.py`). Energy-balance reporting and computational-cost
benchmarking are not primary deliverables in the current scope.

## Implementation Plan

### Phase 1 --- Inspect and establish a baseline

1.  Check the AdditiveFOAM version, OpenFOAM compatibility, build
    instructions, and available example cases.
2.  Identify the existing implementations of heat transfer, laser input,
    phase change, fluid flow, thermal boundary conditions, and Marangoni
    stress.
3.  Build and run an unmodified example before changing the code.
4.  Document which required physics are already implemented and which
    require configuration or code changes.

### Phase 2 --- Define the case

1.  Finalize the half-workpiece geometry, symmetry plane, (x)-extent,
    and ROI placement.
2.  Confirm material properties and initial/boundary temperatures.
3.  Obtain the laser power, beam size, scan speed, and source
    convention.
4.  Confirm the two constants and the exact Marangoni relation with the
    TA.
5.  Select the appropriate fixed-mesh phase-change and fluid-flow
    formulation.

### Phase 3 --- Implement and test incrementally

1.  Configure the geometry, mesh, and boundary conditions.
2.  Add and verify the moving Gaussian heat source.
3.  Verify the thermal response before introducing fluid flow.
4.  Enable and test melting/solidification.
5.  Enable or adapt the Marangoni model after confirming its equation
    and parameters.
6.  Check solver convergence, field behaviour, and conservation
    properties sufficiently to detect implementation errors.

### Phase 4 --- Run mesh-refinement cases

1.  Create the 200 µm, 150 µm, and 100 µm cases.
2.  Keep all physical inputs consistent.
3.  Run the transient simulations and save comparable time snapshots.
4.  Extract the quantities listed in the measurement section.
5.  Compare the results and document mesh sensitivity and any numerical
    limitations.

## Pending Inputs and Decisions

Given by the user: material, block size, symmetry, ROI, beam diameter, scan
speed, mesh sizes, A_mush and B. Chosen by us and to be confirmed with the
TA (reasoning in `config/baseline.json` and `docs/SIMULATION_PLAN.md` §8):

-   The 12-run table above (ranges: 1–5 mm/s, 1–3 kW absorbed, 0.30–0.40
    absorptivity, 1.5–3 mm beam radius).
-   Fixed grid size of 200 µm and the 24 mm block with 5 s per run.
-   Bottom-surface heat transfer (h = 25 W/m²K, no radiation).
-   Which outputs and comparison times the TA expects.

## Tooling and Reproducibility

-   **Solver framework:** AdditiveFOAM 2.0.0 (commit `8314d3c`) on
    OpenFOAM-14 (OpenFOAM Foundation), run natively on Ubuntu 22.04.
-   **Coding assistance:** Codex or another repository-aware AI coding
    agent.
-   **Case management:** keep the three mesh cases and their
    dictionaries/configuration files version-controlled.
-   **Results:** save solver logs, configuration files, mesh
    information, and post-processing scripts alongside results.
-   **Validation:** compare implementation details with the selected
    solver documentation and the equations/assumptions in the research
    papers. A successful compilation alone does not validate the
    physics.

## Status

**Status: initial specification; not yet a validated simulation.**

The geometry interpretation, constants, and laser parameters still
require confirmation. No claim is made here that the model has been
implemented, validated, or reproduced from the papers.
