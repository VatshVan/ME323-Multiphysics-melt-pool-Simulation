# How the simulation is set up in AdditiveFOAM

This document links the project README, the four reference papers, and the
AdditiveFOAM source (`external/AdditiveFOAM`, v2.0.0). Every statement about
the solver was checked against its source code; the file is given in
brackets. Material data and their references are in
`materials/Ti6Al4V_sources.md`.

## 1. What each paper contributes

| Paper | Process / tool | What we take from it |
|---|---|---|
| Gao et al. 2021, OLT 142 (NiTi DED on a **pure-Ti** substrate) | DED, COMSOL + ALE | **Main formulation:** transient 3-D energy/momentum/mass (Eqs. 1–3), properties switched between solid and liquid with a **smoothed step** `step((T−Tm)/(Tl−Ts))` on [−½, ½] (Eqs. 4–8), Boussinesq buoyancy (Eq. 9), top-surface laser + convection + radiation (Eq. 10), h = 25 W/m²K, side walls convection + radiation (Eq. 16), Marangoni force balance (Eq. 17), symmetry half-domain (Eqs. 19–21). ALE free surface and powder addition are **out of scope**. |
| Farzadi et al. 2008, IJAMT 38 (pure Al) | GTA welding, FLUENT, half-domain | Carman–Kozeny damping `C(1−fL)²/(fL³+B)` (Eq. 2): the TF's **B = 1e-4** and **"Aroush" = A_mush ≈ 1e8**. **Marangoni BC scaled by liquid fraction**, `μ ∂u/∂z = fL dγ/dT ∂T/∂x` (Eq. 6). Symmetry BCs (Eq. 8), velocity scale (Eq. 20), G, R, G/R. |
| Pariona et al. 2018, IJHMT 119 (Al-1.5Fe) | Laser surface remelting, COMSOL | Gaussian surface flux, Marangoni stress BC (Eq. 5), workbench and convection/radiation BCs (Eqs. 7–9), 2 kW Yb-fibre laser at 1070 nm. |
| Fuhrich et al. 2001, JLA 13 (steel keyhole) | Keyhole welding, FIDAP | The **sign** of dσ/dT sets the flow direction (negative → outward → wide, shallow pool). With a fixed flat surface only dσ/dT matters, not σ₀. Steep gradients behind the source keep sharpening under refinement. |

The README's surface-tension relation `σ = σ0 + dσ/dT (T − Tref)` therefore
enters our model only through `dSigmadT`. Because the surface is flat and
fixed, σ0 and Tref drop out.

## 2. Governing equations, as AdditiveFOAM implements them

| Physics | AdditiveFOAM implementation | Where |
|---|---|---|
| Energy + latent heat | Enthalpy formulation; solid fraction `alpha.solid` from the `thermoPath` table (T → fs), latent heat released as `ρ L ∂fs/∂t`, iterated `nThermoCorrectors` times per step | `thermo/TEqn.H`, `utilities/thermoPath` |
| Properties | `kappa`, `Cp` = polynomials in T for the solid and the liquid, **mixed by `alpha.solid`**; constant `rho` | `updateProperties.H` |
| Momentum | Incompressible, laminar, Boussinesq buoyancy (`beta`, `rhok`) | `pU/UEqn.H`, `pU/pEqn.H` |
| Mushy-zone damping | `D = ν·180/DAS² · fs²/(1−fs)³`, with fs capped at 0.95 | `pU/UEqn.H` |
| Marangoni | `marangoni` U BC: zero normal velocity, tangential gradient `dU/dn = fL (dσ/dT/μ)·∇ₛT` (fL factor is our patch) | `derivedFvPatchFields/marangoni` |
| Convection + radiation | `mixedTemperature` T BC: `−k∂T/∂n = h(T−T∞) + εσ_SB(T⁴−T∞⁴)` | `derivedFvPatchFields/mixedTemperature` |
| Laser | Volumetric `superGaussian` (k = 2 is a Gaussian) moving along `scanPath`; absorbed power ηP | `movingHeatSource/` |

### Smoothed solid–liquid transition

Gao Eq. 8 asks for a smooth step on [−½, ½]. We use

    H(x) = ½ (1 + sin πx)  for |x| ≤ ½,   0 below,   1 above,
    x = (T − Tm)/(Tl − Ts),  Tm = (Ts + Tl)/2

which has a continuous slope at both ends. `scripts/make_cases.py` tabulates
`alpha.solid = 1 − H(x)` at 21 points between Ts = 1878 K and Tl = 1928 K as
the `thermoPath`. One function then drives everything that changes at
melting:

- **latent heat** (released as `alpha.solid` changes),
- **properties** (`kappa`, `Cp` mixed by `alpha.solid`, Gao Eqs. 5–6),
- **flow damping** in the mushy zone (Darcy term in fs),
- **Marangoni shear**, scaled by `fL = 1 − alpha.solid` (Farzadi Eq. 6).

So a solid region sees only conduction, convection and radiation; flow and
Marangoni stress switch on smoothly as it melts and off as it solidifies.

### Mapping the TF's constants onto AdditiveFOAM

AdditiveFOAM uses DAS (a length) where Farzadi/FLUENT use A_mush. Matching
the Darcy coefficients (`C = 180 μ/DAS²` per unit volume) gives

    DAS = sqrt(180 μ / A_mush) = sqrt(180 · 3.5e-3 / 1e8) ≈ 79 µm

`scripts/make_cases.py` computes this from `config/baseline.json`.
AdditiveFOAM has no B: it caps the solid fraction at 0.95 instead. That gives
a maximum damping of about 7e3·A_mush, compared with A_mush/B = 1e4·A_mush in
Farzadi's form, so the two are equivalent in practice. If the TF wants
Farzadi's exact form, it is a three-line edit of `pU/UEqn.H`, kept as a
patch in `setup/patches/` like the Marangoni fixes below.

### Flow solve and solver patches

All AdditiveFOAM tutorials run conduction-only (`nOuterCorrectors 0` in
`fvSolution`), which skips the momentum and pressure equations entirely. Our
template uses `nOuterCorrectors 1`. Two patches in `setup/patches/` (applied
by the install script; details in `setup/patches/README.md`):

1. `marangoni-assignable.patch`: without it the pressure step puts flux
   through the top of our closed domain and the run aborts.
2. `marangoni-liquid-fraction.patch`: Marangoni shear × liquid fraction.

### Symmetry plane and laser power

The heat source divides ηP by the analytic beam volume `V0`, and only
re-normalises to the mesh integral when that is within 5% of V0
(`movingHeatSource.C`). With the beam centred on the `y = 0` symmetry plane,
the half-domain integral is about V0/2, so the half-model automatically
receives exactly half the power (checked: 262.5 W of 1500 × 0.35 = 525 W).
**Do not halve the power by hand.**

## 3. Case layout (generated by `scripts/make_cases.py`)

```
z = 0      top: marangoni (U), mixedTemperature h_top + ε (T)
y = 0      symmetry: symmetryPlane (track centreline)
y = 10 mm, x = 0, x = 50 mm: sides: noSlip, mixedTemperature h_sides + ε
z = −8 mm  bottom: noSlip, mixedTemperature h_bottom (no radiation)

x: 0 → 14 mm graded 0.6 mm → Δ;  14 → 36 mm uniform Δ;  36 → 50 mm graded Δ → 0.6 mm
y: 0 → 8 mm uniform Δ, then graded to 0.6 mm at y = 10 mm
z: 0 → −5 mm uniform Δ, then graded to 0.6 mm at z = −8 mm
laser: x = 23 → 27 mm along y = 0 at speed v, then 3 s off
```

The real block is 50 × 20 × 8 mm; we model the half y ≥ 0. Δ = 150 µm
(fixed); 577 k cells. One case per scan speed: `cases/v1mmps`,
`cases/v1.5mmps`, `cases/v2mmps` (7, 5.7 and 5 s of simulated time).

The fine region is wider than the 5 × 5 mm first specified: at 1 mm/s and
2.5 kW the pool reaches ~17 mm full width (8.5 mm half width) and ~3.4 mm
depth (test G, §7).

## 4. Outputs, and how they map to the README's list

| README quantity | Source |
|---|---|
| Temperature field, max T; velocity field, max \|U\| | Time directories (`writeInterval`); `postProcessing/Tmax`, `postProcessing/Umax` (volFieldValue) every step |
| Time of first melting | First time `max(T) ≥ T_liq` in `postProcessing/Tmax` |
| Pool length / width / depth vs time | `postProcessing/meltPoolDimensions/<iso>.csv` at liquidus and solidus. **Width is the half-width on our half domain: multiply by 2.** |
| Liquid-fraction distribution | `alpha.solid` field, written each write time (liquid = 1 − alpha.solid) |
| Cooling rate, G, R, G/R, G·R | `solidificationData` (x, y, z, t_s, cooling rate, G vector, v) within the ROI box |
| Flow pattern / vortices | ParaView: U glyphs on cross-sections x = const |

## 5. Run order

1. **Smoke test:** the unmodified `AMB2018-02-B` tutorial (docs/SETUP.md).
2. **Mesh check:** `blockMesh && checkMesh` on each case.
3. **Short smoke run (0.2 s) of each case:** absorbed power = ηP/2, melting
   starts, flow switches on, no errors.
4. **Full runs:** `./Allrun` in each `cases/v*mmps` (resumable: re-run
   `./Allrun` after an interruption; the solidification events of the
   segment before the restart are lost, because AdditiveFOAM writes them
   only at the end of a run).
5. **Analysis:** `scripts/analyze_case.py` per case, then
   `scripts/export_excel.py` for the ML workbook.

## 6. Scan-speed analysis

- **Compare across speeds:** quasi-steady pool depth, width, length;
  T_max; |U|_max; cooling rate, G, R, G/R at the pool bottom; time to full
  solidification after the laser stops.
- **Expected trends:** slower scan → more energy per mm (line energy
  P_abs/v) → deeper, wider pool, lower cooling rate and G·R, larger G/R.
- **ML workbook** (`results/melt_pool_dataset.xlsx`): `runs` (one row per
  speed), `timeseries` (every run every 0.01 s), `solidification` (every
  solidification event in the fine region), `columns` (units).

## 7. Laser settings and how they were chosen

Target: melt pool at least 2.5 mm deep, peak temperature below T_boil =
3533 K (no evaporation in the model), pool inside the 20 mm block. Trial
runs at 200 µm on a 24 mm block (`~/run/screen*`, not version-controlled):

| Test | Speed | P_abs | Beam r | Depth | Full width | Peak T |
|---|---|---|---|---|---|---|
| — | 5 mm/s | 525 W | 1.5 mm | 0.55 mm (steady) | 3.7 mm | 2410 K |
| A | 5 mm/s | 2.5 kW | 2.5 mm | 1.02 mm | 11.6 mm | 3057 K |
| B | 5 mm/s | 3.5 kW | 2.5 mm | 1.15 mm (max 1.45) | 13.2 mm | 3391 K |
| C | 5 mm/s | 3.5 kW | 3.0 mm | 1.16 mm (max 1.45) | 13.7 mm | 3161 K |
| D | 2 mm/s | 1.5 kW | 2.0 mm | 1.04 mm | 10.4 mm | 2914 K |
| E | 1 mm/s | 1.0 kW | 2.0 mm | 1.00 mm | 8.4 mm | 2640 K |
| F | 1 mm/s | 2.0 kW | 2.5 mm | 2.40 mm (rising) | 13.0 mm | 2888 K |
| **G** | **1 mm/s** | **2.5 kW** | **2.5 mm** | **3.35–3.4 mm (steady after ~3 s)** | 15 mm at 3 s, 20 mm at 5 s | 3068 K |

With dσ/dT < 0 the surface flow drives heat outward, so extra power
mostly widens the pool (Fuhrich). Only slow scanning reached the target.
At 1 mm/s the pool keeps widening, reaching the block's side wall after
~5 s, so the track is limited to 4 mm. Test G also confirmed `maxCo` 0.9
is stable (max Courant 0.90).

## 8. Remaining choices to confirm with the TA

1. Laser power, absorptivity and beam radius (chosen: 7.14 kW, η = 0.35,
   r = 2.5 mm, from test G).
2. Track x = 23 → 27 mm and 3 s of cooling (chosen).
3. Bottom boundary: h = 25 W/m²K without radiation (Pariona's workbench
   h_d has no value); Gao instead keeps the bottom at room temperature.
4. Whether AdditiveFOAM's built-in mushy-zone damping is acceptable, or the
   exact Farzadi form with B should be coded.
