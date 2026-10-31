#!/usr/bin/env python3
"""Learning curve: out-of-sample accuracy against the number of simulated
runs used for training. For each size n, n runs are drawn at random (5
repeats), the composite members are trained with the tuned hyperparameters
(k capped at n/2), and every run not drawn is predicted.

Writes results/learning_curve.csv and results/fig_learning_curve.png.
"""

import json
import warnings
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score

from mpml.data import TARGET_NAMES, Features, Targets, load_runs, HERE
from mpml.models import MEMBERS, KFoldEnsemble
from mpml.plots import INK, SERIES, plt

OUT, MODELS = HERE/"results", HERE/"models"
SIZES, REPEATS = (10, 15, 20, 25, 30, 35, 41), 5


def job(args):
    import torch
    torch.set_num_threads(1)
    warnings.filterwarnings("ignore")
    n, rep, params, fs = args
    runs = load_runs()
    rng = np.random.RandomState(100 + rep)
    tr = np.sort(rng.choice(len(runs), n, replace=False))
    te = np.setdiff1d(np.arange(len(runs)), tr)
    feats = Features(fs, runs)
    tg = Targets().fit(runs.iloc[tr])
    X, Y = feats(runs.iloc[tr]), tg(runs.iloc[tr])
    Yte = runs.iloc[te][[c for c in tg.cols]].values
    preds, rows = {}, []
    for a in MEMBERS:
        p = dict(params[a])
        p["k"] = int(min(p["k"], max(2, n//2)))
        e = KFoldEnsemble(a, p, seed=rep).fit(X, Y)
        preds[a] = tg.to_physical(e.predict(feats(runs.iloc[te])))
    preds["composite"] = np.mean([preds[a] for a in MEMBERS], axis=0)
    for a, P in preds.items():
        r2 = [r2_score(np.log1p(Yte[:, j]*1e3) if t == "U_surf" else np.log(Yte[:, j]),
                       np.log1p(np.clip(P[:, j], 0, None)*1e3) if t == "U_surf" else np.log(P[:, j]))
              for j, t in enumerate(TARGET_NAMES)]
        rows.append({"n_train": n, "repeat": rep, "model": a, "mean_R2_log": float(np.mean(r2)),
                     **{f"R2_{t}": v for t, v in zip(TARGET_NAMES, r2)}})
    return rows


def main():
    saved = json.loads((MODELS/"run_params.json").read_text())
    jobs = [(n, r, saved["params"], saved["feature_set"]) for n in SIZES for r in range(REPEATS)]
    rows = []
    with ProcessPoolExecutor(6) as ex:
        for out in ex.map(job, jobs):
            rows += out
            print(f"n={out[0]['n_train']} rep={out[0]['repeat']} composite mean R2 "
                  f"{[r['mean_R2_log'] for r in out if r['model'] == 'composite'][0]:.3f}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT/"learning_curve.csv", index=False)
    summ = df.groupby(["model", "n_train"])[["mean_R2_log", "R2_depth", "R2_width", "R2_R"]].median().round(3)
    print(summ.to_string())

    fig, axs = plt.subplots(1, 3, figsize=(13, 3.8), sharex=True)
    order = ["composite"] + MEMBERS
    for ax, col, title in zip(axs, ["mean_R2_log", "R2_width", "R2_R"],
                              ["mean over 8 outputs", "width", "R (median solidification rate)"]):
        for i, a in enumerate(order):
            g = df[df.model == a].groupby("n_train")[col]
            med, q1, q3 = g.median(), g.quantile(0.25), g.quantile(0.75)
            c = INK if a == "composite" else SERIES[i - 1]
            ax.fill_between(med.index, q1, q3, color=c, alpha=0.12, lw=0)
            ax.plot(med.index, med, color=c, marker="o", ms=4, lw=2.4 if a == "composite" else 1.4,
                    label=a.replace("Gaussian Process", "GP").replace("Neural Network", "neural net"))
        ax.set_ylim(max(-0.2, ax.get_ylim()[0]), 1.0)
        ax.set_title(f"Out-of-sample R² (log): {title}", loc="left")
        ax.set_xlabel("number of training runs")
    axs[0].set_ylabel("R² (median of 5 draws, band: IQR)")
    axs[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(OUT/"fig_learning_curve.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
