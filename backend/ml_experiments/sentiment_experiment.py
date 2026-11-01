"""Experiment B - does a small ML text classifier beat the Phase 8 word-list
sentiment method on LABELLED headlines?  (EXPERIMENTAL)

This is the evaluation Phase 8 asked for ("accuracy NOT measured") - but it can
only produce numbers when YOU supply a labelled dataset. No labelled financial
text exists in this project, and none is downloaded or invented here. Without a
suitable file the experiment reports `insufficient_data` and computes nothing.

Input CSV columns: `text`, `label` (positive | negative | neutral), and an
optional `group` column (e.g. company or article id) so related headlines never
sit on both sides of a train/test split. Licence and provenance of the data are
the user's responsibility (e.g. Financial PhraseBank has its own terms).

Compared on identical out-of-fold rows:
  majority_class    always predicts the most common label (floor)
  lexicon           the existing deterministic Phase 8 scorer, unchanged
                    (a text with no lexicon term is "no_signal"; for this
                    3-class comparison it is counted as "neutral" and the
                    no-signal share is reported separately)
  tfidf_logreg      TF-IDF (1-2 grams) + logistic regression, fixed settings,
                    trained only on each fold's training part

The existing lexicon result is never modified or replaced.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold
from sklearn.pipeline import Pipeline

from app.services import sentiment_engine
from ml_experiments.common import SEED, new_report

LABELS = ("negative", "neutral", "positive")
MIN_ROWS = 200
MIN_PER_CLASS = 30
N_SPLITS = 5
N_BOOT = 1000

LIMITATIONS = [
    "Accuracy is only as meaningful as the labels: who labelled them, how, and whether they match this project's news style.",
    "Results describe the supplied dataset; headlines from another source or period may behave differently.",
    "Fixed, untuned settings; TF-IDF cannot read negation or context beyond 2-word phrases.",
    "The model is not saved or deployed; the Phase 8 lexicon remains the only sentiment used by the app.",
    "Sentiment of a headline is not a statement about whether a company's shares will rise or fall.",
]


def load_labelled(path: str) -> tuple[pd.DataFrame, dict]:
    return clean_labelled(pd.read_csv(path))


def clean_labelled(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    cols = {c.strip().lower(): c for c in raw.columns}
    if "text" not in cols or "label" not in cols:
        raise ValueError(f"CSV needs 'text' and 'label' columns; found {list(raw.columns)}")
    df = pd.DataFrame(
        {
            "text": raw[cols["text"]].astype("string"),
            "label": raw[cols["label"]].astype("string").str.strip().str.lower(),
        })
    has_group = "group" in cols
    df["group"] = raw[cols["group"]].astype("string") if has_group else pd.NA
    info = {"rows_read": int(len(df)), "dropped": {}, "has_group_column": has_group}

    empty = df["text"].isna() | (df["text"].str.strip() == "")
    info["dropped"]["empty_text"] = int(empty.sum())
    df = df[~empty]
    bad = ~df["label"].isin(LABELS)
    info["dropped"]["unknown_label"] = int(bad.sum())
    df = df[~bad].copy()

    df["key"] = df["text"].map(sentiment_engine.normalize_for_dedup)
    # identical text with conflicting labels cannot be a trustworthy example
    nlab = df.groupby("key")["label"].transform("nunique")
    conflict = nlab > 1
    info["dropped"]["conflicting_duplicate_labels"] = int(conflict.sum())
    df = df[~conflict]
    dup = df["key"].duplicated(keep="first")  # exact duplicates would leak across folds
    info["dropped"]["exact_duplicate_text"] = int(dup.sum())
    df = df[~dup].reset_index(drop=True)
    info["rows_used"] = int(len(df))
    info["class_counts"] = {lab: int((df["label"] == lab).sum()) for lab in LABELS}
    return df, info


def lexicon_predict(texts) -> tuple[list[str], float]:
    """Existing Phase 8 scorer, untouched. Returns (labels, no_signal_share)."""
    out, no_signal = [], 0
    for t in texts:
        label = sentiment_engine.score_text(str(t))["label"]
        if label == "no_signal":
            no_signal += 1
            label = "neutral"
        out.append(label)
    return out, (no_signal / len(out) if len(out) else 0.0)


def _make_model() -> Pipeline:
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, lowercase=True)),
            ("clf", LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced", random_state=SEED)),
        ]
    )


def _scores(y_true, y_pred) -> dict:
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=list(LABELS), zero_division=0)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=list(LABELS), average="macro", zero_division=0)),
        "per_class": {
            lab: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]), "support": int(s[i])}
            for i, lab in enumerate(LABELS)
        },
        "confusion_matrix": {
            "labels_in_order": list(LABELS),
            "rows_true_cols_predicted": confusion_matrix(y_true, y_pred, labels=list(LABELS)).tolist(),
        },
    }


def _paired_bootstrap_macro_f1(y, a, b, groups=None, n_boot=N_BOOT, seed=SEED):
    """95% interval for macro-F1(a) - macro-F1(b); resamples groups when given."""
    rng = np.random.default_rng(seed)
    y, a, b = np.asarray(y), np.asarray(a), np.asarray(b)
    n = len(y)
    if groups is not None:
        uniq, inv = np.unique(groups, return_inverse=True)
        members = [np.flatnonzero(inv == i) for i in range(len(uniq))]
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        if groups is None:
            idx = rng.integers(0, n, n)
        else:
            pick = rng.integers(0, len(members), len(members))
            idx = np.concatenate([members[j] for j in pick])
        fa = f1_score(y[idx], a[idx], labels=list(LABELS), average="macro", zero_division=0)
        fb = f1_score(y[idx], b[idx], labels=list(LABELS), average="macro", zero_division=0)
        diffs[i] = fa - fb
    lo, hi = np.quantile(diffs, [0.025, 0.975])
    return float(lo), float(hi)


def make_splits(texts, y, groups=None):
    """Stratified 5-fold; grouped too when `groups` is given, so one group never
    appears in both the training and the test part of a fold."""
    if groups is not None:
        return list(StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED).split(texts, y, groups))
    return list(StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED).split(texts, y))


def run(df: pd.DataFrame, load_info: dict, data_source: dict) -> dict:
    report = new_report(
        "sentiment_classifier",
        data_source={**data_source, "load_info": load_info},
        parameters={
            "labels": list(LABELS),
            "cv": f"{N_SPLITS}-fold, stratified" + (", grouped" if load_info.get("has_group_column") else ""),
            "min_rows": MIN_ROWS,
            "min_per_class": MIN_PER_CLASS,
            "model": "TF-IDF(1-2 grams, min_df=2) + LogisticRegression(C=1, class_weight=balanced)",
            "tuning": "none (fixed settings)",
            "lexicon_version": sentiment_engine.lex.LEXICON_VERSION,
            "no_signal_handling": "counted as neutral for this comparison; share reported",
            "bootstrap_resamples": N_BOOT,
        },
    )
    report["limitations"] = list(LIMITATIONS)

    counts = load_info.get("class_counts", {})
    too_few = [lab for lab in LABELS if counts.get(lab, 0) < MIN_PER_CLASS]
    if len(df) < MIN_ROWS or too_few:
        report["status"] = "insufficient_data"
        report["results"] = None
        report["message"] = (
            f"{len(df)} usable rows (need at least {MIN_ROWS}, and at least {MIN_PER_CLASS} per class; "
            f"short classes: {too_few or 'none'}). No accuracy figure was computed - a number from so "
            "little labelled data would not be trustworthy."
        )
        return report

    y = df["label"].to_numpy()
    texts = df["text"].astype(str).to_numpy()
    use_groups = bool(load_info.get("has_group_column")) and df["group"].notna().all()
    groups = df["group"].astype(str).to_numpy() if use_groups else None

    splits = make_splits(texts, y, groups)

    oof = np.empty(len(y), dtype=object)
    for train, test in splits:
        model = _make_model().fit(texts[train], y[train])
        oof[test] = model.predict(texts[test])

    lex_pred, no_signal_share = lexicon_predict(texts)
    lex_pred = np.asarray(lex_pred, dtype=object)
    majority = pd.Series(y).value_counts().idxmax()
    maj_pred = np.full(len(y), majority, dtype=object)

    lo, hi = _paired_bootstrap_macro_f1(y, oof, lex_pred, groups)
    if lo > 0:
        verdict = "ML macro-F1 higher than the lexicon on this dataset (interval excludes 0)"
    elif hi < 0:
        verdict = "ML macro-F1 lower than the lexicon on this dataset (interval excludes 0)"
    else:
        verdict = "no clear difference between ML and the lexicon (interval includes 0)"

    report["status"] = "completed"
    report["results"] = {
        "n_rows": int(len(y)),
        "n_folds": len(splits),
        "majority_class": str(majority),
        "metrics_by_method": {
            "majority_class": _scores(y, maj_pred),
            "lexicon": {**_scores(y, lex_pred), "no_signal_share": float(no_signal_share)},
            "tfidf_logreg": _scores(y, oof),
        },
        "ml_minus_lexicon_macro_f1": {"ci95_low": lo, "ci95_high": hi, "verdict": verdict},
    }
    return report
