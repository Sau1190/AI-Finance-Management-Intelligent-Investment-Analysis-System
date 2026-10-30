# Sentiment module (Phase 8 — verified complete, 2026-10-24)

Scores the sentiment of financial headlines/text with a **deterministic,
explainable word-list method**. Every score can be traced to the exact words
and phrases that produced it. No LLM, no machine-learning model, no new
dependency (ML sentiment is Phase 13; LLM wording of explanations is Phase 11).

> **Read this before trusting the numbers.**
> 1. **Accuracy has not been measured.** The word list is a small, hand-written
>    starter list (251 words, 44 phrases). It has not been validated against any
>    labelled financial dataset, and no accuracy figure is claimed. Treat results
>    as a transparent baseline, not as a trading signal.
> 2. **Live news fetching has never run.** The build environment has no outbound
>    access, so the NewsAPI adapter was tested only against a simulated transport
>    using the vendor's documented response shape. Do one real fetch with your
>    own key and read the returned headlines before relying on it.

## Method

For each text (title + description for news):
1. Split into sentences on `. ! ? ; :` and newlines.
2. Lowercase word tokens (apostrophes/hyphens kept inside words: `didn't`, `sell-off`).
3. Match **phrases first** (longest first, e.g. `beats expectations` = +2, `profit warning` = −2), then single words. Each token is used at most once.
4. A term is **negated** if a negator (`not no never without neither nor cannot hardly barely`, or any `…n't`) is within the 3 tokens before it. Negation flips the sign, keeps the strength, and is recorded on the match.
5. `P` = sum of positive contributions, `N` = sum of negative ones (as positives), `evidence = P + N`, **`score = (P − N) / (P + N)`** in [−1, 1].
6. Label: score ≥ +0.05 `positive`, ≤ −0.05 `negative`, else `neutral` (the ±0.05 convention VADER uses — a convention, not a calibrated threshold).

**No signal is not neutral.** A text with no lexicon term gets `score: null`, label `no_signal`. The aggregate reports `coverage` (the share of texts that carried any signal) so a "neutral" average over mostly-empty texts is visible as such.

**Aggregate:** `mean_score` is the plain mean over texts that carried a signal (equal weight per text; no recency or source weighting). **A neutral mean can hide disagreement** (one very positive and one very negative headline average to 0.0), so `counts` (positive/negative/neutral/no_signal) are always returned alongside it.

The word list is `app/services/sentiment_lexicon.py` — plain data, weights ±1 (normal) or ±2 (strong), versioned (`LEXICON_VERSION`). Results store the version used. Generic words whose polarity depends on context (`risk`, `cut`, `up`, `record`, `debt`, `dividend`, `short`) are deliberately absent; where they matter they appear only inside phrases.

## Input handling

- **Duplicates:** texts that are identical ignoring case and spacing (typically a syndicated headline) are counted once; the first occurrence is kept and `duplicates_removed` is reported. For news the headline is the dedup key.
- **Unusable articles** (no title, or NewsAPI's `[Removed]` placeholder) are skipped and counted in `skipped`, never scored.
- **Zero articles** is a successful empty result (`COMPLETE`, `mean_score: null`, label `no_signal`) — unlike Phase 6, "no news" is a legitimate answer, not a failure.
- Article fields are untrusted third-party data: URLs are kept only if they start with `http://`/`https://` and are ≤ 500 characters (so `javascript:` links are dropped); dates are parsed and normalised to UTC (unparseable → `null`); text is shown truncated to 300 characters (`text_truncated`) but scored up to 2000; nothing is rendered, executed, or used in file paths.

## API

- `POST /api/sentiment/{symbol}/text` — body `{"texts": ["…", …]}`, 1–100 texts, each 1–2000 characters after trimming. Needs no external service. Invalid bodies → 422 `INVALID_REQUEST`.
- `POST /api/sentiment/{symbol}/news?query=…` — fetches up to `NEWS_PAGE_SIZE` (default 50) recent English headlines (`searchIn=title,description`, newest first) and scores them. `query` defaults to the symbol; 1–100 printable characters (`INVALID_QUERY` otherwise). A provider problem is a 201 with `status: FAILED` and an `error_code`. **503 `NEWS_NOT_CONFIGURED`** if no key is set (nothing recorded; checked before input validation).
- `GET /api/sentiment/{symbol}?source=text|news` — the latest result for the symbol (optionally for one source); 404 `SENTIMENT_RESULT_NOT_FOUND`.
- 400 `INVALID_SYMBOL` everywhere for a bad symbol.

Symbols are only a label for submitted text; for news the default search is the ticker text, so **ambiguous tickers (e.g. `T`, `ON`, `A`) will match unrelated articles** — pass a company name as `query`. Results are not linked to uploaded files, Phase 5, or Phase 6.

Result: `id`, `symbol`, `source_type`, `provider`, `query`, `status`, `error_code`, `error_message`, `lexicon_version`, `received_count`, `duplicates_removed`, `skipped`, `text_count`, `scored_count`, `counts`, `coverage`, `mean_score`, `label`, `earliest_published`, `latest_published`, `items[]` (per text: `index`, `text`, `source`, `published_at`, `url`, `score`, `label`, `positive`, `negative`, `evidence`, `matches[]` with `term`, `weight`, `negated`, `contribution`). Results are stored inline in the database (no file artifacts).

## Security notes

- NewsAPI takes its key in the **`X-Api-Key` header**, so it is never in the URL (the Phase 6 provider puts its key in the URL; that is why Phase 6 needed log silencing). Errors still map to fixed messages with the underlying exception dropped, `httpx`/`httpcore` loggers are pinned to WARNING, redirects are not followed, responses are capped at 10 MB, requests time out.
- Tests assert the key is absent from the URL, responses, database rows, and logs at DEBUG, and that `NEWS_API_KEY` is blanked in `conftest.py` so tests never use a real key.
- Provider terms: NewsAPI's free developer plan is, as far as I recall, restricted to development/testing and delays articles — **check the current terms before any real use**; headlines are third-party content.

## Known limitations (all deliberate or unavoidable at this stage)

- **No context understanding:** "rising costs worry investors" scores positive (`rising`); a negator more than 3 tokens before a term is missed ("Not a single analyst expects growth" scores positive). Both are pinned by tests so any improvement is a conscious change.
- No sarcasm, no entity targeting (a headline about a competitor counts for the symbol), English only, no stemming (inflections are listed explicitly), no weighting by source or recency.
- Titles and descriptions are scored together, so a long description can outweigh a short headline.
- Small lexicon → low coverage on real news; check `coverage` and `scored_count`.
- No scheduling, history comparison, or caching; every fetch calls the provider (and uses quota).
- Not yet used by anything downstream (scoring is Phase 10).

## Tests

`backend/tests/test_sentiment.py` (108 tests, no network): scoring arithmetic with an injected tiny lexicon (balance formula, no-signal ≠ neutral, thresholds, negation window and sentence boundaries, contractions incl. curly apostrophes, phrase precedence/longest-first, truncation, determinism, native types); aggregation; lexicon integrity (no polarity conflicts or duplicates, every word and phrase reachable by the tokenizer); behaviour on unambiguous examples and the two documented limitations; the NewsAPI adapter (header-only key, request shape, 11 failure mappings, network errors without leakage, oversize, redirects, malformed articles, logging); the API (explainability, dedup, truncation, markup as plain data, 8 invalid-body cases, limits, symbols, news skipping/dedup/URL and date handling, queries, zero articles, provider failures, unexpected errors, unconfigured/unsupported provider, key never leaking, database failure, latest-by-source). Eight mutations (no-signal→neutral, wider negation window, negation across sentences, shortest-phrase-first, no dedup, key in URL, any URL scheme, no-signal counted as 0 in the mean) were each caught.
