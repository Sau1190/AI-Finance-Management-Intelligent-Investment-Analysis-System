"""Shared helpers: reproducibility metadata, report writing, bootstrap CIs.

Pure numpy/pandas/scikit-learn. No network access, no pickles (models are never
saved, so there is nothing to load back and nothing unsafe to deserialise).
"""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ml_experiments import EXPERIMENTAL_NOTICE

SEED = 20260101  # fixed so every run on the same data gives the same numbers


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def environment_info() -> dict:
    import pandas
    import sklearn

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pandas.__version__,
        "scikit_learn": sklearn.__version__,
    }


def new_report(experiment: str, *, data_source: dict, parameters: dict) -> dict:
    """Skeleton every report starts from. `status` is set by the experiment."""
    return {
        "experimental": True,
        "notice": EXPERIMENTAL_NOTICE,
        "experiment": experiment,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": SEED,
        "environment": environment_info(),
        "data_source": data_source,
        "parameters": parameters,
        "status": None,
        "results": None,
        "limitations": [],
    }


def write_report(report: dict, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = f"{report['experiment']}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    path = out / name
    with path.open("x", encoding="utf-8") as handle:  # never overwrite
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def moving_block_bootstrap_ci(
    values: np.ndarray,
    *,
    block: int,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = SEED,
) -> tuple[float, float, float]:
    """Mean of `values` with a (1-alpha) moving-block-bootstrap interval.

    Blocks keep neighbouring (autocorrelated) observations together; a plain
    bootstrap would give intervals that are too narrow for overlapping
    forecast windows. Returns (mean, low, high).
    """
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n == 0:
        raise ValueError("no values")
    block = max(1, min(block, n))
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    starts_max = n - block + 1
    means = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, starts_max, size=n_blocks)
        sample = np.concatenate([values[s : s + block] for s in starts])[:n]
        means[b] = sample.mean()
    low, high = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(values.mean()), float(low), float(high)
