# MeltPool_ML: the Wang et al. (2024) method on our melt-pool simulations

This applies the machine-learning pipeline of Wang et al., *Addit. Manuf.* 92 (2024) 104384
(replicated in `../Replicated_Paper`) to the AdditiveFOAM Ti-6Al-4V runs of this project:
feature-set study, k-fold ensembles of the paper's five algorithms plus a Gaussian process
(random forest trained but left out of the composite, see below),
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
XGBoost 0.444, random forest −0.340.

**Random forest is trained and reported but left out of the composite** (μ and σ use the other
five algorithms; 69 models). Its Eq. 1 score is below zero here and 0.08 on the event data; the
paper left out KNN for the same reason (low optimisation score, Wang et al. Sec. 3.2).

R² in log space, every run predicted out-of-sample (5-fold over runs):

| | depth | width | length | T_max | U_surf | cooling rate | G | R |
|---|---|---|---|---|---|---|---|---|
| **composite (5 algorithms, no RF)** | **0.981** | **0.974** | **0.983** | **0.944** | **0.983** | **0.869** | **0.927** | **0.866** |
| composite incl. RF (6 algorithms) | 0.972 | 0.954 | 0.967 | 0.932 | 0.975 | 0.815 | 0.897 | 0.824 |
| Gaussian process alone | 0.994 | 0.993 | 0.995 | 0.984 | 0.992 | 0.917 | 0.943 | 0.896 |
| SVR alone | 0.994 | 0.990 | 0.994 | 0.975 | 0.994 | 0.870 | 0.943 | 0.847 |
| random forest alone | 0.805 | 0.609 | 0.681 | 0.678 | 0.897 | 0.071 | 0.484 | 0.140 |
| power-law baseline | 0.983 | 0.986 | 0.988 | 0.992 | 0.999 | 0.746 | 0.836 | 0.809 |

Mean absolute percentage error of the composite (out-of-sample): depth 4.6 %, width 3.1 %,
length 2.3 %, T_max 2.7 %, G 2.7 %, cooling rate 12.7 %, R 13.0 %. On the 5 holdout runs:
depth 2.9 %, width 2.9 %, T_max 1.6 %, G 2.0 %. Ma derived from the predictions: R² 0.991,
3.8 % error; Pe (log): R² 0.995.

Points to state in the report:
- Dropping random forest raised every out-of-sample R² (e.g. width 0.954 → 0.974, R 0.824 →
  0.866) and narrowed the ±3σ bands.
- The composite beats the power-law baseline (a log-space regression with flow/Marangoni terms)
  on cooling rate, G and R, matches it on depth, and is still slightly behind it on width and
  T_max. The GP and SVR alone remain better than the composite: with 46 deterministic runs,
  smooth models do best.
- The hyperparameters were tuned on the 41 training runs, which also appear in the outer 5-fold
  test folds, so the out-of-sample scores are slightly optimistic.

### Local G/R model (events)

70,032 training events (41 runs), 9,227 holdout events (the same 5 holdout runs). Folds grouped
by run; SVR and the GP train on 3000 / 600 events per fold model (a GP fit costs ~n³); the
other algorithms use every event. Eq. 1 scores: neural net 0.688, SVM 0.541, XGBoost 0.504,
Bayesian ridge 0.319, random forest 0.083, GP 0.023 (GP: train R² 1.00 vs validation 0.76, so
Eq. 1 penalises its overfitting on the small subsample). The composite (no RF) has 34 models.

Holdout runs, R² in log space and share of events predicted within a factor 1.25:

| | G | R | G/R | G·R |
|---|---|---|---|---|
| **composite (no RF), R²(log)** | **0.756** | **0.733** | **0.698** | **0.752** |
| composite incl. RF | 0.731 | 0.704 | 0.668 | 0.724 |
| neural net alone | 0.838 | 0.762 | 0.709 | 0.796 |
| GP alone (600 events) | 0.830 | 0.752 | 0.707 | 0.782 |
| log-linear baseline | 0.109 | 0.555 | 0.532 | 0.501 |
| composite (no RF), within ×1.25 | 83 % | 33 % | 36 % | 32 % |

G is predicted well; local R much less so. Along the fusion boundary R runs from near zero at the
pool bottom to about the scan speed at the tail, and the model reproduces each run's trend but
smooths the event-to-event scatter (the predicted G–R map in `fig_events_parity.png` is narrower
than the simulated one). Per-run medians on the holdout runs: G within 1–7 %, R within
12–49 % (worst for U2000_v3_MaB, the slowest, widest pool). The neural net and GP alone still
beat the composite; Bayesian ridge (linear) is the weakest remaining member here.

### Experiment link (Fig. 5 analogue)

Planned experiment: flat-top 3 mm beam (r = 1.5 mm, k = 20), 1000 and 1400 W, 6 and 9 mm/s
(12 mm/s if time allows), Marangoni and buoyancy always present in reality. No optical
microscope is available, so only the **track width** is measured.

Predicted widths at η = 0.35 (mm, ±3σ), Marangoni + buoyancy:

| | 6 mm/s | 9 mm/s | 12 mm/s |
|---|---|---|---|
| 1000 W | 2.85 ± 0.15 (sim 2.83) | 2.60 ± 0.12 (sim 2.61) | 2.46 ± 0.16 |
| 1400 W | 3.60 ± 0.14 | 3.23 ± 0.23 | 3.04 ± 0.13 |

Full table for all modes and outputs: `results/experiment_predictions.csv`.

**Marangoni test without knowing the absorptivity.** Width scales as W ∝ (ηP)^a, so in
W(1400 W)/W(1000 W) = 1.4^a the absorptivity cancels; a = ln(W₁₄₀₀/W₁₀₀₀)/ln 1.4 is computed
from the two measured widths at each speed. Model values (mean of XGBoost, SVR, neural net, GP;
Bayesian ridge is linear in the log inputs with no flow × power terms, so it gives the same
exponent, 0.615, for every mode; see `experiment_width_ratio.csv`):

| mode | a at 6 / 9 / 12 mm/s (±3σ) |
|---|---|
| Marangoni + buoyancy | 0.71 / 0.64 / 0.63 (±0.20–0.24) |
| buoyancy only | 0.51 / 0.49 / 0.49 (±0.11–0.16) |
| conduction only | 0.47 / 0.45 / 0.45 (±0.04–0.12) |

The Marangoni case is separate at 1σ but the 3σ bands touch: a 2–3σ discrimination. The
simulations' own power-law fits (`results/ta_fits.csv`) give 0.70 / 0.49 / 0.44.

**Absorptivity by Bayesian optimisation** (Optuna GPSampler, 40 trials, χ² of the widths with
measurement and model σ in quadrature). Self-test on simulated widths with known η = 0.35:
η = 0.348 (1σ range 0.340–0.355). With real data, fill `experiment/measured_widths.csv` and
rerun step 4.

**Eq. 2 inverse design: speed for a target width at 1400 W.** The paper's
Fp = max(floor, |μ − W*|)/σ (floor 0.05 mm = photo resolution) with the 0.2 distance filter,
minimised over speed by BO and by random search (the paper's method):

| target W* [mm] | Eq. 2 + BO | Eq. 2 + random | direct (μ = W*) |
|---|---|---|---|
| 3.18 | 9.0 mm/s | 9.1 mm/s | 9.7 mm/s |
| 3.32 | 8.0 mm/s | 8.8 mm/s | 8.3 mm/s |
| 3.46 | 7.8 mm/s | 7.6 mm/s | 7.25 mm/s |

Because σ is in the denominator, Eq. 2 favours speeds where the ensemble disagrees more and
accepts missing W* by up to the floor; the direct column is where the model actually predicts
W*. In the lab, the speed for W* comes from interpolating the measured widths between the
6 / 9 / 12 mm/s tracks. On this one-dimensional search BO is no faster than random search.

### Surrogate SHAP (Figs. 6–7)

Grid: P_abs 300–800 W × v 3–12 mm/s × r 0.5–1.5 mm (21 values each), Marangoni on/off,
Gaussian beam: 18,522 points; one default XGBoost surrogate per output (R² > 0.9998).
Share of mean |SHAP|:

| output | P_abs | v | r | Marangoni |
|---|---|---|---|---|
| depth | 27 % | 16 % | 4 % | 52 % |
| width | 44 % | 23 % | 3 % | 31 % |
| T_max | 26 % | 4 % | 21 % | 49 % |
| cooling rate | 22 % | 50 % | 8 % | 20 % |
| G | 58 % | 28 % | 10 % | 4 % |
| R | 13 % | 47 % | 6 % | 34 % |

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
