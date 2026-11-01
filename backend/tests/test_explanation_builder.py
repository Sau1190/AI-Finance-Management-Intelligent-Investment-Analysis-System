"""Phase 11 - What-How-Why explanation builder (pure; stdlib only).

The builder only restates a stored score, so these tests establish: every
number in the text comes from the score, the explanation's accounting adds up
(checked against hand-computed values and an independent re-derivation), a
tampered score is flagged rather than explained away, and nothing reads as a
rating or advice. They do NOT establish that the score itself is meaningful.
"""

import copy
import math
import random
import re

from app.services import explanation_builder as eb
from app.services import scoring_config as cfg
from app.services import scoring_engine as se


def make_score(inputs: dict, weights: dict | None = None) -> dict:
    built = se.build_scores(inputs, weights)
    return {
        "id": "score-1", "symbol": "AAA", "scoring_version": cfg.SCORING_VERSION, "notice": cfg.NOTICE,
        "weights": built["weights"], "weights_customised": weights is not None,
        "overall": built["overall"], "components": built["components"], "warnings": [],
        "method": cfg.describe_method(built["weights"]), "created_at": "2025-01-10T00:00:00+00:00",
    }


FULL_INPUTS = {
    "fundamental": {"as_of": "2024-12-31", "values": {"net_profit_margin": 0.12, "debt_to_equity": None,
                    "liabilities_to_assets": 0.55}, "missing": {"debt_to_equity": "No debt column in the data."}},
    "technical": {"as_of": "2025-01-10", "values": {"price_vs_sma_50": 0.2, "price_vs_sma_200": None},
                  "missing": {"price_vs_sma_200": "Needs 200 bars; 100 available."}},
    "sentiment": {"unavailable_reason": "Only 2 texts carried a signal; at least 5 are needed."},
    "risk": {"as_of": "2025-01-10", "values": {"annualized_volatility": 0.3, "max_drawdown": -0.25,
             "historical_var_95": -0.02}},
}


def all_text(section: dict) -> str:
    out: list[str] = []

    def walk(x):
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, dict):
            for k, v in x.items():
                if k != "limits":
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(section)
    return "\n".join(out)


def test_hand_computed_overall_matches_explanation() -> None:
    # fundamentals (60+70)/2=65 ; technical capped at 100 ; risk (66.667+62.5+75)/3=68.0556
    # overall = (65+100+68.0556)/3 = 77.685185...
    e = eb.build_explanation(make_score(FULL_INPUTS))
    assert math.isclose(e["what"]["overall_score"], (65 + 100 + (200 / 3 + 62.5 + 75) / 3) / 3, abs_tol=1e-9)
    assert "77.7 out of 100" in e["what"]["summary"]
    assert "3 of 4 components" in e["what"]["summary"] and "75.0% of the configured weight" in e["what"]["summary"]


def test_indicator_sentences_carry_the_stored_numbers() -> None:
    e = eb.build_explanation(make_score(FULL_INPUTS))
    fund = next(c for c in e["how"]["components"] if c["key"] == "fundamental")
    npm = next(i for i in fund["indicators"] if i["key"] == "net_profit_margin")["sentence"]
    assert "0.12" in npm and "Sub-score 60.0" in npm and "0.00 to 0 and 0.20 to 100" in npm
    de = next(i for i in fund["indicators"] if i["key"] == "debt_to_equity")["sentence"]
    assert "not used" in de and "No debt column in the data." in de
    tech = next(c for c in e["how"]["components"] if c["key"] == "technical")
    sma = next(i for i in tech["indicators"] if i["key"] == "price_vs_sma_50")["sentence"]
    assert "20.0%" in sma and "capped at 100" in sma
    risk = next(c for c in e["how"]["components"] if c["key"] == "risk")
    assert "30.0%" in risk["indicators"][0]["sentence"] and "lower value is treated as more favourable" in risk["indicators"][0]["sentence"]


def test_unavailable_component_is_explained_with_its_stored_reason() -> None:
    e = eb.build_explanation(make_score(FULL_INPUTS))
    sent = next(c for c in e["what"]["components"] if c["key"] == "sentiment")
    assert sent["status"] == "UNAVAILABLE" and sent["score"] is None
    assert "at least 5 are needed" in sent["sentence"]
    assert any("Sentiment is not in the overall score" in m for m in e["why"]["missing_or_excluded"])
    assert any("Debt to equity was not used" in m for m in e["why"]["missing_or_excluded"])
    assert e["what"]["excluded_components"]["sentiment"].startswith("Only 2 texts")


def test_arithmetic_check_matches_and_accounting_adds_up() -> None:
    score = make_score(FULL_INPUTS)
    e = eb.build_explanation(score)
    check = e["how"]["arithmetic_check"]
    assert check["matches"] is True and check["difference"] < 1e-9
    assert "matches the stored" in check["sentence"]
    # contributions across all indicators add to the overall; lost points add to 100 - overall
    added = lost = 0.0
    for c in score["components"]:
        for i in c["indicators"]:
            pts = eb._indicator_points(c, i)
            if pts:
                added += pts[0]
                lost += pts[1]
    assert math.isclose(added, score["overall"]["score"], abs_tol=1e-9)
    assert math.isclose(100 - lost, score["overall"]["score"], abs_tol=1e-9)
    assert e["why"]["accounting"].startswith("Accounting: the overall score 77.7 = 100 - 22.3")


def test_a_tampered_score_is_flagged_not_explained_away() -> None:
    score = make_score(FULL_INPUTS)
    score["overall"]["score"] += 5.0
    e = eb.build_explanation(score)
    check = e["how"]["arithmetic_check"]
    assert check["matches"] is False and math.isclose(check["difference"], 5.0, abs_tol=1e-9)
    assert "Cross-check FAILED" in check["sentence"] and "unreliable" in check["sentence"]


def test_drivers_are_ranked_deterministically_from_the_points() -> None:
    e = eb.build_explanation(make_score(FULL_INPUTS))
    top = e["why"]["largest_contributors"]
    assert top[0]["indicator"] == "price_vs_sma_50" and math.isclose(top[0]["points"], 100 / 3, abs_tol=1e-9)
    assert [d["points"] for d in top] == sorted((d["points"] for d in top), reverse=True)
    loss = e["why"]["largest_point_losses"]
    assert loss[0]["indicator"] == "net_profit_margin" and math.isclose(loss[0]["points"], 40 * 0.5 / 3, abs_tol=1e-9)
    assert len(top) == 3 and len(loss) == 3


def test_no_overall_score_is_stated_plainly() -> None:
    only_one = {"technical": FULL_INPUTS["technical"], "risk": {"unavailable_reason": "No risk result."}}
    e = eb.build_explanation(make_score(only_one))
    assert e["what"]["overall_score"] is None
    assert "no overall score could be produced" in e["what"]["summary"]
    assert "Only 1 component(s) contributed" in e["what"]["summary"]
    assert e["why"]["accounting"] is None and e["why"]["largest_contributors"] == []
    assert e["how"]["arithmetic_check"]["matches"] is True
    assert "no arithmetic to check" in e["how"]["arithmetic_check"]["sentence"]


def test_custom_weights_and_zero_weight_components_are_described() -> None:
    w = {"fundamental": 2, "technical": 1, "sentiment": 1, "risk": 0}
    e = eb.build_explanation(make_score(FULL_INPUTS, w))
    assert "(custom)" in e["how"]["steps"][3]
    risk = next(c for c in e["how"]["components"] if c["key"] == "risk")
    assert "not part of the overall score" in risk["sentence"]
    fund = next(c for c in e["how"]["components"] if c["key"] == "fundamental")
    assert "effective weight 66.7%" in fund["sentence"]
    assert e["how"]["arithmetic_check"]["matches"] is True


def test_explanation_is_deterministic_and_does_not_mutate_its_input() -> None:
    score = make_score(FULL_INPUTS)
    before = copy.deepcopy(score)
    a, b = eb.build_explanation(score), eb.build_explanation(score)
    assert a == b and score == before


FORBIDDEN = re.compile(
    r"\b(buy|sell|hold|recommend\w*|should|attractive|undervalued|overvalued|outperform\w*|"
    r"upside|downside|bullish|bearish|safe|risky|strong|weak|excellent|poor stock)\b", re.I,
)


def test_text_contains_no_advice_or_rating_language() -> None:
    for inputs in (FULL_INPUTS, {"technical": FULL_INPUTS["technical"], "risk": FULL_INPUTS["risk"]}):
        e = eb.build_explanation(make_score(inputs))
        for section in ("what", "how", "why"):
            text = all_text(e[section])
            m = FORBIDDEN.search(text)
            assert m is None, f"{section}: forbidden wording {m.group(0)!r}"
    # the disclaimer lives in notice/limits, which are passed through unchanged
    assert "not investment advice" in e["notice"].lower()
    assert any("does not recommend buying" in lim for lim in e["why"]["limits"])


def test_limits_and_method_come_from_the_stored_snapshot_not_current_config() -> None:
    score = make_score(FULL_INPUTS)
    score["method"] = copy.deepcopy(score["method"])
    score["method"]["limits"] = ["snapshot limit only"]
    e = eb.build_explanation(score)
    assert e["why"]["limits"] == ["snapshot limit only"] and e["how"]["method_version"] == score["scoring_version"]


def test_format_value_units() -> None:
    assert eb.format_value(0.123, "fraction") == "12.3%"
    assert eb.format_value(-0.25, "fraction") == "-25.0%"
    assert eb.format_value(0.5, "score -1..1") == "+0.50"
    assert eb.format_value(1.2345, "ratio") == "1.23"


def test_arithmetic_always_reconciles_on_random_inputs() -> None:
    rng = random.Random(11)
    for _ in range(300):
        inputs = {}
        for key, spec in cfg.COMPONENTS.items():
            values = {}
            for ind in spec["indicators"]:
                span = abs(ind["good"] - ind["poor"])
                values[ind["key"]] = None if rng.random() < 0.3 else (
                    min(ind["poor"], ind["good"]) - span + rng.random() * 3 * span)
            inputs[key] = {"as_of": "2025-01-01", "values": values}
        weights = None if rng.random() < 0.5 else {k: rng.random() for k in cfg.COMPONENT_ORDER}
        if weights is not None and sum(weights.values()) == 0:
            continue
        e = eb.build_explanation(make_score(inputs, weights))
        assert e["how"]["arithmetic_check"]["matches"] is True
        if e["what"]["overall_score"] is not None:
            assert f"{e['what']['overall_score']:.1f} out of 100" in e["what"]["summary"]


def test_a_value_inside_an_unavailable_component_is_explained_not_crashed() -> None:
    # Risk needs 2 of 3 indicators; one value alone leaves the component unavailable.
    inputs = {"technical": FULL_INPUTS["technical"], "fundamental": FULL_INPUTS["fundamental"],
              "risk": {"as_of": "2025-01-10", "values": {"annualized_volatility": 0.3, "max_drawdown": None,
                                                         "historical_var_95": None}}}
    e = eb.build_explanation(make_score(inputs))
    risk = next(c for c in e["how"]["components"] if c["key"] == "risk")
    vol = next(i for i in risk["indicators"] if i["key"] == "annualized_volatility")["sentence"]
    assert "its component was unavailable, so this value carries no weight" in vol
    assert e["how"]["arithmetic_check"]["matches"] is True
    assert all(d["indicator"] != "annualized_volatility" for d in e["why"]["largest_contributors"])
