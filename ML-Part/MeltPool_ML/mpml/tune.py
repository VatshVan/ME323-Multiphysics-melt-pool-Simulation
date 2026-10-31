"""Optuna hyperparameter search with the paper's fitness function
(Wang et al. 2024, Eq. 1):

    F = R2_val - 3 |R2_train - R2_val|

R2 is averaged over the targets (standardised log space) and over the
k x N fold models; k and N are searched along with the hyperparameters,
as in the paper (its Fig. 4a). TPE sampler, as Optuna's default.
"""

import warnings

import numpy as np
import optuna
from sklearn.metrics import r2_score

from .models import fit_one, predict_one, splits


def fitness(r2_train, r2_val):
    return r2_val - 3.0*abs(r2_train - r2_val)


def space(trial, algo, events=False):
    s = trial.suggest_float, trial.suggest_int
    f, i = s
    p = {"k": i("k", 2, 10), "N": i("N", 1, 5)}
    if algo == "XGBoost":
        p.update(max_depth=i("max_depth", 2, 8), min_child_weight=i("min_child_weight", 1, 15),
                 gamma=f("gamma", 1e-3, 1.0, log=True), learning_rate=f("learning_rate", 0.01, 0.4, log=True),
                 subsample=f("subsample", 0.5, 1.0), colsample_bytree=f("colsample_bytree", 0.5, 1.0),
                 reg_alpha=f("reg_alpha", 1e-3, 30, log=True), reg_lambda=f("reg_lambda", 1e-3, 30, log=True),
                 n_estimators=i("n_estimators", 100, 1500), early_stopping_rounds=i("early_stopping_rounds", 10, 50))
    elif algo == "SVM":
        p.update(C=f("C", 0.1, 1000, log=True), gamma=f("gamma", 1e-3, 10, log=True),
                 epsilon=f("epsilon", 1e-3, 0.5, log=True))
    elif algo == "Neural Network":
        p.update(first=i("first", 8, 128), second=i("second", 8, 128),
                 first_drop=f("first_drop", 0.0, 0.8), second_drop=f("second_drop", 0.0, 0.8),
                 lr=f("lr", 1e-3, 0.05, log=True), num_epochs=i("num_epochs", 50, 1000 if not events else 200))
        if events:
            p["batch_size"] = 1024
    elif algo == "Random Forest":
        p.update(n_estimators=i("n_estimators", 20, 150), max_depth=i("max_depth", 2, 12),
                 min_samples_split=i("min_samples_split", 2, 15), min_samples_leaf=i("min_samples_leaf", 1, 15))
    elif algo == "Bayesian Ridge":
        p.update(alpha_1=f("alpha_1", 1e-7, 1e-1, log=True), alpha_2=f("alpha_2", 1e-7, 1e-1, log=True),
                 lambda_1=f("lambda_1", 1e-7, 1e-1, log=True), lambda_2=f("lambda_2", 1e-7, 1e-1, log=True))
    elif algo == "Gaussian Process":
        p.update(nu=trial.suggest_categorical("nu", [0.5, 1.5, 2.5]), n_restarts=1)
    if events:
        p["N"] = 1
        if algo == "Gaussian Process":
            p["k"] = i("k_gp", 2, 5)
    return p


def evaluate(algo, p, X, Y, seed=0, groups=None, max_rows=None):
    """Mean train / validation R2 of the k x N fold models and Eq. 1."""
    r2_tr, r2_va = [], []
    rng = np.random.RandomState(seed)
    for n in range(int(p["N"])):
        s = seed + 17*n
        for f, (tr, va) in enumerate(splits(len(X), int(p["k"]), s, groups)):
            if max_rows and len(tr) > max_rows:
                tr = rng.choice(tr, max_rows, replace=False)
            m = fit_one(algo, p, s + 3*f, X[tr], Y[tr], X[va], Y[va])
            r2_tr.append(r2_score(Y[tr], predict_one(m, X[tr])))
            r2_va.append(r2_score(Y[va], predict_one(m, X[va])))
    a, b = float(np.mean(r2_tr)), float(np.mean(r2_va))
    return fitness(a, b), a, b


def tune(algo, X, Y, n_trials, seed=0, groups=None, max_rows=None, events=False):
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        p = space(trial, algo, events)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            F, a, b = evaluate(algo, p, X, Y, seed, groups, max_rows)
        trial.set_user_attr("r2_train", a)
        trial.set_user_attr("r2_val", b)
        trial.set_user_attr("params", p)
        return F

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=n_trials)
    best = study.best_trial
    return best.user_attrs["params"], {"F": best.value, "r2_train": best.user_attrs["r2_train"],
                                        "r2_val": best.user_attrs["r2_val"], "n_trials": n_trials}
