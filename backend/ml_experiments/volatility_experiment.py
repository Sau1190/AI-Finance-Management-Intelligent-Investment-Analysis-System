"""Experiment A - can a small ML model forecast NEXT-MONTH VOLATILITY better
than naive baselines?  (EXPERIMENTAL)

Why volatility and not price direction: volatility clusters, so it is the one
quantity where simple models have a documented, testable signal, and a
volatility estimate is descriptive (it says how bumpy prices may be), not a
call to buy or sell. This module deliberately has NO price-direction or
return prediction.

Target (what is forecast, "the label"): the standard deviation of the next
H=21 daily log returns, known only after the fact. Features at day t use data
up to and including day t only.

Models compared, all with fixed (untuned) settings:
  persistence      forecast = trailing 21-day volatility (the naive baseline;
                   this is the number the existing Phase 9 risk module reports)
  historical_mean  forecast = typical volatility seen in the training window
  ridge            linear model on log-volatility features (HAR-style)
  gradient_boosting small boosted-tree regressor

Evaluation: expanding-window walk-forward. A training sample is used only if
its 21-day target window ended before the test day (purge gap), so no future
information leaks into training. Paired error differences vs persistence get a
moving-block bootstrap interval, because overlapping windows make neighbouring
errors correlated.

Output is a report saying whether any model beat persistence on THIS dataset.
It is not a claim about markets in general.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from ml_experiments.common import SEED, moving_block_bootstrap_ci, new_report

HORIZON = 21
FEATURE_WINDOWS = (5, 21, 63)
MIN_TRAIN = 252
TEST_BLOCK = 63
MIN_SAMPLES = 750  # ~3 years of daily samples after warm-up and horizon
JUMP_THRESHOLD = 0.40  # |single-day log return| above this is flagged
EPS = 1e-8

MODEL_NAMES = ("persistence", "historical_mean", "ridge", "gradient_boosting")

LIMITATIONS = [
    "The result describes this dataset and period only; it is not evidence about other stocks or other years.",
    "Hyperparameters are fixed, not tuned; a different configuration could change the ranking.",
    "Forecasts use closing prices only; no volume, news, fundamentals or market-wide data.",
    "Unadjusted prices make splits look like crashes; flagged jumps are reported, never silently removed.",
    "Volatility is a statistical description of past price movement, not a measure of whether an investment is good or bad.",
]


# ---------------------------------------------------------------- loading ---
def load_prices(path: str, price_column: str = "close") -> tuple[pd.DataFrame, dict]:
    """Read a price CSV with a date column and a price column.

    Rows with an unparseable date, a non-positive/non-finite price, or a
    duplicate date are dropped and COUNTED in the returned info - nothing is
    repaired or interpolated.
    """
    raw = pd.read_csv(path)
    return clean_prices(raw, price_column)


def clean_prices(raw: pd.DataFrame, price_column: str = "close") -> tuple[pd.DataFrame, dict]:
    cols = {c.strip().lower().replace(" ", "_").replace(".", "").replace("*", ""): c for c in raw.columns}
    wanted = price_column.strip().lower().replace(" ", "_")
    if "date" not in cols or wanted not in cols:
        raise ValueError(f"CSV needs 'date' and '{price_column}' columns; found {list(raw.columns)}")
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(raw[cols["date"]], errors="coerce"),
            "price": pd.to_numeric(raw[cols[wanted]], errors="coerce"),
        }
    )
    info = {"rows_read": int(len(df)), "dropped": {}}
    bad_date = df["date"].isna()
    info["dropped"]["unparseable_date"] = int(bad_date.sum())
    df = df[~bad_date]
    bad_price = ~np.isfinite(df["price"]) | (df["price"] <= 0)
    info["dropped"]["non_positive_or_non_numeric_price"] = int(bad_price.sum())
    df = df[~bad_price]
    df = df.sort_values("date", kind="stable")
    dup = df["date"].duplicated(keep="first")
    info["dropped"]["duplicate_date"] = int(dup.sum())
    df = df[~dup].reset_index(drop=True)
    info["rows_used"] = int(len(df))
    if len(df) >= 2:
        info["first_date"] = df["date"].iloc[0].date().isoformat()
        info["last_date"] = df["date"].iloc[-1].date().isoformat()
        info["max_gap_days"] = int(df["date"].diff().dt.days.max())
    return df, info


def load_matplotlib_goog() -> tuple[pd.DataFrame, dict]:
    """Real daily GOOG bars (2004-2008) that ship inside matplotlib's sample data.

    Used only as a reproducible demonstration dataset: single stock, single
    period, includes the 2008 crash. Adjusted close is used.
    """
    import matplotlib

    path = Path(matplotlib.get_data_path()) / "sample_data" / "goog.npz"
    with np.load(path, allow_pickle=False) as archive:  # no pickle: plain structured array
        data = archive["price_data"]
    raw = pd.DataFrame({"date": data["date"].astype("datetime64[D]").astype(str), "close": data["adj_close"]})
    df, info = clean_prices(raw, "close")
    info["dataset"] = "matplotlib sample_data goog.npz (adjusted close)"
    return df, info


# ------------------------------------------------------- features/targets ---
def build_samples(df: pd.DataFrame, horizon: int = HORIZON) -> pd.DataFrame:
    """One row per day t with features from data <= t and the forward target.

    Rows without a full feature window or without a full forward window are
    absent (never padded).
    """
    price = df["price"].to_numpy(dtype=float)
    r = pd.Series(np.diff(np.log(price)), index=df.index[1:])  # r_t = ln(P_t / P_{t-1})
    r = r.reindex(df.index)  # r at index 0 is NaN
    out = pd.DataFrame(index=df.index)
    out["date"] = df["date"]
    for w in FEATURE_WINDOWS:
        out[f"vol_{w}"] = r.rolling(w).std(ddof=1)
    out["ret_5"] = r.rolling(5).sum()
    out["ret_21"] = r.rolling(21).sum()
    out["abs_r1"] = r.abs()
    # forward std of r_{t+1..t+h}: rolling std ending at t+h, shifted back by h
    out["target"] = r.rolling(horizon).std(ddof=1).shift(-horizon)
    out = out.dropna().reset_index(drop=True)
    return out


def feature_matrix(samples: pd.DataFrame) -> np.ndarray:
    cols = [np.log(samples[f"vol_{w}"].to_numpy() + EPS) for w in FEATURE_WINDOWS]
    cols.append(np.log(samples["abs_r1"].to_numpy() + 1e-4))
    cols.append(samples["ret_5"].to_numpy())
    cols.append(samples["ret_21"].to_numpy())
    return np.column_stack(cols)


FEATURE_NAMES = [f"log_vol_{w}" for w in FEATURE_WINDOWS] + ["log_abs_return_1d", "return_5d", "return_21d"]


# --------------------------------------------------------------- metrics ---
def _metrics(actual: np.ndarray, forecast: np.ndarray) -> dict:
    a = np.asarray(actual, float)
    f = np.maximum(np.asarray(forecast, float), EPS)
    ratio = (a**2) / (f**2)
    return {
        "mae": float(np.mean(np.abs(a - f))),
        "rmse": float(math.sqrt(np.mean((a - f) ** 2))),
        "mae_log": float(np.mean(np.abs(np.log(a + EPS) - np.log(f)))),
        "qlike": float(np.mean(ratio - np.log(ratio) - 1.0)),  # lower is better; 0 = perfect
    }


def _fit_predict(name: str, X_tr, y_tr_log, X_te, vol21_te) -> np.ndarray:
    """Return forecasts on the volatility scale (not log)."""
    if name == "persistence":
        return vol21_te
    if name == "historical_mean":
        return np.full(len(X_te), math.exp(float(np.mean(y_tr_log))))
    scaler = StandardScaler().fit(X_tr)
    Xs, Xt = scaler.transform(X_tr), scaler.transform(X_te)
    if name == "ridge":
        model = Ridge(alpha=1.0)
    elif name == "gradient_boosting":
        model = GradientBoostingRegressor(
            n_estimators=100, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=SEED
        )
    else:
        raise ValueError(name)
    model.fit(Xs, y_tr_log)
    return np.exp(model.predict(Xt))


def walk_forward_folds(n: int, horizon: int = HORIZON) -> list[tuple[np.ndarray, np.ndarray]]:
    """Expanding-window folds over sample positions 0..n-1.

    Sample p's target covers days p+1..p+horizon (consecutive trading rows), so
    it is only usable for training a test block starting at s if p + horizon <= s.
    """
    folds = []
    s = MIN_TRAIN + horizon
    while s + TEST_BLOCK <= n:
        train = np.arange(0, s - horizon + 1)
        test = np.arange(s, s + TEST_BLOCK)
        folds.append((train, test))
        s += TEST_BLOCK
    return folds


# ------------------------------------------------------------------- run ---
def run(df: pd.DataFrame, load_info: dict, data_source: dict) -> dict:
    report = new_report(
        "volatility_forecast",
        data_source={**data_source, "load_info": load_info},
        parameters={
            "horizon_days": HORIZON,
            "feature_windows": list(FEATURE_WINDOWS),
            "features": FEATURE_NAMES,
            "min_train_samples": MIN_TRAIN,
            "test_block_samples": TEST_BLOCK,
            "min_total_samples": MIN_SAMPLES,
            "models": list(MODEL_NAMES),
            "ridge_alpha": 1.0,
            "gradient_boosting": {"n_estimators": 100, "max_depth": 2, "learning_rate": 0.05, "subsample": 0.8},
            "tuning": "none (fixed settings)",
            "target": "std of next 21 daily log returns",
        },
    )
    report["limitations"] = list(LIMITATIONS)

    warnings = []
    if len(df) >= 2:
        jumps = np.abs(np.diff(np.log(df["price"].to_numpy())))
        n_jumps = int((jumps > JUMP_THRESHOLD).sum())
        if n_jumps:
            warnings.append(
                f"{n_jumps} single-day moves above {JUMP_THRESHOLD:.0%} (possible unadjusted splits or bad data); "
                "kept as received and they will distort volatility."
            )
        if load_info.get("max_gap_days", 0) > 10:
            warnings.append(
                f"largest gap between rows is {load_info['max_gap_days']} days; the data may not be daily, "
                "and '21 rows' would then not mean 21 trading days."
            )
    report["data_warnings"] = warnings

    samples = build_samples(df)
    report["data_source"]["usable_samples"] = int(len(samples))
    if len(samples) < MIN_SAMPLES:
        report["status"] = "insufficient_data"
        report["results"] = None
        report["message"] = (
            f"Only {len(samples)} usable samples; at least {MIN_SAMPLES} are required before any "
            "performance figure is reported. No numbers were computed."
        )
        return report

    X = feature_matrix(samples)
    y = samples["target"].to_numpy()
    y_log = np.log(y + EPS)
    vol21 = samples["vol_21"].to_numpy()

    folds = walk_forward_folds(len(samples))
    if len(folds) < 3:
        report["status"] = "insufficient_data"
        report["results"] = None
        report["message"] = f"Only {len(folds)} walk-forward folds possible; at least 3 are required."
        return report

    test_idx = np.concatenate([te for _, te in folds])
    preds = {m: np.empty(len(test_idx)) for m in MODEL_NAMES}
    pos = 0
    for train, test in folds:
        for m in MODEL_NAMES:
            preds[m][pos : pos + len(test)] = _fit_predict(m, X[train], y_log[train], X[test], vol21[test])
        pos += len(test)

    actual = y[test_idx]
    per_model = {m: _metrics(actual, preds[m]) for m in MODEL_NAMES}

    base_err = np.abs(np.log(actual + EPS) - np.log(np.maximum(preds["persistence"], EPS)))
    comparisons = {}
    for m in MODEL_NAMES:
        if m == "persistence":
            continue
        err = np.abs(np.log(actual + EPS) - np.log(np.maximum(preds[m], EPS)))
        mean_diff, lo, hi = moving_block_bootstrap_ci(err - base_err, block=HORIZON)
        if hi < 0:
            verdict = "lower error than persistence on this dataset (interval excludes 0)"
        elif lo > 0:
            verdict = "higher error than persistence on this dataset (interval excludes 0)"
        else:
            verdict = "no clear difference from persistence (interval includes 0)"
        comparisons[m] = {
            "mean_abs_log_error_difference_vs_persistence": mean_diff,
            "ci95_low": lo,
            "ci95_high": hi,
            "negative_means_model_better": True,
            "verdict": verdict,
        }

    report["status"] = "completed"
    report["results"] = {
        "n_folds": len(folds),
        "n_test_samples": int(len(test_idx)),
        "test_period": {
            "first": samples["date"].iloc[test_idx[0]].date().isoformat(),
            "last": samples["date"].iloc[test_idx[-1]].date().isoformat(),
        },
        "metrics_by_model": per_model,
        "paired_comparison_vs_persistence": comparisons,
        "metric_notes": {
            "mae/rmse": "on the volatility scale (daily std of log returns); lower is better",
            "mae_log": "mean absolute error of log volatility; lower is better",
            "qlike": "standard volatility-forecast loss; lower is better",
            "interval": "95% moving-block bootstrap, block = 21 samples",
        },
    }
    return report
