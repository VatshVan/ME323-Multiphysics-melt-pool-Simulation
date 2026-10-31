#!/usr/bin/env python3
"""Link to the planned experiment: flat-top 3 mm beam (r = 1.5 mm, k = 20)
on Ti-6Al-4V at 1000 and 1400 W, 6 and 9 mm/s (12 mm/s if time allows).
The only measurement is the top-surface track width (phone photo with a
steel ruler, ImageJ), so everything here is built on width.

1. Forward prediction before the experiment (Fig. 5 analogue): width and
   the other outputs for every case and flow mode, mu +- 3 sigma.
2. Marangoni test that does not need the absorptivity: the width ratio
   W(1400 W)/W(1000 W) at equal speed; the absorptivity cancels. Its
   exponent a = ln(ratio)/ln(1.4) is computed the same way from the
   measured widths.
3. Bayesian optimisation (Optuna GPSampler) for
   a) the effective absorptivity eta that reproduces the measured widths;
   b) the paper's inverse design (Eq. 2): the speed that gives a target
      width at 1400 W, checked in the lab by interpolating the measured
      widths between the 6 / 9 / 12 mm/s tracks.
   With no measurements yet (experiment/measured_widths.csv empty), 3a is
   run as a self-test on simulated widths whose eta is known (0.35).

Usage: python step4_experiment.py
"""

import pickle
import warnings

import numpy as np
import optuna
import pandas as pd

from mpml.data import TARGET_NAMES, TARGETS, derived_numbers, load_runs, HERE
from mpml.plots import INK, MODE_STYLE, MUTED, SERIES, plt

OUT, MODELS, EXP = HERE/"results", HERE/"models", HERE/"experiment"
ETA_NOMINAL = 0.35
POWERS, SPEEDS = (1000.0, 1400.0), (6.0, 9.0, 12.0)
BEAM_R, BEAM_K = 1.5, 20.0
MODES = {"MaB": (1, 1), "B": (1, 0), "none": (0, 0)}  # flow, marangoni
WIDTH_FLOOR_MM = 0.05     # photo reading resolution; plays the 0.1 wt% floor of Eq. 2
DISTANCE_MIN = 0.2        # Eq. 2 novelty filter, normalised input space
BO_TRIALS = 40
optuna.logging.set_verbosity(optuna.logging.WARNING)


class Model:
    def __init__(self):
        with open(MODELS/"run_composite.pkl", "rb") as f:
            d = pickle.load(f)
        self.m, self.fx, self.tg = d["model"], d["features"], d["targets"]
        self.w = TARGET_NAMES.index("width")

    def frame(self, P_abs, v, mode, r=BEAM_R, k=BEAM_K):
        P_abs, v = np.broadcast_arrays(np.atleast_1d(np.asarray(P_abs, float)),
                                       np.atleast_1d(np.asarray(v, float)))
        fl, ma = MODES[mode]
        return pd.DataFrame({"absorbed_power_W": P_abs, "scan_speed_mm_s": v, "beam_radius_mm": r,
                             "beam_k": k, "flow": fl, "marangoni": ma})

    def algos(self, df):
        """(A, n, T) physical predictions of each algorithm ensemble."""
        return self.tg.to_physical(self.m.predict(self.fx(df))[2])

    def width(self, P_abs, v, mode):
        A = self.algos(self.frame(P_abs, v, mode))[..., self.w]
        return A.mean(0), A.std(0), A


def forward(model, runs):
    rows = []
    for mode in MODES:
        for P in POWERS:
            df = model.frame(ETA_NOMINAL*P, SPEEDS, mode)
            A = model.algos(df)
            mu, sd = A.mean(0), A.std(0)
            Ma, Pe = derived_numbers(mu[:, TARGET_NAMES.index("T_max")], mu[:, model.w],
                                     mu[:, TARGET_NAMES.index("U_surf")], MODES[mode][1])
            for i, v in enumerate(SPEEDS):
                row = {"mode": mode, "laser_power_W": P, "absorbed_power_W": ETA_NOMINAL*P, "speed_mm_s": v}
                for j, (_, n, u) in enumerate(TARGETS):
                    row[f"{n}_pred"], row[f"{n}_3sigma"] = mu[i, j], 3*sd[i, j]
                row["Ma_pred"], row["Pe_pred"] = Ma[i], Pe[i]
                sim = runs[(runs.beam_k == BEAM_K) & np.isclose(runs.absorbed_power_W, ETA_NOMINAL*P)
                           & (runs.scan_speed_mm_s == v) & (runs["mode"] == mode)]
                row["width_sim_same_inputs"] = sim["qs_width_mm"].iloc[0] if len(sim) else np.nan
                rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(OUT/"experiment_predictions.csv", index=False)
    cols = ["mode", "laser_power_W", "speed_mm_s", "width_pred", "width_3sigma", "width_sim_same_inputs",
            "depth_pred", "T_max_pred", "Ma_pred"]
    print("Forward predictions for the experiment (eta = 0.35):\n" + df[cols].round(3).to_string(index=False))
    return df


def width_ratio(model):
    rows = []
    for mode in MODES:
        _, _, A1 = model.width(ETA_NOMINAL*POWERS[0], SPEEDS, mode)
        _, _, A2 = model.width(ETA_NOMINAL*POWERS[1], SPEEDS, mode)
        ratio = A2/A1                          # per algorithm
        expo = np.log(ratio)/np.log(POWERS[1]/POWERS[0])
        # Bayesian ridge (linear in log inputs, no flow x power terms)
        # cannot represent a mode-dependent exponent; the "able" columns
        # average the other four composite members
        able = [i for i, al in enumerate(model.m.members) if al != "Bayesian Ridge"]
        for i, v in enumerate(SPEEDS):
            row = {"mode": mode, "speed_mm_s": v, "ratio": ratio[:, i].mean(),
                   "ratio_3sigma": 3*ratio[:, i].std(), "exponent_a": expo[:, i].mean(),
                   "exponent_3sigma": 3*expo[:, i].std(),
                   "exponent_a_able": expo[able, i].mean(), "exponent_3sigma_able": 3*expo[able, i].std()}
            row.update({f"a_{al}": expo[j, i] for j, al in enumerate(model.m.members)})
            rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(OUT/"experiment_width_ratio.csv", index=False)
    print("\nWidth ratio W(1400)/W(1000) and exponent a, per flow mode:\n" + df.round(3).to_string(index=False))
    return df


def fit_eta(model, meas, mode="MaB", trials=BO_TRIALS, seed=0):
    """BO for the effective absorptivity: minimise chi2 of the width over
    the measured tracks, sd = measurement and model (sigma) in quadrature.
    Returns the best eta and a profile of chi2 over eta for the figure."""
    P, v = meas["laser_power_W"].values, meas["speed_mm_s"].values
    W, s = meas["width_mm"].values, meas["width_sd_mm"].values

    def chi2(eta):
        mu, sd, _ = model.width(eta*P, v, mode)
        return float(np.sum((mu - W)**2/(s**2 + sd**2)))

    study = optuna.create_study(sampler=optuna.samplers.GPSampler(seed=seed))
    study.optimize(lambda t: chi2(t.suggest_float("eta", 0.25, 0.57)), n_trials=trials)
    grid = np.linspace(0.25, 0.57, 65)
    prof = np.array([chi2(e) for e in grid])
    # 1-sigma interval: chi2 within +1 of the minimum
    inside = grid[prof <= prof.min() + 1]
    return study, grid, prof, (inside.min(), inside.max())


def eq2_speed(model, runs_norm, target_w, P=1400.0, mode="MaB", trials=BO_TRIALS, seed=0, sampler="gp"):
    """Wang et al. Eq. 2 with the novelty filter, minimised over speed by BO
    (or random search, the paper's method, for comparison)."""
    def fp(v):
        df = model.frame(ETA_NOMINAL*P, v, mode)
        A = model.algos(df)[..., model.w][:, 0]
        mu, sd = A.mean(), A.std()
        d = np.min(np.linalg.norm(runs_norm - model.fx(df)[0], axis=1))
        val = max(WIDTH_FLOOR_MM, abs(mu - target_w))/max(sd, 1e-6)
        return val if d >= DISTANCE_MIN else val + 1e3, mu, sd, d

    smp = optuna.samplers.GPSampler(seed=seed) if sampler == "gp" else optuna.samplers.RandomSampler(seed=seed)
    study = optuna.create_study(sampler=smp)

    def obj(t):
        val, mu, sd, d = fp(t.suggest_float("v", 6.0, 12.0))
        t.set_user_attr("mu", mu)
        t.set_user_attr("sd", sd)
        t.set_user_attr("distance", d)
        return val
    study.optimize(obj, n_trials=trials)
    return study


def main():
    warnings.filterwarnings("ignore")
    model, runs = Model(), load_runs()
    fwd = forward(model, runs)
    ratio = width_ratio(model)

    # 3a. absorptivity: measured widths if present, else self-test
    mfile = EXP/"measured_widths.csv"
    meas = pd.read_csv(mfile).dropna(subset=["width_mm"]) if mfile.exists() else pd.DataFrame()
    if len(meas):
        label = "measured widths"
        meas["width_sd_mm"] = meas["width_sd_mm"].fillna(WIDTH_FLOOR_MM)
    else:
        label = "self-test: simulated MaB widths (true eta = 0.35)"
        sim = runs[(runs.beam_k == BEAM_K) & (runs["mode"] == "MaB") & (runs.absorbed_power_W == 350)]
        meas = pd.DataFrame({"laser_power_W": 1000.0, "speed_mm_s": sim.scan_speed_mm_s.values,
                             "width_mm": sim.qs_width_mm.values, "width_sd_mm": WIDTH_FLOOR_MM})
    study, grid, prof, ci = fit_eta(model, meas)
    eta = study.best_params["eta"]
    print(f"\nAbsorptivity by BO ({label}): eta = {eta:.3f}, chi2 = {study.best_value:.2f}, "
          f"1-sigma range {ci[0]:.3f}-{ci[1]:.3f}  ({len(meas)} tracks, {BO_TRIALS} BO trials)")
    pd.DataFrame({"eta": grid, "chi2": prof}).to_csv(OUT/"experiment_eta_profile.csv", index=False)

    # 3b. Eq. 2 target-width speed at 1400 W, BO vs random search
    runs_norm = model.fx(runs)
    w6, w12 = (fwd[(fwd["mode"] == "MaB") & (fwd.laser_power_W == 1400) & (fwd.speed_mm_s == s)]["width_pred"].iloc[0]
               for s in (6.0, 12.0))
    targets = np.round(np.linspace(w12, w6, 5)[1:-1], 2)
    rows, hist = [], {}
    for W in targets:
        for smp in ("gp", "random"):
            st = eq2_speed(model, runs_norm, W, sampler=smp)
            b = st.best_trial
            rows.append({"target_width_mm": W, "sampler": "BO (GP)" if smp == "gp" else "random (paper)",
                         "speed_mm_s": b.params["v"], "width_pred": b.user_attrs["mu"],
                         "width_3sigma": 3*b.user_attrs["sd"], "Fp": b.value,
                         "distance_to_data": b.user_attrs["distance"],
                         "trials_to_best": b.number + 1})
            hist[(W, smp)] = np.minimum.accumulate([t.value for t in st.trials])
    # direct answer for comparison: the speed where the mean prediction equals W*
    vv = np.linspace(6.0, 12.0, 601)
    mu_v, sd_v, _ = model.width(ETA_NOMINAL*1400.0, vv, "MaB")
    for W in targets:
        i = int(np.argmin(np.abs(mu_v - W)))
        rows.append({"target_width_mm": W, "sampler": "direct |mu - W*| min", "speed_mm_s": vv[i],
                     "width_pred": mu_v[i], "width_3sigma": 3*sd_v[i], "Fp": np.nan,
                     "distance_to_data": np.nan, "trials_to_best": len(vv)})
    eq2 = pd.DataFrame(rows).sort_values(["target_width_mm", "sampler"])
    eq2.to_csv(OUT/"experiment_eq2_speeds.csv", index=False)
    print("\nEq. 2 inverse design at 1400 W (MaB), speed for a target width:\n" + eq2.round(3).to_string(index=False))

    figures(model, fwd, ratio, runs, grid, prof, eta, ci, meas, label, eq2, hist, targets)
    template(mfile)


def template(mfile):
    if mfile.exists():
        return
    EXP.mkdir(exist_ok=True)
    pd.DataFrame([{"laser_power_W": P, "speed_mm_s": v, "width_mm": np.nan, "width_sd_mm": np.nan,
                   "n_readings": np.nan, "photo": ""} for P in POWERS for v in SPEEDS]).to_csv(mfile, index=False)


def figures(model, fwd, ratio, runs, grid, prof, eta, ci, meas, label, eq2, hist, targets):
    # Fig. 5 analogue: width vs speed per power, per mode, +-3 sigma
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    for ax, P in zip(axs, POWERS):
        # 1000 W: flat-top runs exist down to 3 mm/s; 1400 W: only 6-12 mm/s runs nearby
        vv = np.linspace(2.8 if P == 1000 else 5.5, 12.5, 80)
        for mode, (c, mk, lab) in MODE_STYLE.items():
            mu, sd, _ = model.width(ETA_NOMINAL*P, vv, mode)
            ax.fill_between(vv, mu - 3*sd, mu + 3*sd, color=c, alpha=0.15, lw=0)
            ax.plot(vv, mu, color=c, label=f"{lab} (model ±3σ)")
            f = fwd[(fwd["mode"] == mode) & (fwd.laser_power_W == P)]
            ax.plot(f.speed_mm_s, f.width_pred, mk, color=c, mec="white", mew=0.8)
            s = runs[(runs.beam_k == BEAM_K) & np.isclose(runs.absorbed_power_W, ETA_NOMINAL*P) & (runs["mode"] == mode)]
            ax.plot(s.scan_speed_mm_s, s.qs_width_mm, mk, ms=9, mfc="none", mec=INK, mew=1)
        ax.plot([], [], "o", ms=9, mfc="none", mec=INK, label="simulated flat-top run")
        ax.set_title(f"{P:.0f} W, flat-top r = 1.5 mm, η = 0.35", loc="left")
        ax.set_xlabel("scan speed [mm/s]")
        ax.set_xticks((3.0,) + SPEEDS)
    axs[0].set_ylabel("track width [mm]")
    axs[1].legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT/"fig5_experiment_width.png")
    plt.close(fig)

    # width ratio / exponent per mode
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    off = {"MaB": -0.25, "B": 0.0, "none": 0.25}
    for mode, (c, mk, lab) in MODE_STYLE.items():
        r = ratio[ratio["mode"] == mode]
        ax.errorbar(r.speed_mm_s + off[mode], r.exponent_a_able, yerr=r.exponent_3sigma_able, fmt=mk,
                    color=c, capsize=3, label=lab, mec="white")
    ax.set_xticks(SPEEDS)
    ax.set_xlabel("scan speed [mm/s]")
    ax.set_ylabel("a = ln(W₁₄₀₀/W₁₀₀₀) / ln 1.4")
    ax.set_title("Width power exponent (η cancels), ±3σ over XGB, SVR, NN, GP", loc="left")
    ax.legend(fontsize=8)
    fig.savefig(OUT/"fig_experiment_width_exponent.png")
    plt.close(fig)

    # eta profile + Eq. 2 convergence
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.4))
    ax = axs[0]
    ax.plot(grid, prof, color=SERIES[0])
    ax.axvline(eta, color=INK, lw=1)
    ax.axvspan(*ci, color=SERIES[0], alpha=0.12, lw=0)
    ax.text(eta, prof.max()*0.9, f"  η = {eta:.3f}\n  ({ci[0]:.3f}–{ci[1]:.3f})", va="top")
    ax.set_yscale("log")
    ax.set_xlabel("effective absorptivity η")
    ax.set_ylabel("χ² of width")
    ax.set_title(f"Absorptivity from width, BO ({label.split(':')[0]})", loc="left")
    ax = axs[1]
    for i, W in enumerate(targets):
        c = SERIES[i]
        ax.plot(np.arange(1, BO_TRIALS + 1), hist[(W, "gp")], color=c, label=f"W* = {W} mm, BO")
        ax.plot(np.arange(1, BO_TRIALS + 1), hist[(W, "random")], color=c, ls="--", lw=1.2,
                label=f"W* = {W} mm, random")
    ax.set_yscale("log")
    ax.set_xlabel("ensemble evaluations")
    ax.set_ylabel("best Fp so far (Eq. 2)")
    ax.set_title("Target-width speed at 1400 W: BO vs random search", loc="left")
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(OUT/"fig_experiment_inverse.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
