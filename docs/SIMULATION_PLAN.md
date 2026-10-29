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

x: 0 → 50 mm, uniform Δ          laser: x = 5 → 45 mm along y = 0, then 1 s off
y: 0 → 5 mm uniform Δ, then graded to 0.6 mm at y = 10 mm
z: 0 → −5 mm uniform Δ, then graded to 0.6 mm at z = −8 mm
```

The real block is 50 × 20 × 8 mm; we model the half y ≥ 0. The 5 × 5 mm
fine-grid corner sits at the symmetry plane and the top surface.

| Case | Δ in ROI (actual) | Cells |
|---|---|---|
| `cases/mesh_200um` | 200 µm | 322 k |
| `cases/mesh_150um` | 151.5 µm (y, z), 150.2 µm (x) | 671 k |
| `cases/mesh_100um` | 100 µm | 2.04 M |

Cell counts are rounded to whole numbers, so the 150 µm case is 1% off
target in the 5 mm ROI (33 cells).

## 4. Outputs, and how they map to the README's list

| README quantity | Source |
|---|---|
| Temperature field, max T; velocity field, max \|U\| | Time directories (`writeInterval`); `postProcessing/Tmax`, `postProcessing/Umax` (volFieldValue) every step |
| Time of first melting | First time `max(T) ≥ T_liq` in `postProcessing/Tmax` |
| Pool length / width / depth vs time | `postProcessing/meltPoolDimensions/<iso>.csv` at liquidus and solidus. **Width is the half-width on our half domain: multiply by 2.** |
| Liquid-fraction distribution | `alpha.solid` field, written each write time (liquid = 1 − alpha.solid) |
| Cooling rate, G, R, G/R, G·R | `solidificationData` (x, y, z, t_s, cooling rate, G vector, v) within the ROI box |
| Flow pattern / vortices | ParaView: U glyphs on cross-sections x = const |

## 5. Run order (validate step by step)

1. **Smoke test:** the unmodified `AMB2018-02-B` tutorial (docs/SETUP.md).
2. **Mesh check:** `blockMesh && checkMesh` on all three cases.
3. **Short trial (0.4 s, 200 µm):** absorbed power = ηP/2, T_max below
   T_boil = 3533 K, outward surface flow, ~zero velocity on solid surface.
4. **Full runs:** 200 → 150 → 100 µm with identical inputs.
5. **Optional:** conduction-only reference (`nOuterCorrectors 0`) to show
   the effect of Marangoni flow; flip the sign of dσ/dT (Fuhrich).

## 6. Mesh-study analysis

- **Compare:** steady pool width, depth, length and cross-section area;
  T_max; |U|_max; centreline cooling rate; G/R at the pool bottom.
- **Refinement ratios:** 1.33 and 1.5 are unequal, so use the generalised
  Richardson/GCI procedure (Celik et al., J. Fluids Eng. 130, 2008), which
  handles non-constant ratios.
- **Robust metrics:** integral quantities (pool area/volume) converge more
  cleanly than point peaks (T_max, |U|_max). Fuhrich notes that peak
  gradients behind the source keep growing under refinement. Report the
  peaks, but only claim grid independence for the metrics whose changes are
  small and monotonic.

## 7. Laser power choice

`scripts/estimate_pool.py` (conduction-only Rosenthal point source, Ti-6Al-4V
at 5 mm/s) was used to pick the power: **1.5 kW × η = 0.35 → 525 W absorbed**
gives a pool about as wide as the 3 mm beam (Rosenthal: 3.1 × 1.6 mm, 8 / 10
/ 16 cells deep on the three meshes). The 0.4 s trial gave T_max ≈ 2410 K
(below boiling) and a wider, shallower pool than Rosenthal (3.3 × 0.5 mm),
as expected with outward Marangoni flow.

## 8. Remaining choices to confirm with the TF

1. Laser power and absorptivity (chosen: 1.5 kW, η = 0.35).
2. Track x = 5 → 45 mm and 1 s of cooling (chosen).
3. Bottom boundary: h = 25 W/m²K without radiation (Pariona's workbench
   h_d has no value); Gao instead keeps the bottom at room temperature.
4. Whether AdditiveFOAM's built-in mushy-zone damping is acceptable, or the
   exact Farzadi form with B should be coded.
5. Which output times and quantities to compare across meshes.
