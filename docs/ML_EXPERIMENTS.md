# Phase 13 - ML experiments (EXPERIMENTAL)

Status: complete as **offline research tooling**. Nothing here is wired into the API, the
database or the dashboard, and nothing here changes a stored analysis or score.

> EXPERIMENTAL. Not investment advice, not a recommendation, not a forecast of returns.
> The deterministic analysis (Phases 5-10) and the Phase 10 score remain the only source of
> truth. No ML output is stored, scored, explained or shown in the app.

## 1. Proposed scope (as agreed before implementation)

Two small, honest experiments. Each asks one question and can answer "no".

| | Experiment A - volatility forecast | Experiment B - sentiment classifier |
| --- | --- | --- |
| Question | Does a small model forecast the next 21 trading days' volatility better than naive baselines? | Does a TF-IDF classifier beat the Phase 8 word-list method on labelled headlines? |
| Why this one | Volatility clusters, so it is the one price quantity with a testable signal; it is descriptive, not a trade call. It extends Phase 9 (risk). | Phase 8 reported "accuracy NOT measured" and named this as the Phase 13 follow-up. |
| Label / target | Std of the next 21 daily log returns (derived from the price series itself) | Human labels `positive / neutral / negative` supplied by you |
| Models | persistence (trailing 21-day vol), historical mean, Ridge, small GradientBoosting | majority class, the **unchanged** Phase 8 lexicon, TF-IDF + logistic regression |
| Runs here? | Yes, on a real demo dataset (see 4) | **No** - no labelled data exists, so it reports `insufficient_data` |

Deliberately **out of scope**: predicting price direction or returns, buy/sell/hold or
"attractiveness" output, ML scoring, any endpoint or UI, deep learning, XGBoost, LLMs, paid
APIs, model files (no pickle/joblib - nothing is saved), tuning, Phase 14 hardening.

Why no API/UI: an endpoint would make it too easy for an experimental number to sit beside, or
quietly replace, a deterministic one. Keeping it offline also adds no attack surface before the
Phase 14 security review. If you later want it visible, do it as a separate, clearly labelled,
opt-in page.

## 2. Data inventory (what actually existed)

| Needed | Found in project / sandbox | Consequence |
| --- | --- | --- |
| Labelled financial text | None. Phase 8 tests contain a few hand-written headlines whose expected labels were written to match the lexicon (circular). | Experiment B cannot produce accuracy. The harness is ready; it refuses to compute below 200 rows or 30 per class. |
| Long daily price history | Project storage is empty; e2e fixtures are short synthetic series; live providers unreachable (no network). | Used a real daily series that ships inside matplotlib's sample data: GOOG, 2004-08-19 to 2008-10-14, 1,047 rows (adjusted close). Read from the installed package; not copied into this repo. |
| Dependencies | scikit-learn 1.8.0, numpy 2.4.4, pandas 3.0.2 available; XGBoost absent. | scikit-learn only. `backend/requirements-ml.txt` is optional and separate from `requirements.txt`. |

No data left the machine. No download, API call or LLM was used.

## 3. Evaluation method

* **Reproducible:** fixed seed, fixed (untuned) hyperparameters, data fingerprint (SHA-256) and
  library versions written into every JSON report. Same input gives identical numbers (tested).
* **No look-ahead (A):** features at day t use data up to t only (tested by rewriting all later
  prices). Expanding-window walk-forward; a training sample is used only if its 21-day target
  window ended before the test day (purge gap, tested). First 252 samples are training only.
* **No leakage (B):** exact and conflicting-label duplicate headlines are removed; TF-IDF is fit
  inside each training fold; predictions are out-of-fold; an optional `group` column keeps
  related headlines on one side of every split.
* **Baselines first:** a model only matters if it beats persistence (A) or the lexicon (B).
* **Metrics:** A - MAE, RMSE, MAE of log-vol, QLIKE; B - accuracy, macro-F1, per-class
  precision/recall/F1, confusion matrix.
* **Uncertainty:** paired differences vs the baseline get a 95% bootstrap interval (moving-block
  for A because overlapping windows correlate errors; group-aware for B). Verdict wording is
  rule-based: "better/worse" only if the interval excludes 0, otherwise "no clear difference".
* **Refusal:** below the minimum data, status is `insufficient_data`, `results` is `null`, and no
  number is computed.

## 4. Actual results

### Experiment A - GOOG demonstration (the only real-data result)

Command (from `backend/`, with `pip install -r requirements-ml.txt`):
`python -m ml_experiments.run volatility --source matplotlib-goog`. Saved report:
`docs/ml_results/volatility_goog_demo.json` (scikit-learn 1.8.0, Python 3.12.3, seed 20260101).

963 usable samples; 10 walk-forward folds; 630 out-of-sample days (2005-12-16 to 2008-06-19).
Lower is better. Volatility is the daily std of log returns (0.0059 is about 0.59% per day).

| Model | MAE | RMSE | MAE of log-vol | QLIKE |
| --- | --- | --- | --- | --- |
| **persistence (naive baseline)** | **0.00589** | 0.00823 | **0.2885** | **0.3075** |
| historical mean | 0.00677 | 0.00871 | 0.3482 | 0.4145 |
| ridge | 0.00615 | **0.00815** | 0.3114 | 0.3767 |
| gradient boosting | 0.00632 | 0.00836 | 0.3218 | 0.3786 |

Paired difference in mean absolute log error vs persistence (positive = model worse), 95% interval:

| Model | Difference | Interval | Verdict |
| --- | --- | --- | --- |
| historical mean | +0.060 | -0.027 to +0.151 | no clear difference |
| ridge | +0.023 | -0.043 to +0.098 | no clear difference |
| gradient boosting | +0.033 | -0.046 to +0.115 | no clear difference |

**What this does and does not say.** On this one stock and period, neither ML model beat the
naive trailing-volatility baseline on most measures, and no difference was statistically clear
either way (Ridge had the lowest RMSE by a hair, within noise). So there is **no evidence here
that these ML models add anything over what Phase 9 already reports**. It is not proof that ML
cannot help: one stock, one period (including the 2008 crash), 630 correlated test days, fixed
settings. Nothing from this run is a claim about future volatility, returns or any investment.

Sanity check of the harness (synthetic data with persistent volatility, in the tests):
persistence beats the constant-volatility baseline, as it should. That validates the pipeline,
not any market claim.

### Experiment B - sentiment

**No accuracy has been measured and none is claimed.** No labelled financial dataset was
available, so the experiment was never run on real text. On a tiny file it returns
`insufficient_data` (tested through the command line). The harness itself was exercised only on
synthetic template headlines, which is why those numbers are in no report and no document.

To obtain a real result: provide a CSV with `text,label[,group]` (at least 200 rows, 30 per
class), e.g. Financial PhraseBank, **after checking its licence and citation terms yourself**, then run
`python -m ml_experiments.run sentiment --data your_file.csv`.

## 5. How to run

```
cd backend
pip install -r requirements-ml.txt            # optional; adds scikit-learn only
python -m ml_experiments.run volatility --source matplotlib-goog
python -m ml_experiments.run volatility --prices my_prices.csv --price-column close
python -m ml_experiments.run sentiment  --data my_labelled_headlines.csv
python -m unittest discover -s ml_experiments/tests -t .      # 18 harness tests
```

Reports go to `backend/storage/ml_reports/` (git-ignored; never overwritten). Use **adjusted**
prices; the Phase 6 stored bars are unadjusted, and a split would look like a crash (flagged in
the report, never silently removed). The `ml_experiments/tests` folder is outside the existing
`tests/` folder, so `python -m pytest` in `backend/` still collects exactly the same tests as
before (and does not need scikit-learn).

## 6. Risks and how they are handled

| Risk | Handling |
| --- | --- |
| Experimental output mistaken for advice or a score | Offline only; every report has `experimental: true` and a notice; no API/UI; tested that the reports contain no buy/sell/hold language and that `app/` never imports the package |
| Inventing accuracy | No number without enough labelled data; sentiment has none; the volatility result is stated as one dataset only |
| Look-ahead / leakage (the classic way to fake good results) | Purge gap, past-only features, out-of-fold predictions, de-duplication, group splits - each guarded by a test that fails when the safeguard is removed (8 planted faults, all caught) |
| Overfitting through repeated tweaking | Fixed settings, no tuning, one seed; changing them should be a deliberate, recorded decision |
| Overlapping windows inflate confidence | Moving-block bootstrap intervals |
| Small, unrepresentative data | Minimum sizes, `limitations` in every report, this document |
| Unsafe model files | Models are never saved; no pickle/joblib (source-scan test) |
| Data leaving the machine / paid services | None used; no network code in the package (source-scan test) |
| Silent replacement of deterministic results | Not possible: nothing reads the experiment output |
| Dependency drift | Optional, separately pinned; the core install is unchanged |

## 7. Limitations and what was NOT verified

* Experiment A used one stock and one period; it generalises to nothing.
* Experiment B has never been run on real labelled text.
* The Phase 1-12 backend suite (`python -m pytest`) was **not run** by me: the sandbox has no
  FastAPI/SQLAlchemy and no network. You reported it passing for Phase 12 locally. I changed
  `current_phase` to 13 (`config.py`, `tests/test_health.py`), so run it once to confirm.
* The frontend was not touched. `npm test` was re-run after my changes (24/24 pass); the 40-step browser test, `npm run build` and the dashboard against the real backend were not re-run.
* Only the 18 harness tests were run, on Python 3.12 / scikit-learn 1.8.0, via `unittest`
  (they are also valid under pytest, which was not installed here).
* The matplotlib sample file's provenance is Yahoo Finance data bundled by matplotlib; check
  its terms before reusing it beyond a private demonstration.
