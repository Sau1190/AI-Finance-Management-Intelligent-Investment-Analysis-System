"""Deterministic, explainable sentiment scoring.

Beginner view:
  Look through a text for known positive and negative words and phrases, add
  up their strength, and report the balance — together with the exact words
  that were found, so the score can always be explained.

Technical view:
  Pure functions, no I/O, no randomness, no model. For one text:
    1. Split into sentences on . ! ? ; : and newlines (negation never crosses
       a sentence boundary).
    2. Tokenize to lowercase words (apostrophes and hyphens kept inside a
       word: "didn't", "sell-off").
    3. Match PHRASES first (longest first), then single words; a token is used
       at most once.
    4. A term is NEGATED if a negator ("not", "no", "never", any "...n't"
       contraction, ...) appears within the 3 tokens before it; a negated term
       contributes with the opposite sign and the same strength.
    5. P = sum of positive contributions, N = sum of negative contributions
       (as positive numbers). evidence = P + N.
       score = (P - N) / (P + N), in [-1, 1].
       A text with no matched term has score None and label "no_signal" — the
       absence of evidence is NOT reported as neutral.
    6. label: score >= +0.05 positive, <= -0.05 negative, otherwise neutral
       (the same +/-0.05 convention VADER uses; it is a convention, not a
       calibrated threshold).

  What this cannot do: understand context (rising costs), sarcasm, who the
  sentence is about, or any language other than English. Accuracy has NOT been
  measured against labelled data.
"""

import re
from statistics import fmean

from app.services import sentiment_lexicon as lex

POSITIVE_THRESHOLD = 0.05
NEGATIVE_THRESHOLD = -0.05
NEGATION_WINDOW = 3
MAX_TEXT_CHARS = 2000

_SENTENCE_SPLIT = re.compile(r"[.!?;:\n]+")
_TOKEN = re.compile(r"[a-z]+(?:[-'][a-z]+)*")


def tokenize(sentence: str) -> list[str]:
    return _TOKEN.findall(sentence.lower().replace("\u2019", "'").replace("\u2018", "'"))


def _is_negator(token: str, negators: frozenset[str]) -> bool:
    return token in negators or token.endswith("n't")


def label_for(score: float | None) -> str:
    if score is None:
        return "no_signal"
    if score >= POSITIVE_THRESHOLD:
        return "positive"
    if score <= NEGATIVE_THRESHOLD:
        return "negative"
    return "neutral"


def score_text(
    text: str,
    *,
    words: dict[str, int] | None = None,
    phrases: dict[tuple[str, ...], int] | None = None,
    negators: frozenset[str] | None = None,
) -> dict:
    """Score one text. Returns a dict with: score, label, positive, negative,
    evidence, matches[]. Each match: term, weight (as written in the lexicon),
    negated, contribution (signed, after negation).
    """
    words = lex.WORD_WEIGHTS if words is None else words
    phrases = lex.PHRASES if phrases is None else phrases
    negators = lex.NEGATORS if negators is None else negators
    phrase_lengths = sorted({len(p) for p in phrases}, reverse=True)

    matches: list[dict] = []
    for sentence in _SENTENCE_SPLIT.split(text[:MAX_TEXT_CHARS]):
        tokens = tokenize(sentence)
        used = [False] * len(tokens)
        found: list[tuple[int, str, int]] = []  # (start index, term, weight)

        for length in phrase_lengths:
            for i in range(len(tokens) - length + 1):
                if any(used[i : i + length]):
                    continue
                key = tuple(tokens[i : i + length])
                if key in phrases:
                    found.append((i, " ".join(key), phrases[key]))
                    for j in range(i, i + length):
                        used[j] = True
        for i, token in enumerate(tokens):
            if not used[i] and token in words:
                found.append((i, token, words[token]))
                used[i] = True

        for start, term, weight in sorted(found):
            window = tokens[max(0, start - NEGATION_WINDOW) : start]
            negated = any(_is_negator(t, negators) for t in window)
            matches.append(
                {
                    "term": term,
                    "weight": weight,
                    "negated": negated,
                    "contribution": -weight if negated else weight,
                }
            )

    positive = float(sum(m["contribution"] for m in matches if m["contribution"] > 0))
    negative = float(-sum(m["contribution"] for m in matches if m["contribution"] < 0))
    evidence = positive + negative
    score = (positive - negative) / evidence if evidence > 0 else None
    return {
        "score": score,
        "label": label_for(score),
        "positive": positive,
        "negative": negative,
        "evidence": evidence,
        "matches": matches,
    }


def normalize_for_dedup(text: str) -> str:
    return " ".join(text.lower().split())


def aggregate(scored: list[dict]) -> dict:
    """Summarize per-text results. The mean is over texts that carried a
    signal only (equal weight per text — no recency or source weighting);
    coverage says what fraction that was.
    """
    counts = {"positive": 0, "negative": 0, "neutral": 0, "no_signal": 0}
    for item in scored:
        counts[item["label"]] += 1
    with_signal = [item["score"] for item in scored if item["score"] is not None]
    mean_score = float(fmean(with_signal)) if with_signal else None
    return {
        "text_count": len(scored),
        "scored_count": len(with_signal),
        "counts": counts,
        "coverage": (len(with_signal) / len(scored)) if scored else None,
        "mean_score": mean_score,
        "label": label_for(mean_score),
    }
