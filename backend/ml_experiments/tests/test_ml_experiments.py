"""Tests for the Phase 13 experiment harness.

IMPORTANT: these tests prove the HARNESS is correct (no look-ahead, no leakage,
honest refusal when data is insufficient, reproducibility, labelling). They do
NOT, and cannot, show that any model is accurate on real markets or real news.

Run from backend/:   python -m unittest discover -s ml_experiments/tests -t .
(or: python -m pytest ml_experiments/tests)
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from ml_experiments import EXPERIMENTAL_NOTICE
from ml_experiments import sentiment_experiment as se
from ml_experiments import volatility_experiment as ve
from ml_experiments.common import moving_block_bootstrap_ci, write_report
from ml_experiments.run import main as cli_main

BACKEND = Path(__file__).resolve().parents[2]


def synthetic_prices(n=1100, seed=3):
    """Random walk whose volatility switches between calm and stormy regimes."""
    rng = np.random.default_rng(seed)
    vol = np.empty(n)
    level = 0.008
    for i in range(n):
        if i % 90 == 0:
            level = rng.choice([0.006, 0.012, 0.025])
        vol[i] = level
    returns = rng.normal(0, vol)
    price = 50 * np.exp(np.cumsum(returns))
    dates = pd.bdate_range("2015-01-01", periods=n)
    return pd.DataFrame({"date": dates, "price": price})


def synthetic_headlines(per_class=120, seed=5):
    rng = np.random.default_rng(seed)
    pos = ["profit surges", "strong growth", "beats forecasts", "record gains", "upgrade announced"]
    neg = ["shares plunge", "loss widens", "lawsuit filed", "weak demand", "downgrade issued"]
    neu = ["annual meeting scheduled", "board appoints director", "company opens office", "results due Tuesday"]
    rows = []
    for i in range(per_class):
        for lab, pool in (("positive", pos), ("negative", neg), ("neutral", neu)):
            rows.append((f"{pool[rng.integers(len(pool))]} at firm{i} {rng.integers(10**6)}", lab, f"firm{i % 30}"))
    return pd.DataFrame(rows, columns=["text", "label", "group"])


class VolatilityHarness(unittest.TestCase):
    def test_cleaning_counts_what_it_drops(self):
        raw = pd.DataFrame(
            {
                "Date": ["2020-01-02", "2020-01-02", "bad", "2020-01-03", "2020-01-06", "2020-01-07"],
                "Close": [10, 11, 12, -5, "x", 13],
            }
        )
        df, info = ve.clean_prices(raw)
        self.assertEqual(info["dropped"]["unparseable_date"], 1)
        self.assertEqual(info["dropped"]["non_positive_or_non_numeric_price"], 2)
        self.assertEqual(info["dropped"]["duplicate_date"], 1)
        self.assertEqual(len(df), 2)
        self.assertEqual(info["rows_read"], 6)

    def test_target_is_std_of_the_next_21_returns(self):
        df = synthetic_prices(300)
        s = ve.build_samples(df)
        r = np.diff(np.log(df["price"].to_numpy()))  # r[k] = return on row k+1
        row = 100
        sample = s[s["date"] == df["date"].iloc[row]].iloc[0]
        expected = np.std(r[row : row + 21], ddof=1)  # returns on rows row+1..row+21
        self.assertAlmostEqual(sample["target"], expected, places=12)

    def test_features_never_use_future_prices(self):
        """Rewrite every price after day 250 (day 250 itself is known at day 250): features on or before day 250 must not move."""
        df = synthetic_prices(400)
        changed = df.copy()
        changed.loc[251:, "price"] = changed.loc[251:, "price"] * np.random.default_rng(9).uniform(0.5, 2.0, 149)
        a, b = ve.build_samples(df), ve.build_samples(changed)
        cutoff = df["date"].iloc[250]
        a, b = a[a["date"] <= cutoff].reset_index(drop=True), b[b["date"] <= cutoff].reset_index(drop=True)
        self.assertGreater(len(a), 100)
        self.assertEqual(len(a), len(b))
        for f in ["vol_5", "vol_21", "vol_63", "ret_5", "ret_21", "abs_r1"]:
            np.testing.assert_array_equal(a[f].to_numpy(), b[f].to_numpy(), err_msg=f)

    def test_walk_forward_purges_overlapping_targets(self):
        folds = ve.walk_forward_folds(900)
        self.assertGreaterEqual(len(folds), 3)
        previous_end = -1
        for train, test in folds:
            self.assertLessEqual(train.max() + ve.HORIZON, test.min())  # target window ended before test day
            self.assertGreater(test.min(), previous_end)  # test blocks never overlap
            self.assertEqual(train.min(), 0)
            previous_end = test.max()

    def test_refuses_to_report_numbers_on_short_history(self):
        report = ve.run(synthetic_prices(300), {"rows_used": 300}, {"name": "short"})
        self.assertEqual(report["status"], "insufficient_data")
        self.assertIsNone(report["results"])
        self.assertIn("No numbers were computed", report["message"])

    def test_full_run_is_labelled_experimental_and_reproducible(self):
        df = synthetic_prices()
        a = ve.run(df, {"rows_used": len(df)}, {"name": "syn"})
        b = ve.run(df, {"rows_used": len(df)}, {"name": "syn"})
        self.assertEqual(a["status"], "completed")
        self.assertTrue(a["experimental"])
        self.assertEqual(a["notice"], EXPERIMENTAL_NOTICE)
        self.assertEqual(json.dumps(a["results"], sort_keys=True), json.dumps(b["results"], sort_keys=True))
        self.assertTrue(a["limitations"])

    def test_report_has_no_trading_vocabulary(self):
        df = synthetic_prices()
        text = json.dumps(ve.run(df, {"rows_used": len(df)}, {"name": "syn"})).lower()
        for word in ("buy", "sell", "hold", "recommend", "outperform the market", "profit"):
            # allowed only inside the explicit disclaimer sentence
            stripped = text.replace(EXPERIMENTAL_NOTICE.lower(), "")
            self.assertNotRegex(stripped, rf"\b{re.escape(word)}\b", word)

    def test_sensible_on_clustered_volatility(self):
        """Sanity check of the pipeline, not a claim about markets: when
        volatility really is persistent, persistence should beat a constant."""
        df = synthetic_prices()
        r = ve.run(df, {"rows_used": len(df)}, {"name": "syn"})["results"]["metrics_by_model"]
        self.assertLess(r["persistence"]["mae_log"], r["historical_mean"]["mae_log"])

    def test_block_bootstrap_interval_contains_mean_and_is_seeded(self):
        x = np.random.default_rng(0).normal(0.1, 1, 300)
        m, lo, hi = moving_block_bootstrap_ci(x, block=21)
        self.assertLessEqual(lo, m)
        self.assertGreaterEqual(hi, m)
        self.assertEqual((m, lo, hi), moving_block_bootstrap_ci(x, block=21))


class SentimentHarness(unittest.TestCase):
    def test_cleaning_removes_leaky_and_untrustworthy_rows(self):
        raw = pd.DataFrame(
            {
                "text": ["Profit surges", "profit  surges", "Shares plunge", "Shares plunge", "", "ok news", "x"],
                "label": ["positive", "positive", "negative", "positive", "neutral", "mixed", "NEUTRAL"],
            }
        )
        df, info = se.clean_labelled(raw)
        self.assertEqual(info["dropped"]["empty_text"], 1)
        self.assertEqual(info["dropped"]["unknown_label"], 1)
        self.assertEqual(info["dropped"]["conflicting_duplicate_labels"], 2)
        self.assertEqual(info["dropped"]["exact_duplicate_text"], 1)
        self.assertEqual(sorted(df["label"]), ["neutral", "positive"])

    def test_refuses_without_enough_labelled_data(self):
        df, info = se.clean_labelled(synthetic_headlines(per_class=20))
        report = se.run(df, info, {"name": "tiny"})
        self.assertEqual(report["status"], "insufficient_data")
        self.assertIsNone(report["results"])
        self.assertIn("No accuracy figure was computed", report["message"])

    def test_lexicon_baseline_is_the_unchanged_phase8_scorer(self):
        from app.services import sentiment_engine

        texts = ["Profit surges and shares soar", "Shares plunge on fraud probe", "Annual meeting scheduled"]
        labels, no_signal = se.lexicon_predict(texts)
        expected = [sentiment_engine.score_text(t)["label"] for t in texts]
        self.assertEqual(labels, ["neutral" if e == "no_signal" else e for e in expected])
        self.assertAlmostEqual(no_signal, 1 / 3)

    def test_grouped_splits_never_share_a_group(self):
        df, info = se.clean_labelled(synthetic_headlines())
        groups = df["group"].astype(str).to_numpy()
        for train, test in se.make_splits(df["text"].to_numpy(), df["label"].to_numpy(), groups):
            self.assertFalse(set(groups[train]) & set(groups[test]))

    def test_full_run_structure_and_reproducibility(self):
        df, info = se.clean_labelled(synthetic_headlines())
        a = se.run(df, info, {"name": "syn"})
        b = se.run(df, info, {"name": "syn"})
        self.assertEqual(a["status"], "completed")
        self.assertTrue(a["experimental"])
        m = a["results"]["metrics_by_method"]
        self.assertEqual(set(m), {"majority_class", "lexicon", "tfidf_logreg"})
        self.assertLess(m["majority_class"]["macro_f1"], 0.5)  # balanced 3-class floor ~ 0.17
        self.assertEqual(json.dumps(a["results"], sort_keys=True), json.dumps(b["results"], sort_keys=True))
        conf = np.array(m["tfidf_logreg"]["confusion_matrix"]["rows_true_cols_predicted"])
        self.assertEqual(conf.sum(), len(df))  # every row predicted exactly once, out-of-fold


class NoLeakageInSentiment(unittest.TestCase):
    def test_predictions_are_out_of_fold(self):
        """Random labels carry no signal. A model scored on rows it was trained on
        would 'learn' them (memorisation); an honest out-of-fold score stays near chance."""
        rng = np.random.default_rng(11)
        vocab = [f"w{i}" for i in range(60)]
        rows = [(" ".join(rng.choice(vocab, 6)) + f" id{i}", rng.choice(se.LABELS), f"g{i}") for i in range(600)]
        df, info = se.clean_labelled(pd.DataFrame(rows, columns=["text", "label", "group"]))
        report = se.run(df, info, {"name": "random-labels"})
        self.assertEqual(report["status"], "completed")
        self.assertLess(report["results"]["metrics_by_method"]["tfidf_logreg"]["macro_f1"], 0.5)


class IsolationAndSafety(unittest.TestCase):
    def test_app_never_imports_the_experiments(self):
        for path in (BACKEND / "app").rglob("*.py"):
            self.assertNotIn("ml_experiments", path.read_text(encoding="utf-8"), str(path))

    def test_no_network_or_pickle_code_in_the_experiments(self):
        banned = re.compile(r"\b(pickle|joblib|httpx|requests|urllib|socket|urlopen|subprocess)\b")
        for path in (BACKEND / "ml_experiments").glob("*.py"):
            code = "\n".join(
                line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")
            )
            # docstring words like "no pickle" are fine; imports/calls are not
            for line in code.splitlines():
                if line.lstrip().startswith(("import ", "from ")):
                    self.assertIsNone(banned.search(line), f"{path.name}: {line}")
            self.assertNotRegex(code, r"(pickle|joblib)\.(dump|load)")

    def test_reports_never_overwrite_and_cli_reports_insufficient_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv = Path(tmp) / "tiny.csv"
            synthetic_headlines(per_class=10).to_csv(csv, index=False)
            out = Path(tmp) / "reports"
            self.assertEqual(cli_main(["sentiment", "--data", str(csv), "--out", str(out)]), 0)
            files = list(out.glob("*.json"))
            self.assertEqual(len(files), 1)
            body = json.loads(files[0].read_text())
            self.assertEqual(body["status"], "insufficient_data")
            self.assertTrue(body["experimental"])
            with self.assertRaises(FileExistsError):
                # same second, same name -> exclusive create must refuse
                import ml_experiments.common as c

                original = c.datetime
                try:
                    class Fixed(original):
                        @classmethod
                        def now(cls, tz=None):
                            return original.strptime(files[0].stem.split("_")[-1], "%Y%m%dT%H%M%SZ").replace(tzinfo=tz)

                    c.datetime = Fixed
                    write_report(body, out)
                finally:
                    c.datetime = original


if __name__ == "__main__":
    unittest.main()
