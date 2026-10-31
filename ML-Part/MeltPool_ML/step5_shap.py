#!/usr/bin/env python3
"""Surrogate SHAP (Wang et al. 2024 Secs. 2.5, 3.4; Figs. 6-7).

1. Virtual grid: P_abs 300-800 W, v 3-12 mm/s, r 0.5-1.5 mm, 21 values
   each (9261 points), with Marangoni on and off (flow on, Gaussian beam
   k = 2, the beam of the R and V runs that span r): 18522 points.
2. The final composite predicts every grid point.
3. One default-parameter XGBoost surrogate per output on the raw inputs
   [P_abs, v, r, Marangoni]; TreeSHAP main and interaction values.
4. LOWESS trend lines on the dependence plots, as in the paper.

Part of the grid lies outside the simulated runs (e.g. r = 0.5 mm at
3 mm/s and 800 W); the SHAP values describe the model there, not data.
"""

import pickle
import warnings

import numpy as np
import pandas as pd
import shap
import statsmodels.api as sm
import xgboost as xgb
from sklearn.metrics import r2_score

from mpml.data import TARGET_NAMES, TARGETS, HERE
from mpml.plots import INK, MODE_STYLE, MUTED, SERIES, plt

OUT, MODELS = HERE/"results", HERE/"models"
FEATS = ["P_abs [W]", "v [mm/s]", "r [mm]", "Marangoni"]
SHOW = ["depth", "width", "T_max", "cooling_rate", "G", "R"]


def grid():
    P = np.linspace(300, 800, 21)
    v = np.linspace(3, 12, 21)
    r = np.linspace(0.5, 1.5, 21)
    m = np.array([0, 1])
    g = np.array(np.meshgrid(P, v, r, m, indexing="ij")).reshape(4, -1).T
    return pd.DataFrame({"absorbed_power_W": g[:, 0], "scan_speed_mm_s": g[:, 1], "beam_radius_mm": g[:, 2],
                         "beam_k": 2.0, "flow": 1, "marangoni": g[:, 3]})


def lowess(x, y, frac=0.3):
    s = sm.nonparametric.lowess(y, x, frac=frac, return_sorted=True)
    return s[:, 0], s[:, 1]


def main():
    warnings.filterwarnings("ignore")
    with open(MODELS/"run_composite.pkl", "rb") as f:
        d = pickle.load(f)
    G = grid()
    mu = d["targets"].to_physical(d["model"].predict(d["features"](G))[2]).mean(0)
    X = G[["absorbed_power_W", "scan_speed_mm_s", "beam_radius_mm", "marangoni"]].values
    rng = np.random.RandomState(0)
    sub = rng.choice(len(X), 4000, replace=False)  # interaction values on a subsample (cost ~ n x features^2)

    imp, inter, main_sv, inter_sv = {}, {}, {}, {}
    for name in SHOW:
        y = mu[:, TARGET_NAMES.index(name)]
        sur = xgb.XGBRegressor(random_state=0).fit(X, y)
        r2 = r2_score(y, sur.predict(X))
        ex = shap.TreeExplainer(sur)
        sv = ex.shap_values(X)
        iv = ex.shap_interaction_values(X[sub])
        main_sv[name], inter_sv[name] = sv, iv
        imp[name] = np.abs(sv).mean(0)
        inter[name] = {f"{FEATS[i].split()[0]}×{FEATS[j].split()[0]}": np.abs(iv[:, i, j]).mean()*2
                       for i in range(4) for j in range(i + 1, 4)}
        print(f"{name:12s} surrogate R2 {r2:.5f}  mean|SHAP| " +
              "  ".join(f"{f.split()[0]} {v:.3g}" for f, v in zip(FEATS, imp[name])))
    imp_df = pd.DataFrame(imp, index=[f.split()[0] for f in FEATS]).T
    inter_df = pd.DataFrame(inter).T
    imp_df.to_csv(OUT/"shap_main_importance.csv")
    inter_df.to_csv(OUT/"shap_interaction_importance.csv")
    print("\nInteraction importance (mean |SHAP interaction| x 2):\n" + inter_df.round(4).to_string())

    units = {n: u for _, n, u in TARGETS}
    # Fig. 6a: share of mean |SHAP| per output
    share = imp_df.div(imp_df.sum(1), axis=0)
    fig, ax = plt.subplots(figsize=(6.4, 2.9))
    left = np.zeros(len(share))
    for i, f in enumerate(share.columns):
        ax.barh(share.index, share[f], left=left, height=0.6, color=SERIES[i], label=f,
                edgecolor="white", linewidth=2)
        for k, (l, w) in enumerate(zip(left, share[f])):
            if w > 0.07:
                ax.text(l + w/2, k, f"{100*w:.0f}%", ha="center", va="center", color="white", fontsize=8)
        left += share[f].values
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("share of mean |SHAP| (surrogate of the composite)")
    ax.legend(ncol=4, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    ax.grid(axis="y", visible=False)
    fig.savefig(OUT/"fig6a_shap_importance.png")
    plt.close(fig)

    # Fig. 6b: SHAP main values vs each continuous input, depth and width, coloured by Marangoni
    fig, axs = plt.subplots(2, 3, figsize=(10, 5.4))
    for row, name in enumerate(["depth", "width"]):
        sv = main_sv[name]
        for col in range(3):
            ax = axs[row, col]
            for ma, mode in ((1, "MaB"), (0, "B")):
                c, mk, lab = MODE_STYLE[mode]
                sel = (X[:, 3] == ma)
                pick = np.where(sel)[0][::7]
                ax.scatter(X[pick, col], sv[pick, col], s=4, color=c, alpha=0.25, lw=0)
                xl, yl = lowess(X[sel, col][::3], sv[sel, col][::3])
                ax.plot(xl, yl, color=c, label=lab)
            ax.axhline(0, color=MUTED, lw=0.8)
            ax.set_xlabel(FEATS[col])
            if col == 0:
                ax.set_ylabel(f"SHAP for {name} [{units[name]}]")
    axs[0, 2].legend(fontsize=8)
    fig.suptitle("SHAP main values with LOWESS trends, split by Marangoni on/off", x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT/"fig6b_shap_main.png")
    plt.close(fig)

    # Fig. 7: interaction importance heatmap + Marangoni x P_abs interaction for depth and width
    fig, axs = plt.subplots(1, 3, figsize=(12, 3.6), gridspec_kw={"width_ratios": [1.3, 1, 1]})
    ax = axs[0]
    norm = inter_df.div(inter_df.max(1), axis=0)
    im = ax.imshow(norm.values, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(norm.shape[1]), norm.columns, rotation=40, ha="right")
    ax.set_yticks(range(norm.shape[0]), norm.index)
    for i in range(norm.shape[0]):
        for j in range(norm.shape[1]):
            ax.text(j, i, f"{norm.values[i, j]:.2f}", ha="center", va="center",
                    color="white" if norm.values[i, j] > 0.6 else INK, fontsize=7)
    ax.grid(False)
    ax.set_title("interaction importance (row max = 1)", loc="left")
    for ax, name in zip(axs[1:], ["depth", "width"]):
        iv = inter_sv[name][:, 0, 3]*2
        xs = X[sub]
        for ma, mode in ((1, "MaB"), (0, "B")):
            c, mk, lab = MODE_STYLE[mode]
            sel = xs[:, 3] == ma
            ax.scatter(xs[sel, 0], iv[sel], s=5, color=c, alpha=0.3, lw=0)
            xl, yl = lowess(xs[sel, 0], iv[sel])
            ax.plot(xl, yl, color=c, label=lab)
        ax.axhline(0, color=MUTED, lw=0.8)
        ax.set_xlabel("P_abs [W]")
        ax.set_ylabel(f"P_abs × Marangoni SHAP [{units[name]}]")
        ax.set_title(f"{name}: power–Marangoni interaction", loc="left")
    axs[2].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT/"fig7_shap_interactions.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
