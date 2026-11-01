# Explanation module (Phase 11)

`GET /api/scores/{symbol}/explanation` returns a **What / How / Why**
explanation of the latest COMPLETE score for a symbol.

## What it is — and is not

- **Deterministic and template-based.** Every sentence is produced by a fixed
  template from fields already stored in the Phase 10 score. There is **no LLM**
  and no new dependency. The explanation therefore cannot contain a number or a
  claim the score does not contain.
- **Derived on demand, not stored.** The score already carries its inputs,
  weights, source-result ids and a snapshot of the method, so the explanation is
  always consistent with it. `GET` has no side effects (a test checks that no
  score rows are created).
- **Not advice.** It describes a method and its arithmetic. It does not grade
  the score, call anything good or bad, or suggest any action. A test scans the
  What/How/Why text for advice/rating wording (buy, sell, hold, recommend,
  should, attractive, undervalued, bullish, strong, weak, ...). The fixed
  disclaimer and limits are passed through from the stored score.

## Response shape

`template_version`, `symbol`, `score_id`, `scoring_version`,
`score_created_at`, `notice`, `warnings`, and three sections:

- **`what`** — `summary` (the score, components used, weight coverage, or a plain
  statement that no overall score was produced and why), `overall_score`,
  `weight_coverage`, `contributing_components`, `excluded_components`, and one
  `sentence` per component.
- **`how`** — the five method `steps`; per component its source, weights,
  contribution and a `sentence` per indicator (value, anchors, direction,
  sub-score, weight, capping at an anchor, or why it was not used); and
  `arithmetic_check`.
- **`why`** — `largest_contributors` and `largest_point_losses` (top 3 by exact
  points), `accounting` (overall = 100 − points lost), `why_these_indicators`
  (definition of each indicator and what was deliberately left out),
  `missing_or_excluded`, `assumptions`, and `limits` (from the stored method
  snapshot).

## The arithmetic cross-check

`how.arithmetic_check` re-derives the overall score from the indicator rows and
effective weights only (not from the stored component scores or contributions)
and compares it with the stored overall score (tolerance 1e-6 points). If they
differ, `matches` is `false` and the sentence says the score should be treated
as unreliable. A mismatch is shown, never hidden.

"Points" for an indicator = sub-score × weight inside its component × effective
component weight. These add up to the overall score; the shortfall from 100 is
the sum of (100 − sub-score) × the same weights.

## Errors

| Status | Code | When |
|---|---|---|
| 404 | `SCORE_RESULT_NOT_FOUND` | the symbol has never been scored |
| 409 | `SCORE_NOT_COMPLETE` | the latest score run FAILED (nothing to explain; error details are not echoed) |
| 400 | `INVALID_SYMBOL` | malformed symbol |

## Limits

- It explains the **method**, not the **meaning**: it inherits every limit of
  Phase 10 (illustrative anchors, design assumptions behind "favourable", no
  backtest) and of the input phases (unadjusted prices, unmeasured sentiment
  accuracy, live data never fetched).
- English only; one fixed wording per situation. It explains the *latest* score
  only (no `score_id` selector yet).
- "Largest contributors / losses" describe arithmetic, not importance or causes.
- The Phase 12 dashboard shows it on its Explain page; there is no history or comparison view.

## Verification status (honest)

- `tests/test_explanation_builder.py` (14 tests, standard library only) was
  **run and passed** in the authoring sandbox. It covers hand-computed values,
  an independent re-derivation on 300 seeded random inputs, a tampered score
  being flagged, determinism/no mutation, the wording guard, and the
  unavailable-component case (a real crash found by the random test and fixed).
  Five deliberate breakages (wrong weight in the cross-check, loss formula,
  ranking order, tolerance, advice wording) were each caught.
- `tests/test_explanation.py` (9 API tests) was written against Phase 10's
  helpers but **has not been executed**: the authoring sandbox had no network,
  so FastAPI/SQLAlchemy/pytest could not be installed. Run
  `python -m pytest` in `backend/` before relying on the endpoint.
