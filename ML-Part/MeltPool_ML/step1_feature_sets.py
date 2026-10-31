#!/usr/bin/env python3
"""Fig. 3 analogue: compare candidate input sets with a default-parameter
multi-output XGBoost and 10-fold cross-validation over the runs
(Wang et al. 2024 Sec. 2.2), repeated 5 times with new fold splits.

Writes results/fig3_feature_sets.png and results/feature_sets.csv.
"""

import warnings

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import r2_score
from sklearn.model_selection import KFold

from mpml.data import FEATURE_SETS, TARGET_NAMES, Features, Targets, load_runs, HERE
from mpml.plots import INK, MUTED, SERIES, plt

OUT = HERE/"results"
REPEATS = 5


def main():
    OUT.mkdir(exist_ok=True)
    runs = load_runs()
    Y = Targets().fit(runs)(runs)
    rows = []
    for name in FEATURE_SETS:
        X = Features(name, runs)(runs)
        for rep in range(REPEATS):
            pred = np.zeros_like(Y)
            for tr, va in KFold(10, shuffle=True, random_state=rep).split(X):
                m = xgb.XGBRegressor(tree_method="hist", random_state=rep, n_jobs=4)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    m.fit(X[tr], Y[tr])
                pred[va] = m.predict(X[va])
            r2 = r2_score(Y, pred, multioutput="raw_values")
            rows += [{"feature_set": name, "repeat": rep, "target": t, "R2": v}
                     for t, v in zip(TARGET_NAMES, r2)]
    df = pd.DataFrame(rows)
    df.to_csv(OUT/"feature_sets.csv", index=False)
    per_rep = df.groupby(["feature_set", "repeat"])["R2"].mean().unstack()
    summary = pd.DataFrame({"mean_R2": per_rep.mean(1), "sd_over_repeats": per_rep.std(1)})
    print(summary.round(3).to_string())
    print(df.groupby(["target", "feature_set"])["R2"].mean().unstack().round(3).to_string())

    fig, ax = plt.subplots(figsize=(5.2, 2.6))
    names = list(FEATURE_SETS)
    y = np.arange(len(names))
    vals = summary.loc[names, "mean_R2"].values
    err = summary.loc[names, "sd_over_repeats"].values
    best = int(np.argmax(vals))
    ax.barh(y, vals, height=0.5, color=[SERIES[0] if i == best else MUTED for i in range(len(names))],
            xerr=err, error_kw={"ecolor": INK, "lw": 1, "capsize": 3})
    for i, v in enumerate(vals):
        ax.text(v + err[i] + 0.005, i, f"{v:.3f}", va="center", color=INK)
    ax.set_yticks(y, names)
    ax.invert_yaxis()
    ax.set_xlim(max(0, vals.min() - 0.1), 1.0)
    ax.set_xlabel("mean R² over 8 targets (10-fold CV, 5 repeats)")
    ax.set_title("Input set comparison, default XGBoost (+ beam k, flow, Marangoni flags)", loc="left")
    ax.grid(axis="y", visible=False)
    fig.savefig(OUT/"fig3_feature_sets.png")


if __name__ == "__main__":
    main()
