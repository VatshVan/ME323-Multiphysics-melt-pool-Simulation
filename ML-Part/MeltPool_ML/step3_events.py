#!/usr/bin/env python3
"""Local solidification model: G and R at every point of the track.

Inputs: the run inputs [P_abs, v, r, k, flow, marangoni] plus the event's
position scaled by its run's pool: z/depth, y/half-width, and distance
from the track start (mm). Outputs: log G and log R (one multi-output
model); G/R and G*R follow from them.

Every split is grouped by run (events of one simulation are strongly
correlated, a random split would leak). The holdout runs are the same as
the run-level model's. SVR and the GP train on random subsamples of each
fold (3000 / 600 events; a GP fit costs ~n^3); the other algorithms use every event.

Usage: python step3_events.py [--retune] [--smoke]
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
from sklearn.metrics import r2_score

from mpml.data import EVENT_TARGETS as TARGETS, EventFeatures, EventTargets, load_events, load_runs, HERE
from mpml.models import ALGORITHMS, Composite
from mpml.plots import INK, MUTED, SERIES, plt
from mpml.tune import tune

OUT, MODELS = HERE/"results", HERE/"models"
TRIALS = {"Gaussian Process": 6}  # others: 15
TUNE_ROWS = {"Gaussian Process": 400, "SVM": 3000}  # others: 4000 events per fold model while tuning
MAX_ROWS = {"SVM": 3000, "Gaussian Process": 600}
SEED = 0


def _tune(args):
    import torch
    torch.set_num_threads(2)
    algo, X, Y, groups, n = args
    t = time.time()
    p, s = tune(algo, X, Y, n, seed=SEED, groups=groups, max_rows=TUNE_ROWS.get(algo, 4000), events=True)
    s["seconds"] = round(time.time() - t)
    return algo, p, s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retune", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    global OUT, TRIALS
    warnings.filterwarnings("ignore")
    runs, ev = load_runs(), load_events()
    holdout = json.loads((MODELS/"run_params.json").read_text())["holdout"]
    if a.smoke:
        OUT, TRIALS = HERE/"smoke"/"results", {a: 2 for a in ALGORITHMS}
        OUT.mkdir(parents=True, exist_ok=True)
        ev = ev.groupby("case", group_keys=False).apply(lambda d: d.sample(min(len(d), 300), random_state=0))
    test = ev["case"].isin(holdout).values
    tr, te = ev[~test].reset_index(drop=True), ev[test].reset_index(drop=True)
    fx = EventFeatures(json.loads((MODELS/"run_params.json").read_text())["feature_set"], runs, ev)
    tg = EventTargets().fit(tr)
    Xtr, Ytr, Xte, Yte = fx(tr), tg(tr), fx(te), te[TARGETS].values
    groups = tr["case"].values
    print(f"events: train {len(tr)} ({tr.case.nunique()} runs), holdout {len(te)} ({holdout})")

    pfile = (OUT.parent/"models" if a.smoke else MODELS)/"event_params.json"
    pfile.parent.mkdir(parents=True, exist_ok=True)
    if pfile.exists() and not a.retune and not a.smoke:
        saved = json.loads(pfile.read_text())
        params, scores = saved["params"], saved["scores"]
    else:
        params, scores = {}, {}
        with ProcessPoolExecutor(len(ALGORITHMS)) as ex:
            for algo, p, s in ex.map(_tune, [(al, Xtr, Ytr, groups, TRIALS.get(al, 15)) for al in ALGORITHMS]):
                params[algo], scores[algo] = p, s
                print(f"tuned {algo:17s} F={s['F']:.3f} R2tr={s['r2_train']:.3f} R2val={s['r2_val']:.3f} "
                      f"({s['seconds']} s) {p}")
        pfile.write_text(json.dumps({"params": params, "scores": scores, "tune_rows": TUNE_ROWS,
                                     "max_rows": MAX_ROWS}, indent=2))

    t = time.time()
    comp = Composite(params, seed=SEED, max_rows=MAX_ROWS).fit(Xtr, Ytr, groups)
    print(f"composite: {comp.n_models} models in {time.time()-t:.0f} s")
    alg = {a: tg.to_physical(z) for a, z in comp.predict_algos(Xte).items()}  # every algorithm
    phys = np.stack([alg[a] for a in comp.members])                           # composite members
    mu = np.exp(np.log(phys).mean(0))      # geometric mean across the members
    mu_all = np.exp(np.log(np.stack(list(alg.values()))).mean(0))
    lin = LinearRegression().fit(Xtr, Ytr)
    base = tg.to_physical(lin.predict(Xte))

    G, R = Yte[:, 0], Yte[:, 1]
    sim = {"G": G, "R": R, "G/R": G/R, "G*R": G*R}
    def derived(m):
        return {"G": m[:, 0], "R": m[:, 1], "G/R": m[:, 0]/m[:, 1], "G*R": m[:, 0]*m[:, 1]}
    rows = []
    for label, pr in [("composite", derived(mu)), ("6-algorithm composite incl. RF", derived(mu_all)),
                      ("log-linear baseline", derived(base))] + [(al, derived(v)) for al, v in alg.items()]:
        for q in sim:
            rows.append({"model": label, "quantity": q,
                         "R2_log": r2_score(np.log(sim[q]), np.log(pr[q])),
                         "median_abs_log10_err": float(np.median(np.abs(np.log10(pr[q]/sim[q])))),
                         "within_factor_1.25": float(np.mean(np.abs(np.log(pr[q]/sim[q])) <= np.log(1.25)))})
    m = pd.DataFrame(rows)
    m.to_csv(OUT/"event_model_metrics.csv", index=False)
    print(m.pivot_table(index="model", columns="quantity", values="R2_log", sort=False).round(3).to_string())
    print(m.pivot_table(index="model", columns="quantity", values="within_factor_1.25",
                        sort=False).round(3).to_string())

    # per holdout run: medians of simulated vs predicted
    te = te.assign(G_pred=mu[:, 0], R_pred=mu[:, 1])
    per_run = te.groupby("case").agg(G_sim=("G_K_mm", "median"), G_pred=("G_pred", "median"),
                                     R_sim=("R_mm_s", "median"), R_pred=("R_pred", "median"),
                                     n=("G_K_mm", "size"))
    print(per_run.round(3).to_string())
    te.to_csv(OUT/"event_predictions_holdout.csv.gz", index=False, float_format="%.6g")
    figures(te, scores)

    if not a.smoke:
        with open(MODELS/"event_composite.pkl", "wb") as f:
            pickle.dump({"model": comp, "features": fx, "targets": tg}, f)


def figures(te, scores):
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.6))
    for ax, (s, p, lab) in zip(axs[:2], [("G_K_mm", "G_pred", "G [K/mm]"), ("R_mm_s", "R_pred", "R [mm/s]")]):
        x, y = np.log10(te[s]), np.log10(te[p])
        hb = ax.hexbin(x, y, gridsize=45, bins="log", cmap="Blues", mincnt=1, lw=0)
        lo, hi = min(x.min(), y.min()), max(x.max(), y.max())
        ax.plot([lo, hi], [lo, hi], color=INK, lw=1)
        for f in (1.25,):
            ax.plot([lo, hi], [lo + np.log10(f), hi + np.log10(f)], color=MUTED, lw=0.8, ls="--")
            ax.plot([lo, hi], [lo - np.log10(f), hi - np.log10(f)], color=MUTED, lw=0.8, ls="--")
        ax.set_xlabel(f"simulation log10 {lab}")
        ax.set_ylabel(f"prediction log10 {lab}")
        ax.set_title(f"{lab.split()[0]}: holdout runs, R²(log) {r2_score(x, y):.3f}", loc="left")
        fig.colorbar(hb, ax=ax, label="events")
    # G-R map of the holdout runs
    ax = axs[2]
    ax.scatter(te["R_mm_s"], te["G_K_mm"], s=3, color=MUTED, alpha=0.35, lw=0, label="simulation")
    ax.scatter(te["R_pred"], te["G_pred"], s=3, color=SERIES[0], alpha=0.35, lw=0, label="prediction")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("R [mm/s]")
    ax.set_ylabel("G [K/mm]")
    ax.set_title("Solidification map, holdout runs", loc="left")
    ax.legend(markerscale=4, loc="lower left")
    fig.tight_layout()
    fig.savefig(OUT/"fig_events_parity.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
