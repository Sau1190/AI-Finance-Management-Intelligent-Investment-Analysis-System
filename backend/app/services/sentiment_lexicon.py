"""Starter finance sentiment lexicon (plain data, versioned, editable).

This is a small, hand-written word list — NOT a validated research lexicon and
not tuned on labelled data. Its value is transparency: every sentiment score
the system produces can be traced to specific entries here. Known weaknesses
are listed in docs/SENTIMENT_MODULE.md (no context, sarcasm, or entity
targeting; words like "rise" are positive even in "rising costs").

Rules for editing:
  * Keys are lowercase. Weights are +/-1 (normal) or +/-2 (strong).
  * A word may appear in one polarity only.
  * Generic words that carry no polarity on their own ("risk", "cut", "up",
    "record", "debt", "dividend", "short") are deliberately absent; where the
    polarity depends on the next word they appear only inside PHRASES.
  * Inflections are listed explicitly — no stemming or fuzzy matching.
  * Bump LEXICON_VERSION on every change; results store the version they used.
"""

LEXICON_VERSION = "1"

POSITIVE_STRONG = (
    "surge surges surged soar soars soared skyrocket skyrockets skyrocketed "
    "breakthrough outperform outperforms outperformed blowout"
).split()

POSITIVE = (
    "gain gains gained rise rises rose rising higher growth grow grows grew growing "
    "profit profits profitable beat beats rally rallies rallied strong stronger strongest "
    "improve improves improved improvement upgrade upgrades upgraded expansion expands expanded "
    "recover recovers recovered recovery boost boosts boosted success successful successfully "
    "positive increase increases increased approval approved approves win wins won "
    "exceed exceeds exceeded optimistic optimism resilient resilience momentum "
    "jump jumps jumped climb climbs climbed advance advances advanced upbeat bullish "
    "confident confidence opportunity opportunities innovative innovation "
    "partnership partnerships award awarded secures secured "
    "good better best great excellent favorable favourable solid healthy robust"
).split()

NEGATIVE_STRONG = (
    "bankruptcy bankrupt fraud fraudulent plunge plunges plunged plummet plummets plummeted "
    "collapse collapses collapsed crash crashes crashed scandal default defaults defaulted "
    "insolvency insolvent embezzlement delisting delisted"
).split()

NEGATIVE = (
    "loss losses lost lose loses fall falls fell falling drop drops dropped "
    "decline declines declined declining lower weak weaker weakness miss misses missed "
    "downgrade downgrades downgraded underperform underperforms underperformed "
    "lawsuit lawsuits sued sues investigation investigations probe recall recalls recalled "
    "layoff layoffs slump slumps slumped tumble tumbles tumbled concern concerns "
    "warning warns warned shortfall deficit struggle struggles struggling "
    "penalty penalties crisis bearish delay delays delayed halt halted suspend suspended "
    "selloff sell-off slowdown slows slowed shrink shrinks shrank negative "
    "decrease decreases decreased unprofitable worse worst pessimistic disappointing "
    "disappoint disappoints disappointed uncertainty headwind headwinds fear fears "
    "fined breach breaches hack hacked outage outages "
    "bad poor poorly terrible unfavorable unfavourable troubled trouble damage damaged "
    "harm harmed failure failures fail fails failed"
).split()

# Multi-word expressions, matched before single words (longest first). Tokens
# are lowercase; hyphenated words are single tokens ("all-time").
PHRASES: dict[tuple[str, ...], int] = {
    ("beat", "expectations"): 2, ("beats", "expectations"): 2,
    ("beat", "estimates"): 2, ("beats", "estimates"): 2,
    ("exceeds", "expectations"): 2, ("exceeded", "expectations"): 2,
    ("raises", "guidance"): 2, ("raised", "guidance"): 2,
    ("raises", "outlook"): 2, ("raised", "outlook"): 2,
    ("record", "high"): 2, ("record", "highs"): 2,
    ("all-time", "high"): 2, ("all-time", "highs"): 2,
    ("record", "profit"): 2, ("record", "profits"): 2,
    ("record", "revenue"): 2, ("record", "earnings"): 2,
    ("price", "target", "raised"): 1, ("raises", "dividend"): 1, ("share", "buyback"): 1,
    ("miss", "expectations"): -2, ("misses", "expectations"): -2, ("missed", "expectations"): -2,
    ("miss", "estimates"): -2, ("misses", "estimates"): -2, ("missed", "estimates"): -2,
    ("profit", "warning"): -2, ("going", "concern"): -2,
    ("lowers", "guidance"): -2, ("lowered", "guidance"): -2,
    ("cuts", "guidance"): -2, ("cut", "guidance"): -2,
    ("cuts", "outlook"): -2, ("cut", "outlook"): -2,
    ("record", "low"): -2, ("record", "lows"): -2,
    ("all-time", "low"): -2, ("all-time", "lows"): -2,
    ("record", "loss"): -2, ("record", "losses"): -2,
    ("price", "target", "cut"): -1, ("job", "cuts"): -1, ("data", "breach"): -2,
}

NEGATORS = frozenset(
    {"not", "no", "never", "without", "neither", "nor", "cannot", "hardly", "barely"}
)


def build_word_weights() -> dict[str, int]:
    weights: dict[str, int] = {}
    for words, weight in (
        (POSITIVE_STRONG, 2), (POSITIVE, 1), (NEGATIVE_STRONG, -2), (NEGATIVE, -1),
    ):
        for word in words:
            weights[word] = weight
    return weights


WORD_WEIGHTS: dict[str, int] = build_word_weights()
