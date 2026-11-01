"""The scoring method as plain, versioned data.

Everything that decides a score — which indicators are used, the reference
anchors, the default weights, the missing-data thresholds, and the stated
limits — lives here, in one place a reader can inspect and change. The same
data is returned by GET /api/scoring-method and a snapshot of it is stored with
every result, so a stored score can always be reproduced and explained even if
this file is edited later (bump SCORING_VERSION when you do).

IMPORTANT — what these numbers are and are not:
  * The anchors ("poor" / "good") are ILLUSTRATIVE ROUND NUMBERS chosen for
    readability. They are not calibrated on market data, not specific to any
    industry or market regime, and not backed by a backtest. The same ratio can
    be unremarkable in one sector and alarming in another.
  * "Good" means "the end of the range this method treats as favourable". That
    encodes assumptions (e.g. lower volatility and shallower drawdowns are
    preferred, positive sentiment is preferred, price above its moving average
    is preferred). They are design choices, not findings.
  * Equal weights are a no-information default, not evidence that the four
    components matter equally.
  * The result is an educational summary. It is not investment advice, not a
    recommendation to buy, sell, or hold anything, and not a forecast.
"""

SCORING_VERSION = "1"

COMPONENT_ORDER = ("fundamental", "technical", "sentiment", "risk")

DEFAULT_WEIGHTS: dict[str, float] = {key: 1.0 / len(COMPONENT_ORDER) for key in COMPONENT_ORDER}

# The overall score is only reported when enough of the picture is present.
MIN_COMPONENTS_FOR_OVERALL = 2
MIN_WEIGHT_COVERAGE_FOR_OVERALL = 0.5

# A sentiment mean over fewer scored texts is too thin to use.
MIN_SENTIMENT_SCORED_TEXTS = 5

# Each indicator: key, label, where it comes from, and the two anchors.
# sub_score = 100 * clamp((value - poor) / (good - poor), 0, 1)
# so value == poor -> 0, value == good -> 100, linear in between, flat beyond.
# poor > good means "lower is better"; poor < good means "higher is better".
COMPONENTS: dict[str, dict] = {
    "fundamental": {
        "label": "Fundamentals",
        "source": "Phase 5 fundamental analysis of an uploaded file (latest period for the symbol)",
        "min_indicators": 2,
        "indicators": [
            {"key": "net_profit_margin", "label": "Net profit margin", "poor": 0.0, "good": 0.20,
             "unit": "ratio", "note": "net income / revenue of the latest period"},
            {"key": "debt_to_equity", "label": "Debt to equity", "poor": 2.0, "good": 0.5,
             "unit": "ratio", "note": "debt / equity of the latest period"},
            {"key": "liabilities_to_assets", "label": "Liabilities to assets", "poor": 0.9, "good": 0.4,
             "unit": "ratio", "note": "liabilities / assets of the latest period"},
        ],
        "excluded_on_purpose": (
            "Return on assets/equity and growth rates are not used: their size depends on whether a row is an "
            "annual or a quarterly period, which the uploaded data does not state."
        ),
    },
    "technical": {
        "label": "Technical (trend position)",
        "source": "Phase 7 technical analysis of the symbol's stored prices (latest bar)",
        "min_indicators": 1,
        "indicators": [
            {"key": "price_vs_sma_50", "label": "Close vs 50-day average", "poor": -0.10, "good": 0.10,
             "unit": "fraction", "note": "close / SMA(50) - 1"},
            {"key": "price_vs_sma_200", "label": "Close vs 200-day average", "poor": -0.15, "good": 0.15,
             "unit": "fraction", "note": "close / SMA(200) - 1 (needs 200 bars: fetch market data with history=full)"},
        ],
        "excluded_on_purpose": (
            "Oscillators such as RSI are not used: mapping them to 'favourable' needs a judgement about "
            "overbought/oversold that this project deliberately does not make."
        ),
    },
    "sentiment": {
        "label": "Sentiment",
        "source": "Phase 8 sentiment analysis of the symbol (latest complete result)",
        "min_indicators": 1,
        "indicators": [
            {"key": "sentiment_mean", "label": "Mean headline sentiment", "poor": -0.5, "good": 0.5,
             "unit": "score -1..1", "note": f"needs at least {MIN_SENTIMENT_SCORED_TEXTS} texts that carried a signal"},
        ],
        "excluded_on_purpose": None,
    },
    "risk": {
        "label": "Risk (realised)",
        "source": "Phase 9 risk analysis of the symbol's stored prices (latest complete result)",
        "min_indicators": 2,
        "indicators": [
            {"key": "annualized_volatility", "label": "Annualized volatility", "poor": 0.60, "good": 0.15,
             "unit": "fraction", "note": "lower volatility is treated as favourable"},
            {"key": "max_drawdown", "label": "Maximum drawdown", "poor": -0.50, "good": -0.10,
             "unit": "fraction", "note": "a shallower worst fall is treated as favourable"},
            {"key": "historical_var_95", "label": "Historical VaR (95%)", "poor": -0.05, "good": -0.01,
             "unit": "fraction", "note": "a smaller bad-day loss is treated as favourable"},
        ],
        "excluded_on_purpose": (
            "Beta and correlation are not used: they depend entirely on the benchmark chosen, and a neutral "
            "'good' value for them cannot be defined without an investment objective."
        ),
    },
}

FORMULAS = [
    "indicator sub-score = 100 * clamp((value - poor) / (good - poor), 0, 1)",
    "component score = weighted mean of its available indicator sub-scores (equal weights among those available)",
    "effective component weight = configured weight / sum of configured weights of the components that contribute",
    "overall score = sum over contributing components of (effective weight * component score)",
]

RULES = [
    f"An indicator that is missing is excluded and the remaining indicators of that component are re-weighted; "
    "it is never filled in, defaulted, or treated as 0 or 50.",
    "A component needs at least its stated minimum number of available indicators, otherwise it is unavailable.",
    f"The overall score needs at least {MIN_COMPONENTS_FOR_OVERALL} contributing components and at least "
    f"{MIN_WEIGHT_COVERAGE_FOR_OVERALL:.0%} of the configured weight; otherwise it is null with the reason.",
    "A component with weight 0 is shown but does not contribute.",
    "Values are taken from the stored results of earlier phases exactly as stored; nothing is recomputed or repaired.",
    "Only the latest complete result of each phase is used; the date each input is as-of is reported and no "
    "age-based discounting is applied.",
]

LIMITS = [
    "This is an educational summary, not investment advice. It does not recommend buying, selling, or holding "
    "anything and says nothing about future returns.",
    "The reference anchors are illustrative round numbers, not calibrated on data, industries, or market regimes; "
    "the same ratio can be ordinary in one sector and alarming in another.",
    "'Favourable' encodes design assumptions (for example, lower volatility is preferred). They are choices, "
    "not findings, and a different investor objective would justify different anchors.",
    "Equal weights are a no-information default, not evidence that the components matter equally. Changing the "
    "weights changes the score by exactly the amounts shown.",
    "The score has not been backtested or validated against outcomes; no predictive power is claimed.",
    "A score built from fewer components or indicators is less informative; always read the reported coverage.",
    "The score inherits the limits of every input phase: prices are unadjusted for splits and dividends, sentiment "
    "accuracy has not been measured, fundamentals are only as good as the uploaded file, and live market and news "
    "data have never been fetched in testing.",
    "Inputs can come from different dates or different price snapshots; their as-of dates are reported but not "
    "reconciled.",
]

NOTICE = (
    "Educational use only. Not investment advice, not a recommendation, not a forecast. "
    "See `limits` for how to read this score."
)


def describe_method(configured_weights: dict[str, float] | None = None) -> dict:
    """The complete, human-readable description of the method (also stored,
    as a snapshot, with every result).
    """
    return {
        "scoring_version": SCORING_VERSION,
        "notice": NOTICE,
        "default_weights": dict(DEFAULT_WEIGHTS),
        "configured_weights": dict(configured_weights) if configured_weights is not None else dict(DEFAULT_WEIGHTS),
        "min_components_for_overall": MIN_COMPONENTS_FOR_OVERALL,
        "min_weight_coverage_for_overall": MIN_WEIGHT_COVERAGE_FOR_OVERALL,
        "min_sentiment_scored_texts": MIN_SENTIMENT_SCORED_TEXTS,
        "components": {key: COMPONENTS[key] for key in COMPONENT_ORDER},
        "formulas": list(FORMULAS),
        "rules": list(RULES),
        "limits": list(LIMITS),
    }
