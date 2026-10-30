# Driving-force check: does the melt move without Marangoni and buoyancy?

**Question.** In the runs without Marangoni flow the melt still moves at about
0.02 m/s. Is that caused by the buoyancy term, or is the solver creating flow
by itself?

**Test.** The R02 settings were run three times to t = 0.05 s:
- absorbed power 500 W, scan speed 4 mm/s, beam radius 0.75 mm;
- Ti-6Al-4V, 100 µm grid;
- identical in every way except the two driving forces of the melt flow.

| Case | Marangoni (dσ/dT, N/m·K) | Buoyancy (β, 1/K) | Peak melt speed at 0.05 s | Peak T | Pool depth × width |
|---|---|---|---|---|---|
| A | −2.6 × 10⁻⁴ | 1.6 × 10⁻⁴ | **0.33 m/s** | 2971 K | 0.37 × 2.21 mm |
| B | 0 | 1.6 × 10⁻⁴ | **4.7 × 10⁻³ m/s** | 4485 K | 0.61 × 1.82 mm |
| C | 0 | 0 | **3 × 10⁻¹⁶ m/s** (zero) | 4530 K | 0.61 × 1.81 mm |

**Result.** With neither driving force (C), the velocity stays at the
round-off level of double-precision arithmetic, about 10⁻¹⁶ m/s, although a
4500 K pool 0.6 mm deep exists. The solver creates no flow by itself. In B, all
of the flow comes from the buoyancy term ρβ(T − T_liq)g. In A, the Marangoni
shear makes the melt about 70 times faster than buoyancy alone.

Cases B and C have practically the same temperature field and pool. Buoyancy
at 0.005 m/s is far too weak to move heat compared with conduction. Marangoni
flow (A) caps the temperature near 3000 K and makes the pool wide and shallow.

**Files**
- `driving_force_check.png`: peak melt speed (log scale), peak temperature and
  pool depth against time for A, B and C.
- `<case>/contours_<t>s.png`: 10 isotherms with velocity vectors (left) and
  velocity-magnitude contours (right), on the symmetry plane and the
  cross-section through the beam, at t = 0.025 and 0.05 s. Below 10⁻⁶ m/s the
  plots show the melt as at rest.
- `<case>/velocity_profiles_<t>s.png`: surface velocity along and across the
  pool, horizontal velocity against depth, and vertical velocity under the beam.
- `<case>/sections_<t>s.png`: temperature fields with the heated zone.

Reproduce with `scripts/buoyancy_check.py` (setup in its docstring). The
pressure solver was capped at 50 iterations in all three cases. With no
driving force (C), the pressure field is zero and the solver otherwise spends
its full 1000 iterations on nothing; in A and B it converges well within 50.
