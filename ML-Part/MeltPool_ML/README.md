# MeltPool_ML: the Wang et al. (2024) method on our melt-pool simulations

This applies the machine-learning pipeline of Wang et al., *Addit. Manuf.* 92 (2024) 104384
(replicated in `../Replicated_Paper`) to the AdditiveFOAM Ti-6Al-4V runs of this project:
feature-set study, k-fold ensembles of the paper's five algorithms plus a Gaussian process,
Optuna tuning with the paper's Eq. 1, inverse design with Eq. 2 (solved by Bayesian
optimisation), and Surrogate SHAP. The inverse design is aimed at the planned experiment,
where the only measurement is the top-surface track width.

## Running it

Use `python3.11` (torch and optuna are installed there, not in 3.10).

| Step | Script | Output |
|---|---|---|
| 0 | `build_dataset.py` | `data/runs.csv` (46 runs), `data/events.csv.gz` (79,259 events), `data/liquid.json` |
| 1 | `step1_feature_sets.py` | `results/fig3_feature_sets.png`, `feature_sets.csv` |
| 2 | `step2_ensemble.py [--retune]` | `models/run_params.json`, `models/run_composite.pkl`, `results/fig4b_*.png`, `fig4c_parity.png`, `run_model_metrics.csv`, `run_predictions_oos.csv` |
| 3 | `step3_events.py [--retune]` | `models/event_params.json`, `results/fig_events_parity.png`, `event_model_metrics.csv` |
| 4 | `step4_experiment.py` | `results/fig5_experiment_width.png`, `fig_experiment_width_exponent.png`, `fig_experiment_inverse.png`, `experiment_*.csv` |
| 5 | `step5_shap.py` | `results/fig6a_shap_importance.png`, `fig6b_shap_main.png`, `fig7_shap_interactions.png` |

`--smoke` on steps 2 and 3 runs 2 tuning trials into `smoke/` (git-ignored) to check the code.
Steps 4 and 5 use the saved run-level model, so step 2 must run first. Pickled models are not
committed (22 MB); rerun step 2 to rebuild them.

## Data

- **Runs:** R01–R12 and their noMa copies, the V set (incl. V1400_v6_flat) and the 18 U runs; 46 in
  total. All `*_50um` runs (not fully simulated) and `results/archive_overheated` are left out.
- **Inputs:** absorbed power P_abs = P × absorptivity (only the product enters the heat source),
  speed v, beam radius r, beam profile exponent k (2 Gaussian, 10/20 flat top), and the flags
  `flow` and `marangoni`. Buoyancy is on in exactly the runs where flow is on, so a separate
  buoyancy flag would be perfectly collinear and is dropped (B = flow on, Marangoni off).
- **Run targets:** quasi-steady depth, width, length, T_max, mean surface speed, and the medians of
  cooling rate, G and R along the track. Depth and width are the interpolated liquidus values,
  not the event-based fusion zone, which is snapped to the 100 µm cells.
- **Ma and Pe** are not learned: they are calculated from the predicted T_max, width and surface
  speed with the definitions of `scripts/export_excel.py` (Farzadi et al. 2008). Applied to the
  simulated T_max and width this reproduces the snapshot Ma to 0.2 % (median ratio 0.998).
- **Events:** every laser-on solidification event with R > 0. Position is scaled by the run's pool:
  z/depth, y/half-width, and distance from the track start in mm. Splits are always grouped by run.

## Results

### Input set (Fig. 3 analogue)

Default XGBoost, 10-fold CV, 5 repeats, mean R² over the 8 targets:

| Input set | mean R² |
|---|---|
| **[P_abs, v, r]** | **0.898 ± 0.003** |
| [P_abs/v, v, r] | 0.856 ± 0.014 |
| [P_abs/√(v r³), v, r] (normalised enthalpy) | 0.854 ± 0.006 |

Unlike the paper (where the engineered SED won), the raw inputs win here; the runs sit on
factorial grids, which tree splits on raw P and v follow well. The enthalpy feature is the best
single input for T_max (R² 0.95 vs 0.83).

### Run-level model (Fig. 4)

Holdout (random 10 %, seed 0): R04, R09, U1000_v9_MaB, U2000_v3_MaB, U2000_v6_MaB.
Eq. 1 scores after tuning: SVM 0.815, GP 0.782, Bayesian ridge 0.768, neural net 0.754,
XGBoost 0.444, random forest −0.340. The composite has 72 models.

R² in log space, every run predicted out-of-sample (5-fold over runs):

| | depth | width | length | T_max | U_surf | cooling rate | G | R |
|---|---|---|---|---|---|---|---|---|
| composite (6 algorithms) | 0.972 | 0.954 | 0.967 | 0.932 | 0.975 | 0.815 | 0.897 | 0.824 |
| Gaussian process alone | 0.994 | 0.993 | 0.995 | 0.984 | 0.992 | 0.917 | 0.943 | 0.896 |
| SVR alone | 0.994 | 0.990 | 0.994 | 0.975 | 0.994 | 0.870 | 0.943 | 0.847 |
| random forest alone | 0.805 | 0.609 | 0.681 | 0.678 | 0.897 | 0.071 | 0.484 | 0.140 |
| power-law baseline | 0.983 | 0.986 | 0.988 | 0.992 | 0.999 | 0.746 | 0.836 | 0.809 |

Mean absolute percentage error of the composite (out-of-sample): depth 5.6 %, width 4.2 %,
T_max 3.1 %, G 3.1 %, cooling rate 17 %, R 17 %. Ma derived from the predictions: R² 0.98,
6.8 % error; Pe (log): R² 0.99.

Points to state in the report:
- The equal-weight composite is **beaten by the GP and SVR alone** and, for depth, width and
  T_max, by a log-space power-law regression with flow/Marangoni terms. With 46 deterministic
  runs, smooth models do best.
- **Random forest** (Eq. 1 score below zero) and, for some questions, **Bayesian ridge** pull the
  composite down and inflate σ. The paper dropped KNN for a low optimisation score; the same rule
  would drop random forest here. Not done yet: it is the user's decision.
- The hyperparameters were tuned on the 41 training runs, which also appear in the outer 5-fold
  test folds, so the out-of-sample scores are slightly optimistic.

### Experiment link (Fig. 5 analogue)

Planned experiment: flat-top 3 mm beam (r = 1.5 mm, k = 20), 1000 and 1400 W, 6 and 9 mm/s
(12 mm/s if time allows), Marangoni and buoyancy always present in reality. No optical
microscope is available, so only the **track width** is measured.

Predicted widths at η = 0.35 (mm, ±3σ), Marangoni + buoyancy:

| | 6 mm/s | 9 mm/s | 12 mm/s |
|---|---|---|---|
| 1000 W | 2.85 ± 0.14 (sim 2.83) | 2.64 ± 0.27 (sim 2.61) | 2.52 ± 0.43 |
| 1400 W | 3.54 ± 0.38 | 3.23 ± 0.22 | 3.08 ± 0.29 |

Full table for all modes and outputs: `results/experiment_predictions.csv`.

**Marangoni test without knowing the absorptivity.** Width scales as W ∝ (ηP)^a, so in
W(1400 W)/W(1000 W) = 1.4^a the absorptivity cancels; a = ln(W₁₄₀₀/W₁₀₀₀)/ln 1.4 is computed
from the two measured widths at each speed. Model values (mean of XGBoost, SVR, neural net, GP;
random forest and Bayesian ridge cannot represent a mode-dependent exponent, see
`experiment_width_ratio.csv`):

| mode | a at 6 / 9 / 12 mm/s (±3σ) |
|---|---|
| Marangoni + buoyancy | 0.71 / 0.64 / 0.63 (±0.20–0.24) |
| buoyancy only | 0.51 / 0.49 / 0.49 (±0.11–0.16) |
| conduction only | 0.47 / 0.45 / 0.45 (±0.04–0.12) |

The Marangoni case is separate at 1σ but the 3σ bands touch: a 2–3σ discrimination. The
simulations' own power-law fits (`results/ta_fits.csv`) give 0.70 / 0.49 / 0.44.

**Absorptivity by Bayesian optimisation** (Optuna GPSampler, 40 trials, χ² of the widths with
measurement and model σ in quadrature). Self-test on simulated widths with known η = 0.35:
η = 0.346 (1σ range 0.335–0.360). With real data, fill `experiment/measured_widths.csv` and
rerun step 4.

**Eq. 2 inverse design: speed for a target width at 1400 W.** The paper's
Fp = max(floor, |μ − W*|)/σ (floor 0.05 mm = photo resolution) with the 0.2 distance filter,
minimised over speed by BO and by random search (the paper's method):

| target W* [mm] | Eq. 2 + BO | Eq. 2 + random | direct (μ = W*) |
|---|---|---|---|
| 3.19 | 10.7 mm/s | 10.7 mm/s | 9.8 mm/s |
| 3.31 | 8.0 mm/s | 9.1 mm/s | 8.3 mm/s |
| 3.43 | 6.7 mm/s | 6.7 mm/s | 7.2 mm/s |

Because σ is in the denominator, Eq. 2 favours speeds where the ensemble disagrees more and
accepts missing W* by up to the floor; the direct column is where the model actually predicts
W*. In the lab, the speed for W* comes from interpolating the measured widths between the
6 / 9 / 12 mm/s tracks. On this one-dimensional search BO is no faster than random search.

### Surrogate SHAP (Figs. 6–7)

Grid: P_abs 300–800 W × v 3–12 mm/s × r 0.5–1.5 mm (21 values each), Marangoni on/off,
Gaussian beam: 18,522 points; one default XGBoost surrogate per output (R² > 0.9999).
Share of mean |SHAP|:

| output | P_abs | v | r | Marangoni |
|---|---|---|---|---|
| depth | 29 % | 14 % | 3 % | 54 % |
| width | 46 % | 20 % | 3 % | 32 % |
| T_max | 28 % | 3 % | 19 % | 50 % |
| cooling rate | 26 % | 45 % | 8 % | 21 % |
| G | 63 % | 24 % | 9 % | 5 % |
| R | 16 % | 43 % | 5 % | 37 % |

The strongest interaction for depth, width and T_max is power × Marangoni: with Marangoni on,
width grows faster with power and depth grows slower (outward surface flow carries heat
sideways). Part of the grid lies outside the simulated runs; there the SHAP values describe the
model, not data.

## Experiment protocol: track width from a photo

1. Phone straight above the track, surface parallel to the camera; 1× or 2× lens, no digital zoom.
2. Steel ruler with mm marks flat beside the track, at the height of the surface.
3. Diffuse light from a low angle so the rippled melted band stands out. Measure the melted band,
   **not** the coloured oxide halo around it (a cooler isotherm, it reads too wide).
4. One photo per track over its steady middle; label each track (power, speed) on the block or
   in the frame.
5. In ImageJ: set the scale from the ruler, take 5–10 width readings along the steady part.
   Enter mean, standard deviation and the number of readings in
   `experiment/measured_widths.csv`, then rerun `python3.11 step4_experiment.py`.
