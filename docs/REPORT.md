# Transient Laser Melt-Pool Simulation of Ti-6Al-4V with Marangoni Flow

**ME323 course project: final report**

Solver: AdditiveFOAM 2.0.0 on OpenFOAM-14 · Material: Ti-6Al-4V ·
15 simulations (12 laser settings + 3 runs without Marangoni flow)

---

## Abstract

A moving Gaussian laser melting the surface of a Ti-6Al-4V block was simulated
in 3D, transient, with heat conduction, latent heat, melt flow driven by surface
tension (Marangoni) and buoyancy, and convective and radiative losses to room
temperature. The model uses the finite-volume solver AdditiveFOAM, extended with
two small source patches so that the Marangoni shear acts only on molten
surface. The solid-liquid transition uses a cosine-smoothed step. Twelve laser
settings were simulated on a fixed 100 µm grid:

- scan speed 4–10 mm/s;
- absorbed power 300–800 W;
- absorptivity 0.30–0.40;
- beam radius 0.5–1.0 mm.

In each run the laser moves 4 mm and then switches off, so every run captures
heating, melting, steady melt-pool flow and the final solidification.

The pools are 0.37–0.60 mm deep and 2.6–5.1 mm wide. Their peak temperature
stays at 2810–3130 K and the surface melt reaches 0.41–0.53 m/s. Marangoni
forces dominate buoyancy by a factor of 365–1384 (Ma/Gr).

Three repeat runs with the surface-tension gradient set to zero isolate the
Marangoni effect:

- **Shape:** without Marangoni flow the pool is 2.3–2.4× deeper and 23–27 %
  narrower.
- **Peak temperature:** it rises by about 2000–2500 K, well above the boiling
  point.

The outward surface flow is therefore the main mechanism that sets the pool
shape and limits its temperature.

All time histories, surface Marangoni quantities and about 70,000
solidification events are exported to one Excel workbook for later data-driven
modelling.

---

## 1. Introduction

Laser surface melting, laser welding and directed energy deposition (DED) all
create a small, moving pool of molten metal. Its size, temperature and the way
it solidifies set the bead geometry, the residual stresses and the
microstructure of the part.

Inside the pool, the strongest force is usually not gravity but the variation of
surface tension with temperature, the **Marangoni** or thermocapillary effect:

- For most alloys, including Ti-6Al-4V, surface tension falls as temperature
  rises (dσ/dT < 0).
- The hot centre under the beam therefore has lower surface tension than the
  cooler edge.
- The surface is pulled outward, from the beam towards the pool rim, at
  velocities of tenths of a metre per second.
- This carries heat sideways and produces a wide, shallow pool (Fuhrich et al.
  2001).

Experiments cannot easily measure these flows: the pool is millimetres in size,
over 2000 K and opaque. A coupled thermal-fluid simulation is the standard way
to study them.

This project builds such a model with open-source tools and uses it to answer
two engineering questions:

1. How do the laser process parameters (speed, power, absorptivity, beam
   radius) change the melt-pool size, peak temperature, flow and solidification
   conditions?
2. How much of the pool's behaviour is caused by Marangoni flow?

## 2. Objectives and scope

| Objective | How it was met |
|---|---|
| Transient 3D heat transfer with a moving Gaussian laser | AdditiveFOAM energy equation with a moving volumetric Gaussian source (§4) |
| Melting and solidification with latent heat | Enthalpy method with a cosine-smoothed solid fraction (§4.3) |
| Melt flow, damped in solid and mushy material | Incompressible Navier–Stokes with Darcy damping and Boussinesq buoyancy (§4.2) |
| Marangoni surface flow | Thermocapillary shear on the top surface, scaled by liquid fraction (§4.4) |
| Convection and radiation to the surroundings | Mixed boundary condition on every outer surface (§4.5) |
| Laser-parameter study on a fixed grid | 12 runs, 100 µm grid (§6) |
| Marangoni as the main factor | Per-step Marangoni metrics plus 3 runs with dσ/dT = 0 (§6.2, §7.3) |
| Record every data point | Excel workbook with 5 sheets, about 72,000 rows (§9) |

**Out of scope:**
- Free-surface deformation, keyhole formation and evaporation. The top surface
  is flat and fixed.
- Powder addition.
- Solid-state phase transformations and residual stress.

## 3. Geometry and process

![3D view of run R02 at t = 0.75 s](../results/R02/3d_0.75s.png)

*Figure 1. R02 at t = 0.75 s, with the half model mirrored to the full width and
the front quadrant cut away. The cyan line is the melt-pool edge. The heated
zone is small compared with the block, as in the reference papers.*

| Item | Value |
|---|---|
| Workpiece | Ti-6Al-4V block, 24 mm long (x) × 20 mm wide (y) × 8 mm deep (z) |
| Modelled domain | Half block, y = 0 to 10 mm, with a symmetry plane on the track centreline (y = 0) |
| Laser path | Along x on the centreline, from x = 8 mm to x = 12 mm (4 mm track), then switched off |
| Simulated time | 1.5 s per run. The laser is on for 0.4–1.0 s, depending on speed; the rest is cooling |
| Initial state | Whole block at room temperature, 293.15 K |
| Surroundings | Air at 293.15 K (convection) and room-temperature enclosure (radiation) |

The original specification was a 50 mm long block. The scripts support it, but
the dataset uses a 24 mm block: the pools are only a few millimetres long and
the shorter block keeps each run near the 30 min budget. Section 7.6 confirms
that the outer walls stay within 31–42 K of room temperature, so the block is
large enough.

## 4. Mathematical model

### 4.1 Assumptions

1. The liquid metal is Newtonian, incompressible and laminar. At peak speeds of
   about 0.5 m/s in a pool under 1 mm deep, the Reynolds number is below about
   1000.
2. The density is constant, except in the buoyancy term (Boussinesq
   approximation).
3. The top surface stays flat and fixed. There is no evaporation, recoil
   pressure or keyhole.
4. The laser is absorbed in a thin surface layer, 50 µm deep. Absorptivity is a
   constant fraction η, so only the absorbed power ηP enters the model.
5. Melting happens over the solidus–liquidus interval, 1878–1928 K, through a
   smooth solid fraction.
6. The process is symmetric about the track centreline (y = 0).

### 4.2 Governing equations

**Mass (incompressible):**

$$\nabla\cdot\mathbf{u} = 0$$

**Momentum** (Boussinesq buoyancy and Darcy damping of flow in the mushy zone):

$$\rho\left(\frac{\partial \mathbf{u}}{\partial t} + \mathbf{u}\cdot\nabla\mathbf{u}\right)
= -\nabla p + \mu\nabla^2\mathbf{u}
- \rho\beta(T - T_\mathrm{ref})\,\mathbf{g}
- \mu\,\frac{180}{\lambda^2}\,\frac{f_s^2}{(1-f_s)^3}\,\mathbf{u}$$

The last term is the Carman–Kozeny resistance of the dendritic mush. It forces
the velocity to zero as the solid fraction f_s approaches 1, so solid metal does
not flow. AdditiveFOAM writes it with a dendrite arm spacing λ instead of the
mushy-zone constant A_mush of Farzadi et al. (2008, Eq. 2). Matching the two
forms gives

$$\lambda = \sqrt{180\,\mu / A_\mathrm{mush}} = \sqrt{180 \times 3.5\times10^{-3} / 10^{8}} \approx 79\ \mu\mathrm{m}$$

for the course values A_mush = 10⁸ kg/m³s and B = 10⁻⁴. The constant B only
prevents division by zero. AdditiveFOAM does the same by capping f_s at 0.95,
which gives the same order of damping.

**Energy** (enthalpy form with latent heat):

$$\rho c_p\left(\frac{\partial T}{\partial t} + \mathbf{u}\cdot\nabla T\right)
= \nabla\cdot(k\nabla T) + \rho L_f\frac{\partial f_s}{\partial t} + Q_\mathrm{laser}$$

The latent heat term releases L_f as the metal solidifies (f_s rises) and
absorbs it on melting. The solver iterates temperature and solid fraction up to
20 times per time step, until they agree to within 10⁻⁸.

### 4.3 Smoothed solid–liquid transition

A sharp step in properties at the melting point is numerically harsh. Following
the smoothed-step form of Gao et al. (2021, Eq. 8), we use a cosine ramp:

$$H(x) = \tfrac12\left(1 + \sin \pi x\right),\quad |x|\le\tfrac12;
\qquad x = \frac{T - T_m}{T_l - T_s},\quad T_m = \frac{T_s + T_l}{2}$$

The ramp is tabulated at 21 points as the solid fraction f_s = 1 − H. Its slope
is continuous at both ends. This single function drives every melting-related
change:

- **Latent heat** release and absorption.
- **Thermal properties:** k and c_p are mixed between the solid and liquid
  curves by f_s.
- **Flow damping:** the Darcy term above.
- **Marangoni shear:** scaled by the liquid fraction f_L = 1 − f_s (§4.4).

A solid region therefore sees only conduction, convection and radiation. Flow
and surface shear switch on smoothly as it melts and off again as it
solidifies.

### 4.4 Marangoni boundary condition (top surface)

The surface tension varies linearly with temperature,
σ = σ₀ + (dσ/dT)(T − T_ref). On a flat surface only the gradient matters, so σ₀
and T_ref drop out. The tangential force balance is (Farzadi et al. 2008,
Eq. 6):

$$\mu\frac{\partial \mathbf{u}_t}{\partial n} = f_L\,\frac{d\sigma}{dT}\,\nabla_s T,
\qquad u_n = 0$$

Here ∇ₛT is the temperature gradient along the surface, and the liquid fraction
f_L makes the shear vanish on solid surface. With dσ/dT = −2.6 × 10⁻⁴ N/m·K the
shear points from hot to cold, so the surface flows outward from under the beam.

### 4.5 Thermal boundary conditions

| Surface | Velocity | Heat flux |
|---|---|---|
| Top, z = 0 | Marangoni shear, no penetration | Laser + h(T − T∞) + εσ_SB(T⁴ − T∞⁴) |
| Symmetry plane, y = 0 | Symmetry | Symmetry (zero flux) |
| Side walls (y = 10 mm, x = 0, x = 24 mm) | No slip | h(T − T∞) + εσ_SB(T⁴ − T∞⁴) |
| Bottom, z = −8 mm | No slip | h(T − T∞), resting on a workbench, no radiation |

T∞ = 293.15 K, h = 25 W/m²K (Gao 2021), ε = 0.54 (Jelinek 2020).

### 4.6 Laser heat source

The source is a Gaussian (super-Gaussian with exponent k = 2), with 1/e²
radius r, deposited in a 50 µm surface layer, moving at constant speed v:

$$q(x,y,z,t) \propto \eta P\,\exp\!\left(-2\,\frac{(x - x_0 - vt)^2 + y^2}{r^2}\right)$$

The source is normalised so that its volume integral equals ηP. With the beam
centred on the symmetry plane, the half model automatically receives ηP/2. This
was checked from the solver output: 262.5 W out of 525 W.

## 5. Material properties (Ti-6Al-4V)

Every value comes from a cited open-access source. Full references and the
alternatives found are in `materials/Ti6Al4V_sources.md`.

| Property | Value | Source |
|---|---|---|
| Solidus / liquidus temperature | 1878 / 1928 K | Yan et al. 2022 |
| Boiling temperature (check only) | 3533 K | Yan et al. 2022 |
| Density ρ | 4428 kg/m³ | Ghosh et al. 2018 |
| Thermal conductivity, solid | 3.32 + 0.01294 T W/m·K | Linear fit to Ghosh et al. 2018, Table 1 |
| Thermal conductivity, liquid | −6.74 + 0.01812 T W/m·K | Linear fit to Ghosh et al. 2018, Table 1 |
| Specific heat, solid | 427.9 + 0.399 T J/kg·K | Linear fit to Ghosh et al. 2018, Table 3 |
| Specific heat, liquid | 1130 J/kg·K | Much et al. 2024 (after Boivineau 2006) |
| Latent heat of fusion | 2.90 × 10⁵ J/kg | Yan et al. 2022 |
| Dynamic viscosity μ | 3.5 × 10⁻³ Pa·s | Much et al. 2024 (after Mohr 2020) |
| dσ/dT | −2.6 × 10⁻⁴ N/m·K | Yan et al. 2022 |
| Thermal expansion β | 1.6 × 10⁻⁴ 1/K | MSAM 2025 |
| Emissivity ε | 0.54 | Jelinek et al. 2020 |
| Convection coefficient h | 25 W/m²·K | Gao et al. 2021 |
| Mushy-zone constants A_mush, B | 10⁸, 10⁻⁴ | Course specification (Farzadi Eq. 2 form) |

## 6. Numerical method

### 6.1 Solver and discretisation

| Item | Setting |
|---|---|
| Code | AdditiveFOAM 2.0.0 (ORNL), built on OpenFOAM-14 (openfoam.org); 8 MPI processes |
| Method | Finite volume, collocated grid, PIMPLE pressure–velocity coupling |
| Time | First-order implicit (Euler). Adaptive Δt from Courant ≤ 0.9, diffusion number ≤ 10 and melt-front Courant ≤ 1 |
| Convection terms | First-order upwind (robust for the steep thermal and velocity layers) |
| Diffusion terms | Second order; harmonic interpolation of k across cells |
| Linear solvers | GAMG for pressure, PBiCGStab for temperature |
| Hardware | Intel i5-12450H (8 cores), 15 GB RAM, Ubuntu 22.04 |

### 6.2 Mesh

The mesh is block-structured hexahedral with **288,750 cells**:

- **Fine region:** uniform 100 µm cells over x = 6–18 mm, y = 0–4 mm and
  z = 0 to −2 mm. This contains every pool (at most 0.6 mm deep and 2.5 mm half
  width) with margin.
- **Outer region:** cells graded smoothly up to 1 mm towards the far walls,
  where gradients are small.

With this grid a pool is 4–6 cells deep and 26–50 cells wide. The grid is the
same in every run, as the design of experiments requires; only the laser
settings change.

### 6.3 Changes to the solver

AdditiveFOAM's tutorials are conduction-only. Three changes were needed to
solve the flow correctly. All are kept as patch files in `setup/patches/` and
applied by the install script.

1. **Flow switched on:** `nOuterCorrectors 1` in `fvSolution`. The value 0 in
   the tutorials skips the momentum and pressure equations entirely.
2. **`marangoni-assignable.patch`:** marks the Marangoni boundary as not
   assignable by the pressure step. Without it, the pressure correction
   pushed mass through the closed top surface and the run aborted with a
   continuity error.
3. **`marangoni-liquid-fraction.patch`:** multiplies the Marangoni shear by the
   liquid fraction (Farzadi Eq. 6). Without it, the stress would also act on
   solid surface cells.

### 6.4 Verification checks (every run)

| Check | Result |
|---|---|
| Absorbed power in the half model | Exactly ηP/2 (from the solver's power output) |
| Maximum Courant number | 0.91 (limit 0.9 applies before the step) |
| Mass conservation per step | Local continuity error about 10⁻¹⁵ |
| Enthalpy–temperature loop | Converged every step (≤ 20 iterations, 10⁻⁸ tolerance) |
| Fatal errors or crashes | None in any of the 15 runs |
| Outer walls at the end of the run | 324–335 K, near ambient (§7.6) |
| Peak temperature vs boiling point | All Marangoni runs below 3533 K at steady state (§7.2) |

A mesh-independence study was not part of this design of experiments (the grid
is fixed). Section 8 discusses what this means for the numbers.

## 7. Design of experiments

### 7.1 Laser-parameter study

Four scan speeds, each with three combinations of power, absorptivity and beam
radius. The ranges follow the reference papers: a small beam and moderate power
give a pool that is small compared with the part.

| Run | Speed (mm/s) | Laser power (W) | Absorptivity | Absorbed power (W) | Beam radius (mm) | Line energy (J/mm) |
|---|---|---|---|---|---|---|
| R01 | 4 | 1000 | 0.30 | 300 | 0.50 | 75 |
| R02 | 4 | 1429 | 0.35 | 500 | 0.75 | 125 |
| R03 | 4 | 1750 | 0.40 | 700 | 1.00 | 175 |
| R04 | 6 | 1000 | 0.40 | 400 | 0.50 | 67 |
| R05 | 6 | 2000 | 0.30 | 600 | 0.75 | 100 |
| R06 | 6 | 2286 | 0.35 | 800 | 1.00 | 133 |
| R07 | 8 | 1000 | 0.35 | 350 | 0.60 | 44 |
| R08 | 8 | 1375 | 0.40 | 550 | 0.75 | 69 |
| R09 | 8 | 2500 | 0.30 | 750 | 1.00 | 94 |
| R10 | 10 | 1500 | 0.30 | 450 | 0.50 | 45 |
| R11 | 10 | 1857 | 0.35 | 650 | 0.75 | 65 |
| R12 | 10 | 2000 | 0.40 | 800 | 0.90 | 80 |

### 7.2 Marangoni comparison

**R02_noMa, R06_noMa and R11_noMa** repeat R02, R06 and R11 (one per speed
group, spanning low to high power) with dσ/dT = 0. Everything else is
identical, including buoyancy. Each pair isolates the effect of Marangoni flow.

### 7.3 An earlier design that was rejected

A first design aimed for a pool at least 2.5 mm deep, using 2–3.5 kW absorbed,
a 2.5 mm beam radius and 1–5 mm/s. It reached 3.4 mm depth, but only by heating
most of the block:

- 78–93 % of the volume ended more than 100 K above ambient;
- the side walls reached up to 2030 K.

This does not match a real process, where a small pool sits in cool material.
It also confirmed the Marangoni physics: with dσ/dT < 0, extra power mostly
widens the pool rather than deepening it. Those results are archived in
`results/archive_overheated/` and are not part of the dataset.

## 8. Results

All "quasi-steady" values are averages over the last 40 % of the laser-on time,
once the pool has stopped growing. Widths are full widths (both halves).

### 8.1 Evolution of a typical run (R02)

![R02 history](../results/R02/history.png)

*Figure 2. R02: peak temperature, peak melt speed and pool size. The laser
switches off at 1 s (red line); the shaded band is the quasi-steady window.*

A run passes through four stages:

1. **Solid heating** (first ≈ 1–2 ms): conduction, convection and radiation
   only. The surface reaches the solidus after 0.6–1.9 ms, depending on power
   density.
2. **Melting and spreading** (to ≈ 0.3 s): the pool grows quickly. Marangoni
   flow starts as soon as the surface melts and reaches about 0.4 m/s within
   0.1 s.
3. **Quasi-steady pool** (≈ 0.4 s until the laser switches off): peak
   temperature, flow speed and depth are steady. Width and length still grow
   by 3–4 % as heat slowly builds up in the block.
4. **Solidification** (after the laser switches off): the peak temperature
   falls to the liquidus within about 20 ms. The temperature then plateaus at
   the melting range while latent heat is released, and the pool is fully
   solid 45–120 ms after switch-off. The flow stops with it.

![R02 sections](../results/R02/sections_0.75s.png)

*Figure 3. R02 at t = 0.75 s: the symmetry plane (top) and the cross-section
through the beam (bottom). The left panels show the heated zone, which fades to
ambient inside the block. The right panels show close-ups of the pool with
velocity arrows. The surface flows outward from under the beam, turns down at
the rim and returns along the bottom, forming two counter-rotating cells in the
cross-section.*

### 8.2 Effect of the laser parameters

![pool vs line energy](figures/pool_size_vs_line_energy.png)

*Figure 4. Quasi-steady pool depth and width against line energy (absorbed
power ÷ scan speed).*

![speed effects](figures/speed_effects.png)

*Figure 5. Peak temperature, maximum Marangoni shear stress and median cooling
rate against scan speed.*

| Run | Speed (mm/s) | Absorbed power (W) | Depth (mm) | Width (mm) | Length (mm) | Peak T (K) | Peak speed (m/s) | Width/depth |
|---|---|---|---|---|---|---|---|---|
| R01 | 4 | 300 | 0.40 | 2.65 | 2.78 | 2853 | 0.41 | 6.6 |
| R02 | 4 | 500 | 0.51 | 3.97 | 4.15 | 2927 | 0.46 | 7.8 |
| R03 | 4 | 700 | 0.60 | 5.06 | 5.30 | 2951 | 0.47 | 8.5 |
| R04 | 6 | 400 | 0.41 | 3.04 | 3.23 | 3052 | 0.49 | 7.4 |
| R05 | 6 | 600 | 0.50 | 4.12 | 4.37 | 3051 | 0.50 | 8.3 |
| R06 | 6 | 800 | 0.58 | 5.01 | 5.33 | 3033 | 0.50 | 8.7 |
| R07 | 8 | 350 | 0.37 | 2.59 | 2.79 | 2814 | 0.41 | 6.9 |
| R08 | 8 | 550 | 0.46 | 3.59 | 3.86 | 2965 | 0.48 | 7.9 |
| R09 | 8 | 750 | 0.51 | 4.46 | 4.78 | 2980 | 0.49 | 8.7 |
| R10 | 10 | 450 | 0.38 | 2.90 | 3.18 | 3134 | 0.53 | 7.6 |
| R11 | 10 | 650 | 0.46 | 3.79 | 4.12 | 3086 | 0.52 | 8.3 |
| R12 | 10 | 800 | 0.50 | 4.37 | 4.74 | 3110 | 0.53 | 8.8 |

**Observations:**

- **The pools are wide and shallow.** Width/depth is 6.6–8.8 in every run.
  This is the typical conduction-mode pool with outward Marangoni flow
  (Fuhrich 2001). Pariona et al. (2018) and Gao et al. (2021) show similar
  shapes.
- **Power widens more than it deepens.** At 4 mm/s, going from R01 to R03
  (absorbed power 300 → 700 W, beam radius 0.5 → 1.0 mm) increases the width
  by 91 % but the depth by only 49 %. The surface flow carries the extra heat
  sideways. The same pattern appears at every speed.
- **Line energy is the best single predictor of pool size** (Figure 4). At the
  same line energy, faster scans give a slightly larger pool, because their
  power is higher and the heat has less time to conduct away.
- **Peak temperature is almost insensitive to power.** It stays at 2810–3130 K
  while the power more than doubles. Stronger heating drives stronger
  convection, which spreads the heat. Faster scans run about 150 K hotter,
  because the beam reaches fresh, colder metal and the steeper surface
  gradients need a higher peak.
- **Marangoni stress rises with speed** (Figure 5): about 435 Pa at 4 mm/s and
  about 680 Pa at 10 mm/s. Faster scans give sharper surface temperature
  gradients (1.7 K/µm at 4 mm/s, 2.6–2.8 K/µm at 10 mm/s), and the shear is
  proportional to that gradient.
- **Every peak temperature is below the boiling point** (3533 K), so leaving
  evaporation out of the model is acceptable for these runs.

### 8.3 Effect of Marangoni flow

![Marangoni on/off](figures/marangoni_on_off.png)

*Figure 6. Quasi-steady pool depth, width, peak temperature and peak speed,
with and without Marangoni flow.*

![R02 with and without Marangoni](figures/history_R02_on_off.png)

*Figure 7. Time history of R02 with and without Marangoni flow.*

| Pair | Depth (mm) with → without | Width (mm) with → without | Width/depth with → without | Peak T (K) with → without | Peak speed (m/s) with → without | Time to solidify after switch-off (ms) with → without |
|---|---|---|---|---|---|---|
| R02 | 0.51 → **1.19** (×2.3) | 3.97 → 3.07 (−23 %) | 7.8 → 2.6 | 2927 → 4941 | 0.46 → 0.020 | 86 → 170 |
| R06 | 0.58 → **1.35** (×2.3) | 5.01 → 3.74 (−25 %) | 8.7 → 2.8 | 3033 → 5259 | 0.50 → 0.025 | 106 → 230 |
| R11 | 0.46 → **1.09** (×2.4) | 3.79 → 2.78 (−27 %) | 8.3 → 2.6 | 3086 → 5576 | 0.52 → 0.018 | 67 → 142 |

The cross-sections show the difference directly:

![R02 sections without Marangoni](../results/R02_noMa/sections_0.75s.png)

*Figure 8. R02_noMa at t = 0.75 s. Compare with Figure 3. With buoyancy alone
the flow is about 20× weaker (≈ 0.02 m/s). The pool is a deep hemisphere, set
by conduction, with a hot core of nearly 5000 K.*

**Interpretation:**

1. **Marangoni flow is a convective heat spreader.** Fast outward surface flow
   carries heat from under the beam to the rim and along the surface. This
   lowers the peak temperature by about 2000–2500 K and turns a hemispherical
   conduction pool (width/depth ≈ 2.7) into a wide, shallow one (≈ 8).
2. **Without it, the model becomes unphysical.** The peak temperatures of
   4940–5590 K are far above boiling. A real pool would evaporate and its
   surface would deform; neither effect is in this model. The no-Marangoni runs
   are useful only as a numerical experiment. Their peak temperatures should
   not be read as predictions.
3. **The no-Marangoni pool takes about twice as long to solidify** after the
   laser switches off. Its larger volume and hotter core hold more heat.
4. **Marangoni flow also roughly halves the run time** (6–8 min without, 15–33
   min with). The fast flow limits the time step through the Courant number.

### 8.4 Dimensionless analysis

These numbers follow the definitions of Farzadi et al. (2008):

| Number | Definition | Range (Marangoni runs) | Meaning |
|---|---|---|---|
| Marangoni, Ma | ρ L_R ΔT \|dσ/dT\| / μ² (Eq. 17) | 1.2–2.7 × 10⁵ | Strong thermocapillary driving |
| Grashof, Gr | g β L_B³ ΔT ρ² / μ² (Eq. 15) | 83–717 | Weak buoyancy |
| Ma/Gr | Surface tension vs buoyancy (Eq. 18) | **365–1384** | Marangoni force dominates by 2–3 orders of magnitude |
| Péclet, Pe | u ρ c_p L_R / k (Eq. 14) | 58–146 | Convection carries ≫ conduction: flow sets the pool shape |
| Reynolds, Re | ρ u L_R / μ | 410–1040 | Laminar, as assumed |

Here L_R is the pool half-width, L_B = width/8, ΔT = T_max − T_solidus, and u
is the mean surface speed.

- **Pe ≫ 1** explains why switching Marangoni off changes the shape so much:
  heat transport in the pool is dominated by flow, not conduction.
- **Ma/Gr is largest for the small pools** (R01, R07, R10). Gr scales with the
  cube of pool size, so buoyancy matters least in small pools.
- **Farzadi's boundary-layer scale** (Eq. 20) predicts surface speeds of
  1.6–2.2 m/s. The simulation gives 0.4–0.5 m/s, about 4× lower. The scaling
  assumes an infinite, undamped boundary layer. The real pool is shallow and
  its edge is damped by the mush, which slows the flow. The scale still gives
  the correct order of magnitude and the trend with speed.
- **Surface flow direction:** the average outward component of the surface
  velocity, relative to the hottest point, is +0.91 to +0.95 (+1 means fully
  outward). This confirms outward Marangoni flow, as expected for dσ/dT < 0.

### 8.5 Solidification conditions

![solidification map](figures/solidification_map.png)

*Figure 9. Temperature gradient G against solidification rate R at the
solidification front, median along the track while the laser is on. The lines
mark constant G/R.*

| Speed (mm/s) | Median cooling rate (K/s) | G (K/mm) | R (mm/s) | G/R (K·s/mm²) |
|---|---|---|---|---|
| 4 | 960–1790 | 790–1090 | 0.9–1.5 | 840–900 |
| 6 | 1470–2700 | 820–1000 | 1.5–2.3 | 530–630 |
| 8 | 2300–3760 | 860–1050 | 2.1–3.1 | 420–500 |
| 10 | 2830–4260 | 860–1020 | 2.4–3.8 | 370–480 |

The ranges in each row cover the three runs at that speed.

**Microstructure trends:**

- **R is always below the scan speed.** At each point the solidification front
  moves at R = v cos θ, where θ is the angle between the front's normal and the
  scan direction. R approaches v only at the tail of the pool.
- **Faster scans raise the cooling rate G·R.** That favours finer
  microstructure: smaller prior-β grains and finer α′/α laths in Ti-6Al-4V.
- **Faster scans lower G/R** (from about 870 to about 420 K·s/mm²). That moves
  solidification towards less columnar, more equiaxed growth. Ti-6Al-4V tracks
  usually remain columnar; the numbers here show the direction of the trend,
  not a morphology prediction.
- **Without Marangoni flow, R rises and G/R falls.** The deeper, rounder pool
  makes the front turn towards the scan direction sooner.
- **The end crater cools 1.3–3.1× faster than the track** in the Marangoni
  runs (median 2,200–6,700 K/s). It is recorded separately, as `crater_*` columns, so that it does not
  bias the track statistics.

### 8.6 Thermal footprint in the block

At t = 1.5 s, 0.5–1.1 s after the laser switched off, every outer wall is at
324–335 K, within 42 K of ambient. The left panels of Figure 3 show the
temperature falling to room temperature within about 4 mm of the track. The
block is therefore large enough: the boundaries do not affect the pool, which
was the problem with the rejected high-power design (§7.3).

## 9. Data produced

`results/melt_pool_dataset.xlsx` holds every run. All sheets carry the `case`
name and the run's input parameters on every row, so they can be used directly
as machine-learning tables (as in Wang et al. 2024).

| Sheet | Rows | Content |
|---|---|---|
| `runs` | 15 | One row per run: 9 inputs and 37 outputs (pool size, temperatures, speeds, timings, solidification statistics, Marangoni quantities, dimensionless numbers) |
| `timeseries` | 2,265 | Every run every 0.01 s: beam position, peak T, peak speed, pool length, width and depth at liquidus and solidus, Ma, Gr, Ma/Gr, Pe, Re |
| `marangoni` | 90 | Every 0.25 s snapshot: molten surface area, surface temperature gradient, Marangoni shear (max and mean), surface speed, flow direction, dimensionless numbers |
| `solidification` | 69,811 | Every solidification event in the fine region: position, time, cooling rate, G, R, G/R, G·R, and whether the laser was on |
| `columns` | 80 | Description and unit of every column |

Each run folder `results/<run>/` also holds:
- `summary.json`;
- the time-history plot;
- 2D sections at every 0.25 s;
- 3D cut-away images (full width, mirrored);
- `marangoni_snapshots.csv`.

Full-block 3D fields for ParaView are written to `cases/<run>/VTK_full/`.

## 10. Limitations

1. **Flat, fixed surface; no evaporation.** These are acceptable at the
   simulated peak temperatures (below 3533 K). They are not acceptable for the
   no-Marangoni runs, which are a numerical experiment only.
2. **Fixed 100 µm grid, no mesh-independence study.** The pools are only 4–6
   cells deep, so depth is resolved to about ±0.05 mm (half a cell). Peak
   speeds and surface gradients would probably rise somewhat on a finer grid,
   because the velocity boundary layer under the surface is thin (Fuhrich
   2001). The trends between runs are more reliable than the absolute values.
3. **Short track (4 mm).** Depth and peak temperature reach steady state, but
   width and length still grow 3–4 % by switch-off.
4. **Absorptivity is a constant multiplier.** Only the absorbed power ηP enters
   the model, so absorptivity is a dataset column but not an independent
   physical input.
5. **Mushy-zone damping.** AdditiveFOAM's form with λ = 79 µm and f_s capped at
   0.95 is equivalent in practice, but not identical, to Farzadi's
   A_mush/(f_L³ + B) form.
6. **Constant density and linear dσ/dT.** Sulphur or oxygen in the surface can
   change the sign of dσ/dT at high temperature and reverse the flow (Fuhrich
   2001). That is not modelled.

## 11. Conclusions

1. A 3D transient thermo-fluid model of laser melting of Ti-6Al-4V was built on
   open-source AdditiveFOAM/OpenFOAM. Three changes make the Marangoni physics
   work: the flow solve switched on, a fix for the closed top boundary, and
   liquid-fraction scaling of the surface shear. The model uses cited material
   data and a smoothed phase transition.
2. Across 12 laser settings, the pools are 0.37–0.60 mm deep, 2.6–5.1 mm wide
   and 6.6–8.8 times wider than deep. Pool size follows line energy. Peak
   temperature stays near 2800–3100 K regardless of power, and cooling rates
   are 10³–4 × 10³ K/s, rising with scan speed.
3. **Marangoni flow is the dominant mechanism in the pool:**
   - Ma/Gr is 365–1384 and Pe is 58–146.
   - Switching it off makes the pool 2.3–2.4× deeper and 23–27 % narrower.
   - The peak temperature rises by about 2000–2500 K.
   - Solidification takes about twice as long.
4. Faster scanning raises the cooling rate and lowers G/R, which points to a
   finer and less columnar solidification structure.
5. The complete dataset (15 runs, about 72,000 rows) is ready for the planned
   Bayesian-optimisation / machine-learning study.

**Future work:**
- A mesh-refinement check on two or three runs (50 µm in the pool).
- A longer track for fully steady widths.
- Free-surface deformation and evaporation for higher powers.
- Validation against a measured Ti-6Al-4V bead cross-section.

## References

1. S. Gao, Y. Feng, J. Wang, M. Qin, O. P. Bodunde, W. H. Liao, P. Guo, "Molten
   pool characteristics of a nickel-titanium shape memory alloy for directed
   energy deposition", *Optics & Laser Technology* 142 (2021) 107215.
2. A. Farzadi, S. Serajzadeh, A. H. Kokabi, "Modeling of heat transfer and
   fluid flow during gas tungsten arc welding of commercial pure aluminum",
   *Int. J. Adv. Manuf. Technol.* 38 (2008) 258–267.
3. M. M. Pariona, A. F. Taques, L. A. Woiciechowski, "The Marangoni effect on
   microstructure properties and morphology of laser-treated Al-Fe alloy with
   single track by FEM: varying the laser beam velocity", *Int. J. Heat Mass
   Transfer* 119 (2018) 10–19.
4. T. Fuhrich, P. Berger, H. Hügel, "Marangoni effect in laser deep penetration
   welding of steel", *J. Laser Appl.* 13 (2001) 178–186.
5. J. Wang, E. S. Kim, H. S. Kim, B.-J. Lee, "A machine learning approach for
   predicting evaporation-induced composition variability in directed energy
   deposition in-situ alloying", *Additive Manufacturing* 92 (2024) 104384.
6. S. Ghosh et al., "Simulation of temperature, stress and microstructure
   fields during laser deposition of Ti-6Al-4V" (2018),
   [arXiv:1809.01056](https://arxiv.org/abs/1809.01056).
7. J. Yan, Q. Zhu, Z. Zhao, "Computational thermal multi-phase flow for metal
   additive manufacturing" (2022),
   [arXiv:2206.04799](https://arxiv.org/abs/2206.04799).
8. N. Much et al., "Improved accuracy of continuum surface flux models for
   metal additive manufacturing melt pool simulations" (2024),
   [arXiv:2401.12114](https://arxiv.org/abs/2401.12114).
9. "In situ electromagnetic field manipulation during LMD", *Materials Science
   in Additive Manufacturing* 4(1) (2025),
   [doi:10.36922/msam.8332](https://doi.org/10.36922/msam.8332).
10. B. Jelinek et al., "Two-dimensional thermal finite element model of
    directed energy deposition: matching melt pool temperature profile with
    pyrometer measurement" (2020),
    [arXiv:2007.01433](https://arxiv.org/abs/2007.01433).
11. AdditiveFOAM 2.0.0, Oak Ridge National Laboratory,
    <https://github.com/ORNL/AdditiveFOAM>.
12. OpenFOAM-14, The OpenFOAM Foundation, <https://openfoam.org>.

## Appendix A: full output table

The full table, with every input and output column, is the `runs` sheet of
`results/melt_pool_dataset.xlsx`. Selected values not shown above:

| Run | First melt (ms) | Fully solid after switch-off (ms) | Cooling rate, median (K/s) | Max Marangoni stress (Pa) | Max surface ∇T (K/mm) | Ma/Gr | Pe |
|---|---|---|---|---|---|---|---|
| R01 | 1.0 | 52 | 1789 | 441 | 1781 | 1307 | 62 |
| R02 | 1.4 | 86 | 1294 | 431 | 1705 | 592 | 106 |
| R03 | 1.9 | 118 | 957 | 433 | 1678 | 365 | 145 |
| R04 | 0.7 | 56 | 2698 | 513 | 1972 | 1037 | 78 |
| R05 | 1.2 | 83 | 1773 | 527 | 2109 | 582 | 113 |
| R06 | 1.6 | 106 | 1467 | 547 | 2169 | 380 | 146 |
| R07 | 1.3 | 43 | 3760 | 599 | 2305 | 1384 | 58 |
| R08 | 1.3 | 66 | 3080 | 602 | 2317 | 716 | 95 |
| R09 | 1.8 | 85 | 2304 | 578 | 2337 | 447 | 128 |
| R10 | 0.6 | 49 | 4256 | 689 | 2794 | 1186 | 73 |
| R11 | 1.0 | 67 | 3422 | 670 | 2577 | 716 | 101 |
| R12 | 1.2 | 78 | 2829 | 678 | 2608 | 535 | 122 |
| R02_noMa | 1.4 | 170 | 1819 | 0 | 2690 | 0 | 3 |
| R06_noMa | 1.6 | 230 | 1878 | 0 | 2920 | 0 | 5 |
| R11_noMa | 1.0 | 142 | 3418 | 0 | 4150 | 0 | 2 |

## Appendix B: reproducing the results

```bash
source setup/env.sh                                   # OpenFOAM-14 + AdditiveFOAM
python scripts/make_cases.py                          # cases/R01 ... from config/baseline.json
nohup bash scripts/run_all.sh > run_all.log 2>&1 &    # run, analyse, export (resumable)
python scripts/report_figures.py                      # figures in docs/figures/
```

Installation is described in `docs/SETUP.md`. The case setup and solver
details are in `docs/SIMULATION_PLAN.md`.
