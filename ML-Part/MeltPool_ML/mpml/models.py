"""Multi-output k-fold ensembles (Wang et al. 2024, Sec. 2.3 and Fig. 4a)
for the paper's five algorithms plus a Gaussian process.

Each algorithm is trained as a k-fold ensemble: the training runs are split
into k folds, k models are trained on k-1 folds each (the left-out fold is
the validation set for early stopping), and this is repeated N times with
new splits, giving k x N models whose predictions are averaged. The final
composite averages the algorithm ensembles; its spread across algorithms
is the uncertainty sigma (as in the replication, ML-Part/Replicated_Paper).

Multi-output: the neural net, random forest, XGBoost and the GP fit all
targets in one model; SVR and Bayesian ridge are single-output methods and
are wrapped in MultiOutputRegressor (one model per target).

Folds can be grouped (GroupKFold) so that rows from the same simulation
never sit on both sides of a split (needed for the event-level data).
"""

import copy

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import xgboost as xgb
from sklearn.ensemble import RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.linear_model import BayesianRidge
from sklearn.model_selection import GroupKFold, KFold
from sklearn.multioutput import MultiOutputRegressor
from sklearn.svm import SVR

ALGORITHMS = ["XGBoost", "SVM", "Neural Network", "Random Forest", "Bayesian Ridge", "Gaussian Process"]
MEMBERS = [a for a in ALGORITHMS if a != "Random Forest"]  # see Composite


class Net(nn.Module):
    """Paper architecture (mmc3): Linear -> LeakyReLU -> Dropout, twice,
    then a linear output layer, here with one output per target."""

    def __init__(self, n_in, n_out, first, second, first_drop, second_drop):
        super().__init__()
        self.l1, self.d1 = nn.Linear(n_in, first), nn.Dropout(first_drop)
        self.l2, self.d2 = nn.Linear(first, second), nn.Dropout(second_drop)
        self.l3 = nn.Linear(second, n_out)

    def forward(self, x):
        x = self.d1(F.leaky_relu(self.l1(x)))
        x = self.d2(F.leaky_relu(self.l2(x)))
        return self.l3(x)


class NNRegressor:
    """Full-batch Adam on MSE with early stopping on the validation fold
    (patience 20, as in the replication)."""

    def __init__(self, first=117, second=95, first_drop=0.09, second_drop=0.72,
                 lr=0.0253, num_epochs=80, patience=20, batch_size=None, seed=0):
        self.kw = dict(first=first, second=second, first_drop=first_drop, second_drop=second_drop)
        self.lr, self.num_epochs, self.patience = lr, num_epochs, patience
        self.batch_size, self.seed = batch_size, seed

    def fit(self, X, Y, X_val=None, Y_val=None):
        torch.manual_seed(self.seed)
        Y = Y.reshape(len(Y), -1)
        self.model = Net(X.shape[1], Y.shape[1], **self.kw)
        opt = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        Xt, Yt = torch.tensor(X, dtype=torch.float32), torch.tensor(Y, dtype=torch.float32)
        val = X_val is not None
        if val:
            Xv = torch.tensor(X_val, dtype=torch.float32)
            Yv = torch.tensor(Y_val.reshape(len(Y_val), -1), dtype=torch.float32)
        g = torch.Generator().manual_seed(self.seed)
        best, best_state, wait = np.inf, None, 0
        for _ in range(self.num_epochs):
            self.model.train()
            batches = [slice(None)] if not self.batch_size else \
                torch.randperm(len(Xt), generator=g).split(self.batch_size)
            for b in batches:
                opt.zero_grad()
                F.mse_loss(self.model(Xt[b]), Yt[b]).backward()
                opt.step()
            if val:
                self.model.eval()
                with torch.no_grad():
                    loss = F.mse_loss(self.model(Xv), Yv).item()
                if loss < best:
                    best, best_state, wait = loss, copy.deepcopy(self.model.state_dict()), 0
                else:
                    wait += 1
                    if wait >= self.patience:
                        break
        if best_state is not None:
            self.model.load_state_dict(best_state)
        self.model.eval()
        return self

    def predict(self, X):
        with torch.no_grad():
            return self.model(torch.tensor(X, dtype=torch.float32)).numpy()


# Defaults: the paper's tuned values (mmc3) where the algorithm is the
# paper's; the runs here re-tune them with Optuna (Eq. 1) on our data.
DEFAULTS = {
    "XGBoost": dict(k=2, N=2, max_depth=3, min_child_weight=12, gamma=0.1246, learning_rate=0.264,
                    subsample=0.84, colsample_bytree=0.72, reg_alpha=18.63, reg_lambda=24.03,
                    n_estimators=1403, early_stopping_rounds=18),
    "SVM": dict(k=10, N=1, C=999.8, gamma=0.0999, epsilon=0.0696),
    "Neural Network": dict(k=10, N=4, first=117, second=95, first_drop=0.09, second_drop=0.72,
                           lr=0.0253, num_epochs=80),
    "Random Forest": dict(k=10, N=5, n_estimators=99, max_depth=4, min_samples_split=10,
                          min_samples_leaf=13),
    "Bayesian Ridge": dict(k=9, N=3, alpha_1=2.1e-4, alpha_2=2.16e-6, lambda_1=0.1, lambda_2=8.2e-6),
    "Gaussian Process": dict(k=5, N=1, nu=2.5, n_restarts=2),
}


def make_model(algo, p, seed, n_features):
    """One base model with hyperparameters p (k and N are ignored here)."""
    p = {k: v for k, v in p.items() if k not in ("k", "N")}
    if algo == "XGBoost":
        return xgb.XGBRegressor(tree_method="hist", random_state=seed, n_jobs=4, **p)
    if algo == "SVM":
        return MultiOutputRegressor(SVR(kernel="rbf", **p))
    if algo == "Neural Network":
        return NNRegressor(seed=seed, **p)
    if algo == "Random Forest":
        return RandomForestRegressor(bootstrap=False, max_features=1.0, random_state=seed, n_jobs=4, **p)
    if algo == "Bayesian Ridge":
        return MultiOutputRegressor(BayesianRidge(**p))
    if algo == "Gaussian Process":
        kernel = ConstantKernel(1.0, (1e-2, 1e2))*Matern(np.ones(n_features), (1e-2, 1e2), nu=p["nu"]) \
            + WhiteKernel(1e-3, (1e-6, 1e-1))
        return GaussianProcessRegressor(kernel, normalize_y=True, n_restarts_optimizer=p["n_restarts"],
                                        random_state=seed)
    raise ValueError(algo)


def fit_one(algo, p, seed, X, Y, X_val, Y_val):
    m = make_model(algo, p, seed, X.shape[1])
    if algo == "XGBoost":
        m.fit(X, Y, eval_set=[(X_val, Y_val)], verbose=False)
    elif algo == "Neural Network":
        m.fit(X, Y, X_val, Y_val)
    else:
        m.fit(X, Y)
    return m


def predict_one(m, X):
    y = m.predict(X)
    return y.reshape(len(X), -1)


def splits(n, k, seed, groups=None):
    if groups is None:
        return KFold(n_splits=k, shuffle=True, random_state=seed).split(np.arange(n))
    # GroupKFold has no shuffle in older sklearn: shuffle group labels instead
    ug = np.unique(groups)
    perm = dict(zip(ug, np.random.RandomState(seed).permutation(len(ug))))
    return GroupKFold(n_splits=k).split(np.arange(n), groups=np.array([perm[g] for g in groups]))


class KFoldEnsemble:
    def __init__(self, algo, params, seed=0, max_rows=None):
        self.algo, self.p, self.seed = algo, dict(params), seed
        self.k, self.N = int(self.p.get("k", 5)), int(self.p.get("N", 1))
        self.max_rows = max_rows  # subsample cap per model (SVR/GP on event data)

    def fit(self, X, Y, groups=None):
        self.models = []
        rng = np.random.RandomState(self.seed)
        for n in range(self.N):
            s = self.seed + 17*n
            for f, (tr, va) in enumerate(splits(len(X), self.k, s, groups)):
                if self.max_rows and len(tr) > self.max_rows:
                    tr = rng.choice(tr, self.max_rows, replace=False)
                    va = rng.choice(va, min(len(va), self.max_rows), replace=False)
                self.models.append(fit_one(self.algo, self.p, s + 3*f, X[tr], Y[tr], X[va], Y[va]))
        return self

    def predict_all(self, X):
        return np.stack([predict_one(m, X) for m in self.models])  # (k*N, n, T)

    def predict(self, X):
        return self.predict_all(X).mean(0)


class Composite:
    """Average of the algorithm ensembles; sigma = spread across algorithms
    (np.std over the algorithm means, Wang et al. Sec. 2.4).

    All algorithms are trained (predict_algos reports each one), but only
    `members` enter mu and sigma. Random forest is left out: its Eq. 1
    score is below or near zero on both datasets (-0.34 runs, 0.08 events),
    the paper's reason for leaving out KNN (Wang et al. Sec. 3.2)."""

    def __init__(self, params, algos=ALGORITHMS, seed=0, max_rows=None, members=MEMBERS):
        self.ens = {a: KFoldEnsemble(a, params[a], seed, (max_rows or {}).get(a)) for a in algos}
        self.members = [a for a in members if a in self.ens]

    def fit(self, X, Y, groups=None):
        for e in self.ens.values():
            e.fit(X, Y, groups)
        return self

    def predict_algos(self, X):
        return {a: e.predict(X) for a, e in self.ens.items()}

    def predict(self, X):
        """mu, sigma and the (members, n, T) predictions of the members."""
        P = np.stack([self.ens[a].predict(X) for a in self.members])
        return P.mean(0), P.std(0), P

    @property
    def n_models(self):
        return sum(len(self.ens[a].models) for a in self.members)
