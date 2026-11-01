"""Phase 10 — explainable scoring tests.

The arithmetic is verified against hand-computed examples and against an
independent oracle written in this file (a few lines of straightforward maths,
deliberately not sharing code with the engine) on seeded random inputs. The
input-gathering rules (which row is "latest", how a symbol is matched, what
counts as missing) and the API contract are tested through the real pipeline.

What these tests establish: the score is computed exactly as documented, every
point is traceable to its inputs, missing data is excluded and explained (never
filled in), and nothing in a result is a buy/sell/hold style judgement. They do
NOT establish that the score is *meaningful* — its anchors are illustrative and
it has not been validated against outcomes (see docs/SCORING_MODULE.md).
"""

import json
import logging
import math
import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import database
from app.models.score_result import ScoreResult
from app.services import market_storage, score_service, scoring_config as cfg, scoring_engine as se, scoring_inputs

# Reuse earlier phases' helpers rather than duplicating them.
from tests.test_market_data import FakeProvider, use_provider  # noqa: F401
from tests.test_market_data import ProviderError  # noqa: F401
from tests.test_processing import XLSX_MIME, big_upload_limit, build_xlsx  # noqa: F401
from tests.test_risk import bars_from_closes, walk_closes
from tests.test_technical import fetch_market


# ---------------------------------------------------------------------------
# An independent oracle (deliberately simple, shares no code with the engine)
# ---------------------------------------------------------------------------


def oracle_sub(value: float, poor: float, good: float) -> float:
    t = (value - poor) / (good - poor)
    return 100.0 * min(1.0, max(0.0, t))


def oracle_overall(values: dict[str, dict[str, float | None]], weights: dict[str, float] | None = None) -> float | None:
    """values[component][indicator] = value or None. Equal weights by default."""
    w = weights or {k: 0.25 for k in cfg.COMPONENT_ORDER}
    total = sum(w.values())
    w = {k: v / total for k, v in w.items()}
    comp_scores: dict[str, float] = {}
    for key, spec in cfg.COMPONENTS.items():
        subs = []
        for ind in spec["indicators"]:
            v = values.get(key, {}).get(ind["key"])
            if v is not None:
                subs.append(oracle_sub(v, ind["poor"], ind["good"]))
        if len(subs) >= spec["min_indicators"]:
            comp_scores[key] = sum(subs) / len(subs)
    live = {k: s for k, s in comp_scores.items() if w[k] > 0}
    coverage = sum(w[k] for k in live)
    if len(live) < 2 or coverage < 0.5:
        return None
    return sum(w[k] / coverage * s for k, s in live.items())


def engine_inputs(values: dict[str, dict[str, float | None]]) -> dict[str, dict]:
    out = {}
    for key, spec in cfg.COMPONENTS.items():
        provided = values.get(key)
        if provided is None:
            out[key] = {"unavailable_reason": "not provided"}
            continue
        out[key] = {
            "values": {k: v for k, v in provided.items() if v is not None},
            "missing": {k: "missing in test" for k, v in provided.items() if v is None},
        }
    return out


FULL = {
    "fundamental": {"net_profit_margin": 0.10, "debt_to_equity": 1.25, "liabilities_to_assets": 0.90},
    "technical": {"price_vs_sma_50": 0.10, "price_vs_sma_200": None},
    "sentiment": {"sentiment_mean": 0.0},
    "risk": {"annualized_volatility": 0.375, "max_drawdown": -0.30, "historical_var_95": None},
}


# ---------------------------------------------------------------------------
# Configuration integrity
# ---------------------------------------------------------------------------


def test_default_weights_are_equal_and_sum_to_one() -> None:
    assert set(cfg.DEFAULT_WEIGHTS) == set(cfg.COMPONENT_ORDER)
    assert sum(cfg.DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)
    assert len(set(cfg.DEFAULT_WEIGHTS.values())) == 1


def test_every_indicator_is_well_formed() -> None:
    seen: set[str] = set()
    assert tuple(cfg.COMPONENTS) == cfg.COMPONENT_ORDER
    for key, spec in cfg.COMPONENTS.items():
        assert 1 <= spec["min_indicators"] <= len(spec["indicators"]), key
        assert spec["label"] and spec["source"]
        for ind in spec["indicators"]:
            assert ind["key"] not in seen, "indicator keys are unique"
            seen.add(ind["key"])
            assert ind["poor"] != ind["good"], "equal anchors would divide by zero"
            assert all(isinstance(ind[f], (int, float)) for f in ("poor", "good"))
            assert ind["label"] and ind["unit"] and ind["note"]


def test_method_description_states_notice_rules_formulas_and_limits() -> None:
    method = cfg.describe_method()
    assert method["scoring_version"] == cfg.SCORING_VERSION
    assert "not investment advice" in method["notice"].lower()
    assert method["formulas"] and method["rules"] and len(method["limits"]) >= 6
    limits = " ".join(method["limits"]).lower()
    for must_say in ("not investment advice", "illustrative", "not been backtested", "equal weights", "unadjusted"):
        assert must_say in limits, must_say
    assert set(method["components"]) == set(cfg.COMPONENT_ORDER)


def test_unused_but_tempting_inputs_are_explained_not_silently_dropped() -> None:
    assert "annual" in cfg.COMPONENTS["fundamental"]["excluded_on_purpose"].lower()
    assert "rsi" in cfg.COMPONENTS["technical"]["excluded_on_purpose"].lower()
    assert "beta" in cfg.COMPONENTS["risk"]["excluded_on_purpose"].lower()


# ---------------------------------------------------------------------------
# Normalisation — hand-computed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, poor, good, expected, saturated",
    [
        (0.10, 0.0, 0.20, 50.0, None),        # higher is better, midway
        (0.0, 0.0, 0.20, 0.0, None),          # exactly at the poor anchor: not "beyond"
        (0.20, 0.0, 0.20, 100.0, None),       # exactly at the good anchor
        (-0.05, 0.0, 0.20, 0.0, "poor"),      # beyond poor: clipped, and says so
        (0.35, 0.0, 0.20, 100.0, "good"),
        (1.25, 2.0, 0.5, 50.0, None),         # lower is better, midway
        (3.0, 2.0, 0.5, 0.0, "poor"),
        (0.1, 2.0, 0.5, 100.0, "good"),
        (-0.30, -0.5, -0.1, 50.0, None),      # negative anchors (drawdown)
        (-0.80, -0.5, -0.1, 0.0, "poor"),
        (-0.02, -0.5, -0.1, 100.0, "good"),
    ],
)
def test_normalize_hand_examples(value, poor, good, expected, saturated) -> None:
    sub, flag = se.normalize(value, poor, good)
    assert sub == pytest.approx(expected) and flag == saturated


def test_normalize_is_monotone_in_the_favourable_direction() -> None:
    for poor, good in ((0.0, 0.2), (2.0, 0.5), (-0.5, -0.1)):
        lo, hi = sorted((poor, good))
        points = [lo + (hi - lo) * i / 20 for i in range(-5, 26)]
        subs = [se.normalize(p, poor, good)[0] for p in points]
        ordered = subs if good > poor else subs[::-1]
        assert ordered == sorted(ordered)


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------


def test_weights_default_and_normalisation() -> None:
    assert se.resolve_weights(None) == cfg.DEFAULT_WEIGHTS
    got = se.resolve_weights({"fundamental": 2, "technical": 1, "sentiment": 1, "risk": 0})
    assert got == {"fundamental": 0.5, "technical": 0.25, "sentiment": 0.25, "risk": 0.0}
    assert sum(se.resolve_weights({"fundamental": 3.5, "technical": 1, "sentiment": 0.5, "risk": 9}).values()) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "bad",
    [
        {"fundamental": 1},
        {"fundamental": 1, "technical": 1, "sentiment": 1},
        {"fundamental": 1, "technical": 1, "sentiment": 1, "risk": 1, "extra": 1},
        {"fundamental": -1, "technical": 1, "sentiment": 1, "risk": 1},
        {"fundamental": 0, "technical": 0, "sentiment": 0, "risk": 0},
        {"fundamental": float("nan"), "technical": 1, "sentiment": 1, "risk": 1},
        {"fundamental": float("inf"), "technical": 1, "sentiment": 1, "risk": 1},
        {"fundamental": True, "technical": 1, "sentiment": 1, "risk": 1},
        {"fundamental": "1", "technical": 1, "sentiment": 1, "risk": 1},
        {},
    ],
)
def test_invalid_weights_are_rejected(bad) -> None:
    with pytest.raises(ValueError):
        se.resolve_weights(bad)


# ---------------------------------------------------------------------------
# Components and the overall score — hand-computed
# ---------------------------------------------------------------------------


def test_worked_example_matches_hand_calculation() -> None:
    # fundamental (50 + 50 + 0)/3 ; technical 100 (one indicator, minimum is 1) ;
    # sentiment 50 ; risk (50 + 50)/2 ; equal weights.
    built = se.build_scores(engine_inputs(FULL))
    by_key = {c["key"]: c for c in built["components"]}
    assert by_key["fundamental"]["score"] == pytest.approx(100 / 3)
    assert by_key["technical"]["score"] == pytest.approx(100.0)
    assert by_key["sentiment"]["score"] == pytest.approx(50.0)
    assert by_key["risk"]["score"] == pytest.approx(50.0)
    assert built["overall"]["score"] == pytest.approx(0.25 * (100 / 3 + 100 + 50 + 50))
    assert built["overall"]["weight_coverage"] == pytest.approx(1.0)


def test_contributions_add_up_to_the_score_exactly() -> None:
    built = se.build_scores(engine_inputs(FULL))
    total = sum(c["contribution_to_overall"] for c in built["components"])
    assert total == built["overall"]["score"]
    for c in built["components"]:
        assert c["contribution_to_overall"] == pytest.approx(c["weight_effective"] * c["score"])
        assert c["score"] == pytest.approx(sum(i["contribution_to_component"] for i in c["indicators"] if i["status"] == "AVAILABLE"))


def test_indicators_are_weighted_equally_among_those_available() -> None:
    comp = se.build_scores(engine_inputs(FULL))["components"][0]
    weights = [i["weight_in_component"] for i in comp["indicators"]]
    assert weights == pytest.approx([1 / 3] * 3) and sum(weights) == pytest.approx(1.0)
    risk = se.build_scores(engine_inputs(FULL))["components"][3]
    assert [i["weight_in_component"] for i in risk["indicators"]] == [0.5, 0.5, None]  # the missing one gets none


def test_a_missing_indicator_is_excluded_and_explained_never_filled_in() -> None:
    risk = se.build_scores(engine_inputs(FULL))["components"][3]
    missing = risk["indicators"][2]
    assert missing["status"] == "MISSING" and missing["reason"] == "missing in test"
    assert missing["value"] is None and missing["sub_score"] is None and missing["contribution_to_component"] is None
    assert risk["score"] == pytest.approx(50.0)  # the mean of the two present, not (50+50+0 or +50)/3


def test_a_component_below_its_minimum_indicator_count_is_unavailable() -> None:
    inputs = engine_inputs(FULL)
    inputs["fundamental"] = {"values": {"net_profit_margin": 0.2}, "missing": {"debt_to_equity": "x", "liabilities_to_assets": "y"}}
    comp = se.build_scores(inputs)["components"][0]
    assert comp["status"] == "UNAVAILABLE" and comp["score"] is None
    assert comp["reason"] == "Only 1 of 3 indicators are available; at least 2 are needed."
    assert comp["indicators"][0]["sub_score"] == pytest.approx(100.0)  # shown, but not used
    assert comp["indicators"][0]["weight_in_component"] is None


def test_an_unavailable_component_gives_every_indicator_the_reason() -> None:
    inputs = engine_inputs(FULL)
    inputs["sentiment"] = {"unavailable_reason": "No sentiment analysis exists for AAA yet."}
    comp = se.build_scores(inputs)["components"][2]
    assert comp["status"] == "UNAVAILABLE" and comp["reason"] == "No sentiment analysis exists for AAA yet."
    assert comp["indicators"][0]["reason"] == comp["reason"]


def test_missing_components_renormalise_the_weights() -> None:
    inputs = engine_inputs(FULL)
    inputs["sentiment"] = {"unavailable_reason": "none"}
    built = se.build_scores(inputs)
    assert built["overall"]["weight_coverage"] == pytest.approx(0.75)
    assert built["overall"]["score"] == pytest.approx((100 / 3 + 100 + 50) / 3)
    effective = {c["key"]: c["weight_effective"] for c in built["components"]}
    assert effective == {"fundamental": pytest.approx(1 / 3), "technical": pytest.approx(1 / 3),
                         "sentiment": None, "risk": pytest.approx(1 / 3)}
    assert built["overall"]["excluded_components"] == {"sentiment": "none"}


def test_overall_needs_two_components() -> None:
    inputs = {k: {"unavailable_reason": "n/a"} for k in cfg.COMPONENT_ORDER}
    inputs["risk"] = engine_inputs(FULL)["risk"]
    overall = se.build_scores(inputs)["overall"]
    assert overall["score"] is None
    assert overall["reason"] == "Only 1 component(s) contributed; at least 2 are needed for an overall score."
    none_at_all = se.build_scores({k: {"unavailable_reason": "n/a"} for k in cfg.COMPONENT_ORDER})["overall"]
    assert none_at_all["score"] is None and none_at_all["weight_coverage"] == 0.0


def test_overall_needs_half_of_the_configured_weight() -> None:
    inputs = engine_inputs(FULL)
    inputs["fundamental"] = {"unavailable_reason": "n/a"}
    inputs["risk"] = {"unavailable_reason": "n/a"}  # technical + sentiment remain: two components
    heavy_elsewhere = {"fundamental": 0.7, "technical": 0.1, "sentiment": 0.1, "risk": 0.1}
    overall = se.build_scores(inputs, heavy_elsewhere)["overall"]
    assert overall["score"] is None and "20%" in overall["reason"] and "50%" in overall["reason"]
    # Exactly half is enough.
    exactly_half = se.build_scores(inputs)["overall"]  # equal weights: 2 of 4 = 50%
    assert exactly_half["weight_coverage"] == pytest.approx(0.5) and exactly_half["score"] == pytest.approx(75.0)


def test_a_zero_weight_component_is_shown_but_does_not_contribute() -> None:
    built = se.build_scores(engine_inputs(FULL), {"fundamental": 0, "technical": 1, "sentiment": 1, "risk": 1})
    fundamental = built["components"][0]
    assert fundamental["status"] == "AVAILABLE" and fundamental["score"] == pytest.approx(100 / 3)
    assert fundamental["in_overall"] is False and fundamental["weight_effective"] is None
    assert built["overall"]["excluded_components"]["fundamental"] == "Weight is 0, so it does not contribute."
    assert built["overall"]["score"] == pytest.approx((100 + 50 + 50) / 3)


def test_changing_weights_changes_the_score_by_exactly_the_documented_amount() -> None:
    inputs = engine_inputs(FULL)
    base = se.build_scores(inputs)
    heavy = se.build_scores(inputs, {"fundamental": 5, "technical": 1, "sentiment": 1, "risk": 1})
    comp = {c["key"]: c["score"] for c in base["components"]}
    expected = (5 * comp["fundamental"] + comp["technical"] + comp["sentiment"] + comp["risk"]) / 8
    assert heavy["overall"]["score"] == pytest.approx(expected)
    assert heavy["overall"]["score"] != pytest.approx(base["overall"]["score"])


def test_saturation_is_reported_on_the_indicator() -> None:
    inputs = engine_inputs(FULL)
    inputs["sentiment"] = {"values": {"sentiment_mean": 0.9}}
    row = se.build_scores(inputs)["components"][2]["indicators"][0]
    assert row["sub_score"] == 100.0 and row["saturated"] == "good" and row["value"] == 0.9


def test_indicator_rows_carry_their_anchors_and_direction() -> None:
    rows = {i["key"]: i for c in se.build_scores(engine_inputs(FULL))["components"] for i in c["indicators"]}
    assert rows["debt_to_equity"]["direction"] == "lower_is_better"
    assert rows["max_drawdown"]["direction"] == "higher_is_better"
    assert (rows["net_profit_margin"]["poor"], rows["net_profit_margin"]["good"]) == (0.0, 0.20)


def test_scoring_is_deterministic_and_uses_native_types() -> None:
    first, second = se.build_scores(engine_inputs(FULL)), se.build_scores(engine_inputs(FULL))
    assert first == second
    assert type(first["overall"]["score"]) is float
    for c in first["components"]:
        for i in c["indicators"]:
            assert i["value"] is None or type(i["value"]) is float


# ---------------------------------------------------------------------------
# Engine vs the independent oracle, and properties, on seeded random inputs
# ---------------------------------------------------------------------------


def _random_values(rng: random.Random) -> dict:
    values: dict = {}
    for key, spec in cfg.COMPONENTS.items():
        if rng.random() < 0.15:
            continue  # component not provided at all
        row = {}
        for ind in spec["indicators"]:
            lo, hi = sorted((ind["poor"], ind["good"]))
            span = hi - lo
            row[ind["key"]] = None if rng.random() < 0.25 else rng.uniform(lo - 0.4 * span, hi + 0.4 * span)
        values[key] = row
    return values


def test_engine_matches_the_independent_oracle_on_random_inputs() -> None:
    rng = random.Random(2024)
    scored = 0
    for _ in range(400):
        values = _random_values(rng)
        weights = None if rng.random() < 0.5 else {k: rng.choice([0, 1, 2, 5]) for k in cfg.COMPONENT_ORDER}
        if weights is not None and sum(weights.values()) == 0:
            weights = None
        expected = oracle_overall(values, weights)
        got = se.build_scores(engine_inputs(values), weights)["overall"]["score"]
        if expected is None:
            assert got is None
        else:
            scored += 1
            assert got == pytest.approx(expected, abs=1e-9)
    assert scored > 100, "the random cases must actually exercise scored outcomes"


def test_improving_a_favourable_input_never_lowers_the_score() -> None:
    rng = random.Random(7)
    for _ in range(150):
        values = _random_values(rng)
        for key, spec in cfg.COMPONENTS.items():
            for ind in spec["indicators"]:
                if values.get(key, {}).get(ind["key"]) is None:
                    continue
                better = json.loads(json.dumps(values))
                step = abs(ind["good"] - ind["poor"]) * 0.1
                better[key][ind["key"]] += step if ind["good"] > ind["poor"] else -step
                a = se.build_scores(engine_inputs(values))["overall"]["score"]
                b = se.build_scores(engine_inputs(better))["overall"]["score"]
                if a is not None:
                    assert b >= a - 1e-9, (key, ind["key"])


def test_the_score_always_lies_between_0_and_100() -> None:
    rng = random.Random(11)
    for _ in range(300):
        score = se.build_scores(engine_inputs(_random_values(rng)))["overall"]["score"]
        assert score is None or 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# API helpers — build real upstream results through the real pipeline
# ---------------------------------------------------------------------------

THIS_FUNDAMENTALS = (
    "Date,Ticker,Revenue,Net Income,Debt,Equity,Liabilities,Assets\n"
    "2023-12-31,AAA,900,90,500,900,600,1000\n"
    "2024-12-31,AAA,1000,150,400,1000,500,1000\n"
    "2024-12-31,BBB,500,5,900,100,950,1000\n"
)

SENTIMENT_TEXTS = [
    "profits surge as company beats estimates", "shares plunge after fraud probe",
    "strong growth and record profits", "weak outlook and layoffs",
    "analysts upgrade on improved margins", "lawsuit and recall hit shares",
]


def upload_fundamentals(client: TestClient, csv_text: str, name: str = "f.csv") -> str:
    response = client.post("/api/files", files={"file": (name, csv_text.encode(), "text/csv")})
    assert response.status_code == 201, response.text
    file_id = response.json()["id"]
    assert client.post(f"/api/files/{file_id}/process").json()["status"] == "COMPLETE"
    assert client.post(f"/api/files/{file_id}/fundamentals").json()["status"] == "COMPLETE"
    return file_id


def run_prices(client: TestClient, use_provider, symbol: str, n: int = 300, seed: int = 5, history: str = "compact"):
    market = fetch_market(client, use_provider, bars_from_closes(walk_closes(n, seed, 0.011, 0.0004)), symbol)
    tech = client.post(f"/api/technical/{symbol}").json()
    risk = client.post(f"/api/risk/{symbol}").json()
    assert tech["status"] == "COMPLETE" and risk["status"] == "COMPLETE"
    return market, tech, risk


def run_sentiment(client: TestClient, symbol: str, texts=None) -> dict:
    response = client.post(f"/api/sentiment/{symbol}/text", json={"texts": texts or SENTIMENT_TEXTS})
    assert response.status_code == 201
    return response.json()


def score(client: TestClient, symbol: str = "AAA", **body):
    response = client.post(f"/api/scores/{symbol}", json=body) if body else client.post(f"/api/scores/{symbol}")
    return response


def comp(result: dict, key: str) -> dict:
    return next(c for c in result["components"] if c["key"] == key)


def ind(result: dict, component: str, key: str) -> dict:
    return next(i for i in comp(result, component)["indicators"] if i["key"] == key)


def all_scores() -> list[ScoreResult]:
    db = database.SessionLocal()
    try:
        return db.query(ScoreResult).all()
    finally:
        db.close()


@pytest.fixture
def full_setup(client: TestClient, use_provider):
    file_id = upload_fundamentals(client, THIS_FUNDAMENTALS)
    market, tech, risk = run_prices(client, use_provider, "AAA")
    sent = run_sentiment(client, "AAA")
    return {"file_id": file_id, "market": market, "tech": tech, "risk": risk, "sent": sent}


# ---------------------------------------------------------------------------
# API — the method endpoint
# ---------------------------------------------------------------------------


def test_scoring_method_endpoint_needs_no_data_and_matches_the_config(client: TestClient) -> None:
    response = client.get("/api/scoring-method")
    assert response.status_code == 200
    body = response.json()
    assert body == json.loads(json.dumps(cfg.describe_method()))
    assert sum(body["default_weights"].values()) == pytest.approx(1.0)
    assert "not investment advice" in body["notice"].lower()


def test_a_symbol_called_method_is_not_shadowed_by_the_method_endpoint(client: TestClient) -> None:
    assert client.get("/api/scores/method").status_code == 404  # the symbol route, not the method doc
    assert client.get("/api/scores/method").json()["detail"]["code"] == "SCORE_RESULT_NOT_FOUND"


# ---------------------------------------------------------------------------
# API — a full score, verified independently from the raw upstream numbers
# ---------------------------------------------------------------------------


def test_full_score_matches_an_independent_recomputation(client: TestClient, full_setup) -> None:
    response = score(client, file_id=full_setup["file_id"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "COMPLETE" and body["symbol"] == "AAA" and body["scoring_version"] == cfg.SCORING_VERSION

    last = full_setup["tech"]["preview_rows"][-1]
    risk = {m["key"]: m["value"] for m in full_setup["risk"]["metrics"]}
    values = {
        "fundamental": {"net_profit_margin": 150 / 1000, "debt_to_equity": 400 / 1000, "liabilities_to_assets": 500 / 1000},
        "technical": {"price_vs_sma_50": last["close"] / last["sma_50"] - 1, "price_vs_sma_200": None},
        "sentiment": {"sentiment_mean": full_setup["sent"]["mean_score"]},
        "risk": {k: risk[k] for k in ("annualized_volatility", "max_drawdown", "historical_var_95")},
    }
    # 300 bars with the default (compact) history still yields sma_200, so include it.
    values["technical"]["price_vs_sma_200"] = last["close"] / last["sma_200"] - 1
    assert body["overall"]["score"] == pytest.approx(oracle_overall(values), abs=1e-9)
    assert body["overall"]["weight_coverage"] == pytest.approx(1.0)
    assert sum(c["contribution_to_overall"] for c in body["components"]) == pytest.approx(body["overall"]["score"])
    assert comp(body, "fundamental")["score"] == pytest.approx(85.0)  # (75 + 100 + 80)/3 by hand


def test_a_result_traces_every_source_and_stores_the_method_snapshot(client: TestClient, full_setup) -> None:
    body = score(client, file_id=full_setup["file_id"]).json()
    refs = {c["key"]: c["source_ref"] for c in body["components"]}
    assert refs["technical"]["result_id"] == full_setup["tech"]["id"]
    assert refs["technical"]["market_snapshot_id"] == full_setup["market"]["id"]
    assert refs["risk"]["result_id"] == full_setup["risk"]["id"]
    assert refs["sentiment"]["result_id"] == full_setup["sent"]["id"]
    assert refs["fundamental"]["file_id"] == full_setup["file_id"] and refs["fundamental"]["result_id"]
    assert body["weights"] == pytest.approx(cfg.DEFAULT_WEIGHTS) and body["weights_customised"] is False
    assert body["method"]["scoring_version"] == cfg.SCORING_VERSION
    assert body["method"]["components"]["risk"]["indicators"][0]["poor"] == 0.60
    assert "not investment advice" in body["notice"].lower() and len(body["method"]["limits"]) >= 6
    assert client.get("/api/scores/AAA").json()["id"] == body["id"]


def test_results_contain_no_ratings_labels_or_recommendations(client: TestClient, full_setup) -> None:
    body = score(client, file_id=full_setup["file_id"]).json()
    forbidden_keys = {"rating", "recommendation", "signal", "action", "band", "grade", "label_overall", "verdict"}

    def keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from keys(v)
        elif isinstance(node, list):
            for item in node:
                yield from keys(item)

    assert not forbidden_keys & set(keys(body))
    assert set(body["overall"]) == {"score", "reason", "weight_coverage", "contributing_components", "excluded_components"}
    text = json.dumps({k: v for k, v in body.items() if k not in ("method", "notice")}).lower()
    for phrase in ("strong buy", "strong sell", "bullish", "bearish", "undervalued", "overvalued", "outperform"):
        assert phrase not in text


def test_scoring_does_not_modify_any_upstream_data(client: TestClient, full_setup) -> None:
    path = market_storage.market_directory() / Path(full_setup["market"]["bars_storage_key"]).name
    before = path.read_bytes()
    upstream = [client.get(f"/api/{p}").json() for p in ("technical/AAA", "risk/AAA", "sentiment/AAA")]
    score(client, file_id=full_setup["file_id"])
    after = [client.get(f"/api/{p}").json() for p in ("technical/AAA", "risk/AAA", "sentiment/AAA")]
    assert upstream == after and path.read_bytes() == before


# ---------------------------------------------------------------------------
# API — fundamentals: which row, which symbol, what counts as missing
# ---------------------------------------------------------------------------


def test_the_latest_period_is_chosen_by_date_not_file_order(client: TestClient, use_provider) -> None:
    csv = ("Date,Ticker,Revenue,Net Income,Debt,Equity,Liabilities,Assets\n"
           "2024-12-31,AAA,1000,150,400,1000,500,1000\n"      # newest, listed FIRST
           "2023-12-31,AAA,900,90,500,900,600,1000\n")
    file_id = upload_fundamentals(client, csv)
    run_prices(client, use_provider, "AAA"); run_sentiment(client, "AAA")
    result = score(client, file_id=file_id).json()
    assert ind(result, "fundamental", "net_profit_margin")["value"] == pytest.approx(0.15)
    assert comp(result, "fundamental")["as_of"] == "2024-12-31"
    assert comp(result, "fundamental")["source_ref"]["latest_row_basis"] == "date"


def test_without_a_date_column_the_last_row_in_the_file_is_used(client: TestClient, use_provider) -> None:
    csv = ("Ticker,Revenue,Net Income,Debt,Equity,Liabilities,Assets\n"
           "AAA,900,90,500,900,600,1000\n"
           "AAA,1000,200,400,1000,500,1000\n")
    file_id = upload_fundamentals(client, csv)
    run_prices(client, use_provider, "AAA"); run_sentiment(client, "AAA")
    result = score(client, file_id=file_id).json()
    assert ind(result, "fundamental", "net_profit_margin")["value"] == pytest.approx(0.20)
    assert comp(result, "fundamental")["as_of"] is None
    assert comp(result, "fundamental")["source_ref"]["latest_row_basis"] == "file order"


def test_each_symbol_gets_its_own_rows_and_unlisted_symbols_get_none(client: TestClient, use_provider) -> None:
    file_id = upload_fundamentals(client, THIS_FUNDAMENTALS)
    for symbol in ("AAA", "BBB", "CCC"):
        run_prices(client, use_provider, symbol, seed={"AAA": 5, "BBB": 6, "CCC": 7}[symbol]); run_sentiment(client, symbol)
    aaa, bbb, ccc = (score(client, s, file_id=file_id).json() for s in ("AAA", "BBB", "CCC"))
    assert ind(aaa, "fundamental", "net_profit_margin")["value"] == pytest.approx(0.15)
    assert ind(bbb, "fundamental", "net_profit_margin")["value"] == pytest.approx(0.01)  # 5 / 500
    assert comp(ccc, "fundamental")["status"] == "UNAVAILABLE"
    assert comp(ccc, "fundamental")["reason"] == "No rows for ticker CCC in this worksheet."
    assert ccc["overall"]["score"] is not None  # the other three components still score


def test_a_single_company_worksheet_is_accepted_but_many_companies_are_not(client: TestClient, use_provider) -> None:
    run_prices(client, use_provider, "AAA"); run_sentiment(client, "AAA")
    one = upload_fundamentals(client, "Company,Revenue,Net Income,Debt,Equity,Liabilities,Assets\nAcme,1000,100,400,1000,500,1000\n", "one.csv")
    many = upload_fundamentals(client, "Company,Revenue,Net Income,Debt,Equity,Liabilities,Assets\nAcme,1000,100,400,1000,500,1000\nGlobex,500,50,200,500,300,900\n", "many.csv")
    assert comp(score(client, file_id=one).json(), "fundamental")["status"] == "AVAILABLE"
    refused = comp(score(client, file_id=many).json(), "fundamental")
    assert refused["status"] == "UNAVAILABLE" and "company name" in refused["reason"]


def test_an_ambiguous_latest_period_is_refused_not_guessed(client: TestClient, use_provider) -> None:
    csv = ("Date,Ticker,Revenue,Net Income,Debt,Equity,Liabilities,Assets\n"
           "2024-12-31,AAA,1000,150,400,1000,500,1000\n"
           "2024-12-31,AAA,1000,10,400,1000,500,1000\n")
    file_id = upload_fundamentals(client, csv)
    run_prices(client, use_provider, "AAA"); run_sentiment(client, "AAA")
    refused = comp(score(client, file_id=file_id).json(), "fundamental")
    assert refused["status"] == "UNAVAILABLE" and "ambiguous" in refused["reason"]


def test_a_metric_missing_in_the_latest_period_is_not_back_filled_from_an_older_one(client: TestClient, use_provider) -> None:
    csv = ("Date,Ticker,Revenue,Net Income,Debt,Equity,Liabilities,Assets\n"
           "2023-12-31,AAA,900,90,500,900,600,1000\n"
           "2024-12-31,AAA,1000,150,,1000,500,1000\n")  # latest period has no Debt
    file_id = upload_fundamentals(client, csv)
    run_prices(client, use_provider, "AAA"); run_sentiment(client, "AAA")
    result = score(client, file_id=file_id).json()
    row = ind(result, "fundamental", "debt_to_equity")
    assert row["status"] == "MISSING" and row["value"] is None and "latest period" in row["reason"]
    assert comp(result, "fundamental")["status"] == "AVAILABLE"  # 2 of 3 meets the minimum of 2


def test_several_analysed_worksheets_require_a_choice(client: TestClient, big_upload_limit, use_provider) -> None:
    header = ["Revenue", "Net Income", "Debt", "Equity", "Liabilities", "Assets"]
    content = build_xlsx({"First": [header, [1000, 100, 400, 1000, 500, 1000]],
                          "Second": [header, [1000, 200, 400, 1000, 500, 1000]]})
    upload = client.post("/api/files", files={"file": ("book.xlsx", content, XLSX_MIME)})
    file_id = upload.json()["id"]
    client.post(f"/api/files/{file_id}/process"); client.post(f"/api/files/{file_id}/fundamentals")
    run_prices(client, use_provider, "AAA"); run_sentiment(client, "AAA")

    refused = comp(score(client, file_id=file_id).json(), "fundamental")
    assert refused["status"] == "UNAVAILABLE" and "pass sheet_name" in refused["reason"]
    chosen = score(client, file_id=file_id, sheet_name="Second").json()
    assert ind(chosen, "fundamental", "net_profit_margin")["value"] == pytest.approx(0.20)
    assert chosen["sheet_name"] == "Second"
    unknown = comp(score(client, file_id=file_id, sheet_name="Nope").json(), "fundamental")
    assert unknown["status"] == "UNAVAILABLE" and "'Nope'" in unknown["reason"]


def test_fundamentals_are_unavailable_when_not_requested_or_not_analysed(client: TestClient, use_provider) -> None:
    run_prices(client, use_provider, "AAA"); run_sentiment(client, "AAA")
    assert comp(score(client).json(), "fundamental")["reason"] == "No file_id was given, so fundamentals were not used."
    raw = client.post("/api/files", files={"file": ("raw.csv", b"Revenue,Net Income\n1,1\n", "text/csv")}).json()["id"]
    unanalysed = comp(score(client, file_id=raw).json(), "fundamental")
    assert unanalysed["status"] == "UNAVAILABLE" and "No successful fundamental analysis" in unanalysed["reason"]
    pdf = client.post("/api/files", files={"file": ("d.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")}).json()["id"]
    assert comp(score(client, file_id=pdf).json(), "fundamental")["status"] == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# API — technical / sentiment / risk inputs
# ---------------------------------------------------------------------------


def test_short_price_history_uses_what_exists_and_says_what_is_missing(client: TestClient, use_provider) -> None:
    run_prices(client, use_provider, "AAA", n=60); run_sentiment(client, "AAA")
    result = score(client).json()
    technical = comp(result, "technical")
    assert technical["status"] == "AVAILABLE" and technical["available_indicators"] == 1
    assert ind(result, "technical", "price_vs_sma_200")["reason"] == "Needs at least 200 bars; 60 available."
    risk = comp(result, "risk")
    assert risk["status"] == "AVAILABLE" and risk["available_indicators"] == 2  # VaR needs 100 returns
    assert ind(result, "risk", "historical_var_95")["reason"] == "Needs at least 100 daily returns; 59 available."


def test_too_little_sentiment_evidence_is_not_used(client: TestClient, use_provider) -> None:
    run_prices(client, use_provider, "AAA")
    run_sentiment(client, "AAA", texts=SENTIMENT_TEXTS[:3] + ["nothing to see", "board meets tuesday"])  # only 3 scored
    result = score(client).json()
    sentiment = comp(result, "sentiment")
    assert sentiment["status"] == "UNAVAILABLE"
    assert ind(result, "sentiment", "sentiment_mean")["reason"] == "Only 3 text(s) carried a sentiment signal; at least 5 are needed."
    assert sentiment["warnings"] == []  # 3 of 5 texts carried a signal (60%), so no low-coverage warning
    assert result["overall"]["score"] is not None  # technical + risk still score


def test_low_sentiment_coverage_is_warned_about(client: TestClient, use_provider) -> None:
    run_prices(client, use_provider, "AAA")
    texts = SENTIMENT_TEXTS + [f"agenda item number {i}" for i in range(20)]  # 6 scored of 26
    run_sentiment(client, "AAA", texts=texts)
    sentiment = comp(score(client).json(), "sentiment")
    assert sentiment["status"] == "AVAILABLE"
    assert any("6 of 26 texts" in w for w in sentiment["warnings"])


def test_risk_warnings_about_possible_splits_are_passed_through_not_hidden(client: TestClient, use_provider) -> None:
    closes = walk_closes(300, 5, 0.011, 0.0004)
    closes[150:] = [c * 0.5 for c in closes[150:]]  # an unadjusted split
    fetch_market(client, use_provider, bars_from_closes(closes), "AAA")
    client.post("/api/technical/AAA"); client.post("/api/risk/AAA"); run_sentiment(client, "AAA")
    result = score(client).json()
    risk = comp(result, "risk")
    assert risk["status"] == "AVAILABLE" and any("stock split" in w for w in risk["warnings"])
    assert "One or more inputs carry warnings; see components[].warnings." in result["warnings"]
    stored = {m["key"]: m["value"] for m in client.get("/api/risk/AAA").json()["metrics"]}
    assert ind(result, "risk", "annualized_volatility")["value"] == stored["annualized_volatility"]  # as stored


def test_a_failed_later_run_does_not_replace_the_latest_complete_result(client: TestClient, use_provider) -> None:
    _, tech, _ = run_prices(client, use_provider, "AAA"); run_sentiment(client, "AAA")
    fetch_market(client, use_provider, bars_from_closes([100.0] * 5), "AAA")  # too short for any indicator
    assert client.post("/api/technical/AAA").json()["status"] == "FAILED"
    assert comp(score(client).json(), "technical")["source_ref"]["result_id"] == tech["id"]


def test_inputs_are_taken_per_symbol(client: TestClient, use_provider) -> None:
    run_prices(client, use_provider, "AAA", seed=5); run_sentiment(client, "AAA")
    _, tech_b, _ = run_prices(client, use_provider, "BBB", seed=99); run_sentiment(client, "BBB")
    aaa, bbb = score(client, "AAA").json(), score(client, "BBB").json()
    assert comp(aaa, "technical")["source_ref"]["result_id"] != comp(bbb, "technical")["source_ref"]["result_id"]
    assert comp(bbb, "technical")["source_ref"]["result_id"] == tech_b["id"]
    assert aaa["overall"]["score"] != bbb["overall"]["score"]


# ---------------------------------------------------------------------------
# API — missing components, consistency warnings
# ---------------------------------------------------------------------------


def test_with_nothing_run_every_component_explains_why_and_overall_is_null(client: TestClient) -> None:
    body = score(client).json()
    assert body["status"] == "COMPLETE" and body["overall"]["score"] is None
    assert body["overall"]["contributing_components"] == [] and body["overall"]["weight_coverage"] == 0.0
    reasons = body["overall"]["excluded_components"]
    assert set(reasons) == set(cfg.COMPONENT_ORDER)
    assert reasons["technical"] == "No successful technical analysis exists for AAA. Run it first."
    assert reasons["sentiment"] == "No successful sentiment analysis exists for AAA. Run it first."
    assert reasons["risk"] == "No successful risk analysis exists for AAA. Run it first."


def test_one_component_is_not_enough_for_an_overall_score(client: TestClient, use_provider) -> None:
    run_prices(client, use_provider, "AAA")
    only_prices = score(client).json()  # technical + risk = two components
    assert only_prices["overall"]["score"] is not None and only_prices["overall"]["weight_coverage"] == pytest.approx(0.5)
    run_sentiment(client, "BBB")
    one = score(client, "BBB").json()
    assert one["overall"]["score"] is None
    assert one["overall"]["reason"] == "Only 1 component(s) contributed; at least 2 are needed for an overall score."


def test_different_price_snapshots_are_flagged(client: TestClient, use_provider) -> None:
    run_prices(client, use_provider, "AAA", n=300, seed=5)
    fetch_market(client, use_provider, bars_from_closes(walk_closes(300, 6, 0.011, 0.0004)), "AAA")  # a newer fetch
    client.post("/api/risk/AAA")  # risk now uses the newer snapshot, technical the older one
    run_sentiment(client, "AAA")
    warnings = score(client).json()["warnings"]
    assert any("different market-data snapshots" in w for w in warnings)


def test_the_same_snapshot_raises_no_snapshot_warning(client: TestClient, use_provider) -> None:
    run_prices(client, use_provider, "AAA"); run_sentiment(client, "AAA")
    assert not any("snapshots" in w for w in score(client).json()["warnings"])


def test_inputs_from_different_dates_are_reported_not_reconciled(client: TestClient, use_provider) -> None:
    file_id = upload_fundamentals(client, THIS_FUNDAMENTALS)  # as-of 2024-12-31
    run_prices(client, use_provider, "AAA"); run_sentiment(client, "AAA")  # prices end 2023-10-28
    warnings = score(client, file_id=file_id).json()["warnings"]
    assert any("as-of different dates" in w and "fundamental: 2024-12-31" in w for w in warnings)


# ---------------------------------------------------------------------------
# API — custom weights and request validation
# ---------------------------------------------------------------------------


def test_custom_weights_are_normalised_stored_and_applied(client: TestClient, full_setup) -> None:
    base = score(client, file_id=full_setup["file_id"]).json()
    custom = score(client, file_id=full_setup["file_id"],
                   weights={"fundamental": 5, "technical": 1, "sentiment": 1, "risk": 1}).json()
    assert custom["weights_customised"] is True
    assert custom["weights"] == pytest.approx({"fundamental": 0.625, "technical": 0.125, "sentiment": 0.125, "risk": 0.125})
    scores_by = {c["key"]: c["score"] for c in custom["components"]}
    assert custom["overall"]["score"] == pytest.approx(0.625 * scores_by["fundamental"] + 0.125 * (scores_by["technical"] + scores_by["sentiment"] + scores_by["risk"]))
    assert custom["overall"]["score"] != pytest.approx(base["overall"]["score"])
    assert custom["method"]["configured_weights"] == pytest.approx(custom["weights"])
    assert custom["method"]["default_weights"] == pytest.approx(cfg.DEFAULT_WEIGHTS)


def test_a_zero_weight_removes_a_component_from_the_score_but_not_from_the_report(client: TestClient, full_setup) -> None:
    body = score(client, file_id=full_setup["file_id"],
                 weights={"fundamental": 0, "technical": 1, "sentiment": 1, "risk": 1}).json()
    assert comp(body, "fundamental")["status"] == "AVAILABLE" and comp(body, "fundamental")["in_overall"] is False
    assert body["overall"]["excluded_components"]["fundamental"] == "Weight is 0, so it does not contribute."
    assert body["overall"]["contributing_components"] == ["technical", "sentiment", "risk"]


@pytest.mark.parametrize(
    "weights",
    [
        {"fundamental": 1},
        {"fundamental": 1, "technical": 1, "sentiment": 1, "risk": 1, "extra": 1},
        {"fundamental": -1, "technical": 1, "sentiment": 1, "risk": 1},
        {"fundamental": 0, "technical": 0, "sentiment": 0, "risk": 0},
        {},
    ],
)
def test_invalid_weights_return_400_and_record_nothing(client: TestClient, weights) -> None:
    response = client.post("/api/scores/AAA", json={"weights": weights})
    assert response.status_code == 400 and response.json()["detail"]["code"] == "INVALID_WEIGHTS"
    assert all_scores() == []


def test_malformed_bodies_use_the_standard_error_envelope(client: TestClient) -> None:
    for payload in ({"weights": "heavy"}, {"weights": {"fundamental": "abc", "technical": 1, "sentiment": 1, "risk": 1}},
                    {"file_id": 123}, {"sheet_name": "x" * 300, "file_id": "f"}):
        response = client.post("/api/scores/AAA", json=payload)
        assert response.status_code == 422 and response.json()["detail"]["code"] == "INVALID_REQUEST"


def test_request_errors_unknown_file_sheet_without_file_and_bad_symbols(client: TestClient) -> None:
    unknown = client.post("/api/scores/AAA", json={"file_id": "00000000-0000-0000-0000-000000000000"})
    assert unknown.status_code == 404 and unknown.json()["detail"]["code"] == "FILE_NOT_FOUND"
    orphan = client.post("/api/scores/AAA", json={"sheet_name": "Sheet1"})
    assert orphan.status_code == 400 and orphan.json()["detail"]["code"] == "SHEET_WITHOUT_FILE"
    for bad in ("A%20B", "-AAPL", "TOOLONGSYMBOL", "AAP%24"):
        for response in (client.post(f"/api/scores/{bad}"), client.get(f"/api/scores/{bad}")):
            assert response.status_code == 400 and response.json()["detail"]["code"] == "INVALID_SYMBOL"
    assert all_scores() == []


def test_the_request_body_is_optional(client: TestClient) -> None:
    assert client.post("/api/scores/AAA").status_code == 201
    assert client.post("/api/scores/AAA", json={}).status_code == 201


def test_get_before_any_score_returns_404_and_results_are_per_symbol(client: TestClient) -> None:
    response = client.get("/api/scores/AAA")
    assert response.status_code == 404 and response.json()["detail"]["code"] == "SCORE_RESULT_NOT_FOUND"
    client.post("/api/scores/AAA")
    assert client.get("/api/scores/BBB").status_code == 404


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


def test_an_unexpected_error_fails_the_run_without_leaking(client: TestClient, monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG)

    def exploding(*_args, **_kwargs):
        raise RuntimeError("boom internal detail /srv/secret/path")

    monkeypatch.setattr(scoring_inputs, "gather_all", exploding)
    response = client.post("/api/scores/AAA")
    body = response.json()
    assert response.status_code == 201 and body["status"] == "FAILED" and body["error_code"] == "SCORING_FAILURE"
    assert body["overall"]["score"] is None and body["overall"]["contributing_components"] == []
    assert body["components"] == []
    assert "boom" not in response.text and "/srv/secret" not in response.text
    assert "boom" not in caplog.text, "only the exception type may be logged"
    assert client.get("/api/scores/AAA").json()["status"] == "FAILED"


def test_database_failure_propagates_and_stores_nothing(client: TestClient, monkeypatch) -> None:
    db = database.SessionLocal()
    try:
        def failing_commit():
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(db, "commit", failing_commit)
        with pytest.raises(RuntimeError):
            score_service.compute_score(db, "AAA")
    finally:
        db.close()
    assert all_scores() == []
