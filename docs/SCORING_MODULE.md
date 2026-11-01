# Scoring module (Phase 10 — verified complete, 2026-10-29)

Combines the results of Phases 5, 7, 8 and 9 into **one explainable 0–100
summary score per symbol**, with every number traceable to the inputs that
produced it. Deterministic arithmetic only: no LLM, no model, no randomness, no
new dependency, no network access, no new external data.

> **What this score is — and is not.**
> It is a transparent summary of how a few already-computed indicators sit
> against **fixed reference ranges that I chose**. It is **not investment
> advice, not a recommendation to buy, sell or hold anything, and not a
> forecast**. It carries no rating, band, grade or signal — by design there is
> no "good/bad stock" label anywhere in the result.
>
> **It has not been validated.** The reference ranges are illustrative round
> numbers, not calibrated on data, industries or market regimes, and the score
> has not been backtested against any outcome. A higher score means only "the
> measured indicators are nearer the end of the ranges this method treats as
> favourable" — and "favourable" encodes design assumptions (below).

The narrative What–How–Why explanation of a score is **Phase 11** (see
`EXPLANATION_MODULE.md`). Phase 10 itself produces the *structured* explanation
(inputs, anchors, sub-scores, weights, contributions, missing-data reasons,
limits) that Phase 11 phrases; it does not generate prose.

## The method

1. **Indicator → sub-score (0–100).** Each indicator has a "poor" and a "good" anchor. `sub = 100 × clamp((value − poor) / (good − poor), 0, 1)`: poor→0, good→100, straight line between, flat beyond. If `poor > good` lower is better. A value beyond an anchor is flagged `saturated` so you can see it was clipped.
2. **Component score.** The equal-weight mean of the component's *available* indicator sub-scores.
3. **Overall score.** `Σ (effective weight × component score)` over the contributing components, where `effective weight = configured weight ÷ sum of configured weights of the contributing components`. The overall score is computed *as the sum of the contributions*, so the contributions add up to it exactly.

### Inputs, anchors and the assumptions they encode

| Component | Source (stored result, used exactly as stored) | Indicator | Poor → Good | Needs |
| --- | --- | --- | --- | --- |
| Fundamentals | Phase 5, for a file you name; latest period for the symbol | net profit margin | 0 → 0.20 | ≥ 2 of 3 |
| | | debt to equity | 2.0 → 0.5 | |
| | | liabilities to assets | 0.9 → 0.4 | |
| Technical | Phase 7, latest bar | close vs 50-day average (`close/SMA50 − 1`) | −0.10 → +0.10 | ≥ 1 of 2 |
| | | close vs 200-day average | −0.15 → +0.15 | |
| Sentiment | Phase 8, latest complete result | mean headline sentiment | −0.5 → +0.5 | ≥ 5 texts that carried a signal |
| Risk | Phase 9, latest complete result | annualized volatility | 0.60 → 0.15 | ≥ 2 of 3 |
| | | maximum drawdown | −0.50 → −0.10 | |
| | | historical VaR (95%) | −0.05 → −0.01 | |

The assumptions that "favourable" encodes: higher margins and lower leverage are preferred; price above its moving averages is preferred; positive sentiment is preferred; lower volatility, shallower drawdowns and smaller bad-day losses are preferred. These are **choices, not findings**; a different investor objective would justify different anchors. The anchors, thresholds and limits live in one file (`backend/app/services/scoring_config.py`), are returned by `GET /api/scoring-method`, and a **snapshot is stored with every result**, so an old score stays reproducible if the configuration changes (bump `SCORING_VERSION` when it does).

**Left out on purpose (and said so in the output):** return on assets/equity and growth rates (their size depends on whether rows are annual or quarterly, which the data does not state); RSI and other oscillators (mapping them to "favourable" needs an overbought/oversold judgement this project deliberately does not make); beta and correlation (they depend entirely on the benchmark chosen).

## Missing-data handling

- **A missing indicator is excluded** and the component's remaining indicators are re-weighted equally. It is **never filled in, defaulted, or treated as 0 or 50**; the indicator row records the reason (e.g. `Needs at least 200 bars; 60 available.`).
- **A component** needs its minimum number of indicators (above), otherwise it is `UNAVAILABLE` with the reason, and its weight is redistributed.
- **The overall score** needs **at least 2 contributing components and at least 50% of the configured weight**; otherwise `overall.score` is `null` with the reason. These two thresholds are my judgement, not statistical standards. `weight_coverage` and `contributing_components` are always reported.
- **A weight of 0** shows a component but excludes it from the score.
- **Older periods are never substituted.** If the latest period lacks a metric, that input is missing even if an earlier period has it.
- **A score built from fewer components is not comparable to one built from more** (or with different weights). Compare two symbols only if `contributing_components` and `weights` match.

### Which data is used

- Technical / sentiment / risk: the **latest COMPLETE** result for the symbol (a newer failed run does not hide good data).
- Fundamentals: the latest complete Phase 5 result for the `file_id` you pass. If the file has several analysed worksheets you must pass `sheet_name`. Rows are matched to the symbol by a **`ticker` column** (case-insensitive); a `company` column is accepted only if the worksheet holds a single company, because company names cannot be matched to tickers. The **latest period** is the row with the greatest parseable date (dates are read month-first when ambiguous, as in Phase 5); with no date column it is the last row in the file. If several rows share the latest date, the period is **ambiguous and refused**, not guessed.
- Inputs can be from different dates or price snapshots. Each component reports `as_of`; the result **warns** when the technical and risk inputs come from different market-data snapshots, when as-of dates differ, and when any input carries a warning (for example Phase 9's possible-stock-split warning, which is passed through unchanged — the value is used as stored). Nothing is reconciled or age-discounted.

## Weights

Default: **equal (25% each)** — a no-information prior chosen because no data supports any other split, **not** evidence that the components matter equally. You may pass your own (`weights` for all four components; non-negative, finite, not all zero; normalised to sum to 1). The weights used are stored and `weights_customised` is set. Changing the weights changes the score by exactly the amounts shown, which is also a reminder that the weights are assumptions.

## API

- `GET /api/scoring-method` — the full method (components, indicators, anchors, default weights, formulas, rules, limits). Needs no data.
- `POST /api/scores/{symbol}` — optional JSON body `{"file_id": "...", "sheet_name": "...", "weights": {"fundamental":1,"technical":1,"sentiment":1,"risk":1}}`. 201 in every run outcome; a missing input is excluded and explained (not an error); an unexpected failure is `status: FAILED`, `SCORING_FAILURE`. 400 `INVALID_SYMBOL`, `INVALID_WEIGHTS`, `SHEET_WITHOUT_FILE`; 404 `FILE_NOT_FOUND`; 422 for a malformed body.
- `GET /api/scores/{symbol}` — latest score (successful or not); 404 `SCORE_RESULT_NOT_FOUND`.

Result: `id`, `symbol`, `file_id`, `sheet_name`, `status`, `created_at`, `scoring_version`, `notice`, `weights`, `weights_customised`, `overall` (`score`, `reason`, `weight_coverage`, `contributing_components`, `excluded_components`), `components[]` (each with `status`, `reason`, `score`, `as_of`, `source_ref` — the ids of the upstream results used —, `warnings`, `weight_configured`, `weight_effective`, `contribution_to_overall`, and `indicators[]` with `value`, `poor`, `good`, `direction`, `sub_score`, `saturated`, `weight_in_component`, `contribution_to_component`, `reason`), `warnings[]`, and the `method` snapshot (including `limits`). Results are stored inline; there are no file artifacts.

## Verification

Three kinds of evidence: (1) hand-computed worked examples (e.g. fundamentals (50+50+0)/3, overall 58.33 with all four components and 61.11 with one missing); (2) an **independent oracle** written in the test file (a few lines of plain maths that share no code with the engine) agreeing with the engine on 400 seeded random input sets, with random missing indicators, missing components and random weights, and — through the real pipeline — recomputing a full score from the raw upstream numbers to 1e-9; (3) properties: sub-scores and the overall score stay within 0–100, improving a favourable input never lowers the score, contributions add up to the score exactly. **Thirteen deliberate breakages were each caught** (missing indicator dragging the mean down, no weight renormalisation, no clamping, lowered overall thresholds, file-order instead of date-order, ticker matching ignored, ambiguous period resolved silently, sentiment accepted from one text, risk warnings dropped, an anchor direction swapped, a failed run replacing a complete one, a silent worksheet choice).

My own first-draft suite passed on its first run, which I treated as a warning rather than a result: reviewing it found two weak assertions (one vacuous, `… is False or True`, one too lenient), both replaced before the mutation runs.

**What the tests do not show:** that the score is meaningful. They prove it is computed exactly as documented and fully explainable; they say nothing about whether the anchors or weights are sensible, because that cannot be tested without outcome data this project does not have.

## Tests

`backend/tests/test_scores.py` (82 tests, no network): configuration integrity and stated limits; normalisation (hand examples, saturation, monotonicity); weights (normalisation, 10 invalid forms); components and overall (worked example, contributions summing exactly, equal indicator weights, missing indicators and components, minimums, thresholds including the exact-50% boundary, zero weights, weight what-if); engine vs oracle and properties on random inputs; the real pipeline end to end (traceability to upstream ids, method snapshot, no ratings/labels/recommendation keys or vocabulary, upstream data unmodified); fundamentals row/symbol/period rules (date vs file order, per-ticker rows, single vs many companies, ambiguity, no back-filling, worksheet choice, unanalysed and PDF files); technical/sentiment/risk inputs (short history, thin sentiment, low coverage, split warnings passed through, failed later runs ignored, per-symbol inputs); missing components, snapshot and date warnings; custom and invalid weights; request validation and 400/404/422 paths; unexpected-error and database-failure handling.

## Known limitations

- **The anchors and thresholds are unvalidated judgement** (see the top of this document). The score can rank two symbols only as well as those judgements deserve.
- Anchors ignore industry, size and market regime; one fixed set is applied to everything.
- Four equally weighted components is a convention. The weights are yours to change, which also means the score can be made to say almost anything.
- Fundamentals need an uploaded file with a ticker column (or a single company) and are only as good as that file.
- Inputs are never age-discounted; a stale sentiment or fundamentals result is used as-is (its date is reported).
- Inherits every earlier phase's limits: prices are unadjusted for splits and dividends; sentiment accuracy has never been measured; live price and news data have never been fetched in testing; indicators describe the past only.
- No history of scores, no comparison across symbols, no portfolio view, no score-history view (the Phase 12 dashboard shows only the latest score).
