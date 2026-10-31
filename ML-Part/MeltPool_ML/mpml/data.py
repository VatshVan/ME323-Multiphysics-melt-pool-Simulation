"""Inputs, targets and transforms for the melt-pool ML models.

Inputs (one row per run):
    absorbed_power_W  P_abs = laser power x absorptivity (only the product
                      enters the heat source)
    scan_speed_mm_s   v
    beam_radius_mm    r
    beam_k            superGaussian exponent (2 Gaussian, 10/20 flat top)
    flow              1 = flow solved (buoyancy is on exactly when flow is,
                      so a separate buoyancy flag would be collinear)
    marangoni         1 = dSigma/dT = -2.6e-4 N/(m K), 0 = off

Scale inputs enter as logs, then min-max to [0, 1] over the data range
(the paper's min-max normalisation, Wang et al. 2024 Sec. 2.3).
Targets enter as logs (surface speed as log1p of mm/s, it is 0 without
flow) and are standardised per target.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
DATA = HERE/"data"
DSIGMADT = -2.6e-4  # N/(m K), the Marangoni-on runs

# Run-level targets: column, short name, unit
TARGETS = [
    ("qs_depth_mm", "depth", "mm"),
    ("qs_width_mm", "width", "mm"),
    ("qs_length_mm", "length", "mm"),
    ("qs_T_max_K", "T_max", "K"),
    ("qs_U_surface_mean_m_s", "U_surf", "m/s"),
    ("cooling_rate_median_K_s", "cooling_rate", "K/s"),
    ("G_median_K_mm", "G", "K/mm"),
    ("R_median_mm_s", "R", "mm/s"),
]
TARGET_COLS = [t[0] for t in TARGETS]
TARGET_NAMES = [t[1] for t in TARGETS]

# Candidate feature sets (Fig. 3 analogue). Each entry: name -> list of
# (feature name, function of the runs table, log?)
FEATURE_SETS = {
    "[P_abs, v, r]": [
        ("P_abs", lambda d: d["absorbed_power_W"], True),
        ("v", lambda d: d["scan_speed_mm_s"], True),
        ("r", lambda d: d["beam_radius_mm"], True),
    ],
    "[P_abs/v, v, r]": [
        ("P_abs/v", lambda d: d["absorbed_power_W"]/d["scan_speed_mm_s"], True),
        ("v", lambda d: d["scan_speed_mm_s"], True),
        ("r", lambda d: d["beam_radius_mm"], True),
    ],
    "[P_abs/sqrt(v r^3), v, r]": [
        # normalised enthalpy dH/h_s ~ A P / sqrt(v r^3) up to material constants
        ("H*", lambda d: d["absorbed_power_W"]/np.sqrt(d["scan_speed_mm_s"]*d["beam_radius_mm"]**3), True),
        ("v", lambda d: d["scan_speed_mm_s"], True),
        ("r", lambda d: d["beam_radius_mm"], True),
    ],
}
COMMON = [
    ("k", lambda d: d["beam_k"], True),
    ("flow", lambda d: d["flow"], False),
    ("marangoni", lambda d: d["marangoni"], False),
]


def load_runs():
    return pd.read_csv(DATA/"runs.csv")


def load_events():
    return pd.read_csv(DATA/"events.csv.gz")


def liquid():
    return json.loads((DATA/"liquid.json").read_text())


class Features:
    """Builds the normalised input matrix for one feature set. Bounds are
    fixed from a reference table (all 46 runs) so new inputs, the virtual
    SHAP grid and the experiment cases share one scale."""

    def __init__(self, set_name, reference):
        self.set_name = set_name
        self.names = [s[0] for s in self.spec]
        raw = self._raw(reference)
        self.lo, self.hi = raw.min(0), raw.max(0)
        self.hi = np.where(self.hi > self.lo, self.hi, self.lo + 1)

    @property
    def spec(self):  # rebuilt from the name, so the object pickles
        return FEATURE_SETS[self.set_name] + COMMON

    def _raw(self, d):
        cols = []
        for _, f, log in self.spec:
            x = np.asarray(f(d), float)
            cols.append(np.log(x) if log else x)
        return np.column_stack(cols)

    def __call__(self, d):
        return (self._raw(d) - self.lo)/(self.hi - self.lo)


class Targets:
    """log transform + standardisation of the run-level targets."""

    def __init__(self, cols=TARGET_COLS):
        self.cols = list(cols)

    @staticmethod
    def _fwd(c, y):
        return np.log1p(y*1e3) if c == "qs_U_surface_mean_m_s" else np.log(y)

    @staticmethod
    def _inv(c, z):
        return np.expm1(z)*1e-3 if c == "qs_U_surface_mean_m_s" else np.exp(z)

    def fit(self, d):
        z = np.column_stack([self._fwd(c, d[c].values) for c in self.cols])
        self.mu, self.sd = z.mean(0), z.std(0)
        return self

    def __call__(self, d):
        z = np.column_stack([self._fwd(c, d[c].values) for c in self.cols])
        return (z - self.mu)/self.sd

    def to_physical(self, Z):
        """Standardised (..., n_targets) -> physical units, any leading shape."""
        Z = np.asarray(Z)*self.sd + self.mu
        return np.stack([self._inv(c, Z[..., i]) for i, c in enumerate(self.cols)], -1)


def derived_numbers(T_max_K, width_mm, U_surf_m_s, marangoni):
    """Ma and Pe from predicted T_max, width and mean surface speed, with
    the definitions of scripts/export_excel.py (Farzadi et al. 2008
    Eqs. 14, 17): L_R = half width, dT = T_max - T_sol,
    Ma = rho L_R dT |dSigma/dT| / mu^2, Pe = u rho cp L_R / k."""
    m = liquid()
    L_R = np.asarray(width_mm, float)*1e-3/2
    dT = np.clip(np.asarray(T_max_K, float) - m["T_sol"], 0, None)
    Ma = m["rho"]*L_R*dT*abs(DSIGMADT)*np.asarray(marangoni, float)/m["mu"]**2
    Pe = np.asarray(U_surf_m_s, float)*m["rho"]*m["cp"]*L_R/m["k"]
    return Ma, Pe
