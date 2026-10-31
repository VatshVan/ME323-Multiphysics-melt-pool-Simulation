#!/usr/bin/env python3
"""Run-level multi-output model (Wang et al. 2024 Secs. 2.3, 3.2; Fig. 4).

1. Holdout split 90/10 at random over runs (paper Sec. 2.3).
2. Optuna tuning (Eq. 1) of each algorithm on the training runs.
3. Composite of the six k-fold ensembles; parity on the holdout runs.
4. Every run predicted out-of-sample once (5-fold over runs, tuned
   hyperparameters fixed) for an honest parity over all 46 runs.
5. Baseline: one linear regression in log space with flow / Marangoni
   interaction terms (a power law per flow mode).
6. Ma and Pe derived from the predicted T_max, width and surface speed.
7. Final composite refitted on all runs, saved for the later steps.

Usage: python step2_ensemble.py [--retune] [--smoke]
"""

import argparse
import json
import pickle
import time
import warnings
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import KFold

from mpml.data import (TARGET_COLS, TARGET_NAMES, TARGETS, Features, Targets, derived_numbers,
                       load_runs, HERE)
from mpml.models import ALGORITHMS, Composite
from mpml.plots import INK, MODE_STYLE, MUTED, SERIES, plt
from mpml.tune import tune

FEATURE_SET = "[P_abs, v, r]"
OUT, MODELS = HERE/"results", HERE/"models"
TRIALS = {"XGBoost": 30, "SVM": 60, "Neural Network": 30, "Random Forest": 40,
          "Bayesian Ridge": 60, "Gaussian Process": 12}
HOLDOUT_FRACTION, SEED = 0.10, 0


def _tune(args):
    import torch
    torch.set_num_threads(1)
    algo, X, Y, n = args
    t = time.time()
    p, score = tune(algo, X, Y, n, seed=SEED)
    score["seconds"] = round(time.time() - t)
    return algo, p, score


def baseline_design(runs):
    lp, lv = np.log(runs["absorbed_power_W"]), np.log(runs["scan_speed_mm_s"])
    lr, lk = np.log(runs["beam_radius_mm"]), np.log(runs["beam_k"])
    fl, ma = runs["flow"].values, runs["marangoni"].values
    return np.column_stack([lp, lv, lr, lk, fl, ma, fl*lp, fl*lv, ma*lp, ma*lv, ma*lr])


def to_phys(tg, P):
    """(A, n, T) standardised algorithm predictions -> physical mean, sd."""
    phys = tg.to_physical(P)
    return phys.mean(0), phys.std(0)


def metrics(y, mu, label):
    rows = []
    for j, (col, name, unit) in enumerate(TARGETS):
        rows.append({"set": label, "target": name, "unit": unit,
                     "R2": r2_score(y[:, j], mu[:, j]),
                     "R2_log": r2_score(np.log1p(y[:, j]*1e3) if name == "U_surf" else np.log(y[:, j]),
                                        np.log1p(mu[:, j]*1e3) if name == "U_surf" else np.log(mu[:, j])),
                     "MAE": mean_absolute_error(y[:, j], mu[:, j]),
                     "MAPE_%": 100*np.mean(np.abs(mu[:, j] - y[:, j])/np.where(y[:, j] > 0, y[:, j], np.nan))
                     if name != "U_surf" else np.nan,
                     "within_10%": np.mean(np.abs(mu[:, j] - y[:, j]) <= 0.1*np.abs(y[:, j]))})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retune", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="2 trials per algorithm, nothing saved over")
    a = ap.parse_args()
    global OUT, MODELS
    if a.smoke:
        OUT, MODELS = HERE/"smoke"/"results", HERE/"smoke"/"models"
        OUT.mkdir(parents=True, exist_ok=True)
        for k in TRIALS:
            TRIALS[k] = 2
    OUT.mkdir(exist_ok=True)
    MODELS.mkdir(exist_ok=True)
    warnings.filterwarnings("ignore")

    runs = load_runs()
    feats = Features(FEATURE_SET, runs)
    rng = np.random.RandomState(SEED)
    n_test = int(round(HOLDOUT_FRACTION*len(runs)))
    test_idx = np.sort(rng.choice(len(runs), n_test, replace=False))
    train_idx = np.setdiff1d(np.arange(len(runs)), test_idx)
    print("holdout runs:", ", ".join(runs["case"].iloc[test_idx]))
    tr, te = runs.iloc[train_idx], runs.iloc[test_idx]
    tg = Targets().fit(tr)
    Xtr, Ytr, Xte = feats(tr), tg(tr), feats(te)

    # 2. tuning
    pfile = MODELS/"run_params.json"
    if pfile.exists() and not a.retune:
        saved = json.loads(pfile.read_text())
        params, scores = saved["params"], saved["scores"]
    else:
        params, scores = {}, {}
        with ProcessPoolExecutor(len(ALGORITHMS)) as ex:
            for algo, p, s in ex.map(_tune, [(al, Xtr, Ytr, TRIALS[al]) for al in ALGORITHMS]):
                params[algo], scores[algo] = p, s
                print(f"tuned {algo:17s} F={s['F']:.3f} R2tr={s['r2_train']:.3f} "
                      f"R2val={s['r2_val']:.3f} ({s['seconds']} s) {p}")
        pfile.write_text(json.dumps({"feature_set": FEATURE_SET, "holdout": list(te["case"]),
                                     "params": params, "scores": scores}, indent=2))

    # 3. composite on the training runs, holdout parity
    comp = Composite(params, seed=SEED).fit(Xtr, Ytr)
    print(f"composite: {comp.n_models} models")
    mu_tr, _ = to_phys(tg, comp.predict(Xtr)[2])
    mu_te, sd_te = to_phys(tg, comp.predict(Xte)[2])
    Y_tr, Y_te = tr[TARGET_COLS].values, te[TARGET_COLS].values

    # 4. out-of-sample prediction of every run (5-fold over runs)
    oos_mu = np.zeros((len(runs), len(TARGETS)))
    oos_sd = np.zeros_like(oos_mu)
    oos_alg = np.zeros((len(ALGORITHMS), len(runs), len(TARGETS)))
    base_oos = np.zeros_like(oos_mu)
    Xb = baseline_design(runs)
    for k, (a_idx, b_idx) in enumerate(KFold(5, shuffle=True, random_state=SEED).split(runs)):
        t_k = Targets().fit(runs.iloc[a_idx])
        c = Composite(params, seed=SEED).fit(feats(runs.iloc[a_idx]), t_k(runs.iloc[a_idx]))
        Xk = feats(runs.iloc[b_idx])
        oos_mu[b_idx], oos_sd[b_idx] = to_phys(t_k, c.predict(Xk)[2])
        oos_alg[:, b_idx] = t_k.to_physical(np.stack(list(c.predict_algos(Xk).values())))
        lin = LinearRegression().fit(Xb[a_idx], t_k(runs.iloc[a_idx]))
        base_oos[b_idx] = t_k.to_physical(lin.predict(Xb[b_idx]))
        print(f"  outer fold {k+1}/5 done")
    lin = LinearRegression().fit(Xb[train_idx], tg(tr))
    base_te = tg.to_physical(lin.predict(Xb[test_idx]))

    Y_all = runs[TARGET_COLS].values
    m = pd.DataFrame(metrics(Y_tr, mu_tr, "composite train") + metrics(Y_te, mu_te, "composite holdout")
                     + metrics(Y_te, base_te, "power-law baseline holdout")
                     + metrics(Y_all, oos_mu, "composite 5-fold OOS (all runs)")
                     + metrics(Y_all, base_oos, "power-law baseline 5-fold OOS")
                     + metrics(Y_all, oos_alg.mean(0), "6-algorithm composite incl. RF 5-fold OOS"))
    for j, al in enumerate(ALGORITHMS):
        m = pd.concat([m, pd.DataFrame(metrics(Y_all, oos_alg[j], f"{al} 5-fold OOS"))])
    m.to_csv(OUT/"run_model_metrics.csv", index=False)
    piv = m.pivot_table(index="set", columns="target", values="R2_log", sort=False)[TARGET_NAMES]
    print("\nR2 (log space) per target:\n" + piv.round(3).to_string())
    print("\nMAPE % per target:\n" + m.pivot_table(index="set", columns="target", values="MAPE_%",
                                                    sort=False)[TARGET_NAMES[:4] + TARGET_NAMES[5:]].round(1).to_string())

    # 6. derived Ma, Pe
    j = {n: i for i, n in enumerate(TARGET_NAMES)}
    Ma_p, Pe_p = derived_numbers(oos_mu[:, j["T_max"]], oos_mu[:, j["width"]], oos_mu[:, j["U_surf"]],
                                 runs["marangoni"])
    Ma_s, Pe_s = derived_numbers(runs["qs_T_max_K"], runs["qs_width_mm"], runs["qs_U_surface_mean_m_s"],
                                 runs["marangoni"])
    on = runs["marangoni"].values == 1
    print(f"\nMa from simulated T_max, width vs snapshot Ma (Marangoni runs): median ratio "
          f"{np.median(Ma_s[on]/runs['qs_Ma'][on]):.3f}")
    print(f"Ma predicted (OOS) vs simulated: R2 {r2_score(Ma_s[on], Ma_p[on]):.3f}, "
          f"MAPE {100*np.mean(np.abs(Ma_p[on]/Ma_s[on]-1)):.1f} %")
    print(f"Pe predicted (OOS) vs simulated (flow runs): R2 "
          f"{r2_score(np.log1p(Pe_s[runs.flow == 1]), np.log1p(Pe_p[runs.flow == 1])):.3f} (log1p)")

    oos = runs[["case", "set", "mode"]].copy()
    for i, n in enumerate(TARGET_NAMES):
        oos[f"{n}_sim"], oos[f"{n}_pred"], oos[f"{n}_sd"] = Y_all[:, i], oos_mu[:, i], oos_sd[:, i]
    oos["Ma_sim"], oos["Ma_pred"], oos["Pe_sim"], oos["Pe_pred"] = Ma_s, Ma_p, Pe_s, Pe_p
    oos["holdout"] = oos["case"].isin(te["case"]).astype(int)
    oos.to_csv(OUT/"run_predictions_oos.csv", index=False)
    np.savez(OUT/"run_oos_algorithms.npz", algorithms=np.array(ALGORITHMS), cases=runs["case"].values,
             targets=np.array(TARGET_NAMES), pred=oos_alg)  # (algorithm, run, target), physical units

    figures(scores, runs, oos, Y_tr, mu_tr, Y_te, mu_te, sd_te, te)

    # 7. final model on all runs
    tg_all = Targets().fit(runs)
    final = Composite(params, seed=SEED).fit(feats(runs), tg_all(runs))
    with open(MODELS/"run_composite.pkl", "wb") as f:
        pickle.dump({"model": final, "features": feats, "targets": tg_all,
                     "feature_set": FEATURE_SET}, f)
    print(f"final composite ({final.n_models} models) saved -> {MODELS/'run_composite.pkl'}")


def figures(scores, runs, oos, Y_tr, mu_tr, Y_te, mu_te, sd_te, te):
    # Fig. 4b: optimisation scores
    fig, ax = plt.subplots(figsize=(5.2, 2.6))
    algos = sorted(scores, key=lambda k: scores[k]["F"])
    F = [scores[k]["F"] for k in algos]
    ax.barh(algos, F, height=0.5, color=[SERIES[0] if f == max(F) else MUTED for f in F])
    for i, f in enumerate(F):
        ax.text(f + 0.005, i, f"{f:.3f}", va="center")
    ax.set_xlabel("optimisation score F = R²val − 3|R²train − R²val|")
    ax.set_xlim(min(0, min(F)), 1.0)
    ax.set_title("Eq. 1 scores after Optuna tuning (training runs)", loc="left")
    ax.grid(axis="y", visible=False)
    fig.savefig(OUT/"fig4b_optimisation_scores.png")
    plt.close(fig)

    # Fig. 4c: parity, all runs out-of-sample, by flow mode; holdout ringed
    fig, axs = plt.subplots(2, 4, figsize=(11, 5.6))
    for ax, (col, name, unit) in zip(axs.flat, TARGETS):
        s, p = oos[f"{name}_sim"], oos[f"{name}_pred"]
        for mode, (c, mk, lab) in MODE_STYLE.items():
            sel = oos["mode"] == mode
            ax.errorbar(s[sel], p[sel], yerr=3*oos[f"{name}_sd"][sel], fmt=mk, color=c, ms=5,
                        elinewidth=0.8, capsize=0, label=lab, mec="white", mew=0.6)
        h = oos["holdout"] == 1
        ax.scatter(s[h], p[h], s=110, facecolors="none", edgecolors=INK, lw=1, label="10 % holdout run")
        lo, hi = min(s.min(), p.min()), max(s.max(), p.max())
        pad = 0.05*(hi - lo)
        xx = np.linspace(lo - pad, hi + pad, 2)
        ax.plot(xx, xx, color=INK, lw=1)
        ax.fill_between(xx, 0.9*xx, 1.1*xx, color=MUTED, alpha=0.15, lw=0, label="±10 %")
        r2 = r2_score(s, p)
        ax.set_title(f"{name} [{unit}]   R² {r2:.3f}", loc="left")
        if name in ("U_surf",):
            ax.set_xscale("symlog", linthresh=0.01)
            ax.set_yscale("symlog", linthresh=0.01)
    axs[1, 0].set_xlabel("simulation")
    axs[1, 0].set_ylabel("composite prediction (±3σ)")
    handles, labels = axs[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.04))
    fig.suptitle("Every run predicted out-of-sample (5-fold over runs)", x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT/"fig4c_parity.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
