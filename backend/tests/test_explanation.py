"""Phase 11 - What-How-Why explanation API tests.

They run the real pipeline (upload -> process -> fundamentals, prices ->
technical/risk, sentiment -> score) and then check the explanation endpoint
against the stored score. The explanation logic itself is covered, without any
framework, in test_explanation_builder.py.
"""

import pytest
from fastapi.testclient import TestClient

from app.core import database
from app.models.score_result import ScoreResult
from app.services import scoring_inputs

# Reuse Phase 10's helpers and fixtures rather than duplicating them.
from tests.test_market_data import FakeProvider, use_provider  # noqa: F401
from tests.test_processing import XLSX_MIME, big_upload_limit, build_xlsx  # noqa: F401
from tests.test_scores import full_setup, score  # noqa: F401


def explanation(client: TestClient, symbol: str = "AAA"):
    return client.get(f"/api/scores/{symbol}/explanation")


def score_count() -> int:
    db = database.SessionLocal()
    try:
        return db.query(ScoreResult).count()
    finally:
        db.close()


def test_explanation_matches_the_stored_score(client: TestClient, full_setup) -> None:
    stored = score(client, file_id=full_setup["file_id"]).json()
    response = explanation(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["score_id"] == stored["id"] and body["symbol"] == "AAA"
    assert body["what"]["overall_score"] == pytest.approx(stored["overall"]["score"])
    assert f"{stored['overall']['score']:.1f} out of 100" in body["what"]["summary"]
    assert body["how"]["arithmetic_check"]["matches"] is True
    assert {c["key"] for c in body["how"]["components"]} == {"fundamental", "technical", "sentiment", "risk"}
    assert "not investment advice" in body["notice"].lower()
    assert len(body["why"]["limits"]) >= 6 and body["why"]["accounting"]


def test_getting_an_explanation_changes_nothing_and_is_repeatable(client: TestClient, full_setup) -> None:
    score(client, file_id=full_setup["file_id"])
    count = score_count()
    first, second = explanation(client).json(), explanation(client).json()
    assert first == second and score_count() == count


def test_the_latest_score_is_the_one_explained(client: TestClient, full_setup) -> None:
    score(client, file_id=full_setup["file_id"])
    custom = score(client, file_id=full_setup["file_id"], weights={"fundamental": 3, "technical": 1, "sentiment": 1, "risk": 1})
    body = explanation(client).json()
    assert body["score_id"] == custom.json()["id"]
    assert "(custom)" in body["how"]["steps"][3]


def test_explanation_of_a_partial_score_explains_what_is_missing(client: TestClient, use_provider) -> None:
    from tests.test_scores import run_prices, run_sentiment
    run_prices(client, use_provider, "AAA")
    run_sentiment(client, "AAA")
    assert score(client).status_code == 201  # no file: fundamentals are absent
    body = explanation(client).json()
    assert body["what"]["overall_score"] is not None
    assert any("Fundamentals is not in the overall score" in m for m in body["why"]["missing_or_excluded"])
    assert body["how"]["arithmetic_check"]["matches"] is True


def test_symbol_is_case_insensitive(client: TestClient, full_setup) -> None:
    score(client, file_id=full_setup["file_id"])
    assert explanation(client, "aaa").json()["symbol"] == "AAA"


def test_unscored_symbol_is_404(client: TestClient) -> None:
    response = explanation(client, "ZZZ")
    assert response.status_code == 404 and response.json()["detail"]["code"] == "SCORE_RESULT_NOT_FOUND"


def test_a_failed_score_has_nothing_to_explain_409(client: TestClient, monkeypatch) -> None:
    def exploding(*args, **kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(scoring_inputs, "gather_all", exploding)
    assert score(client).json()["status"] == "FAILED"
    response = explanation(client)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "SCORE_NOT_COMPLETE"
    assert "secret internal detail" not in response.text


def test_invalid_symbol_is_rejected(client: TestClient) -> None:
    assert explanation(client, "bad symbol!").status_code == 400


def test_explanation_does_not_leak_secrets_or_paths(client: TestClient, full_setup) -> None:
    score(client, file_id=full_setup["file_id"])
    text = explanation(client).text
    for needle in ("api_key", "apikey", "ALPHA_VANTAGE", "NEWS_API", "/tmp", "Traceback", "storage/"):
        assert needle.lower() not in text.lower(), needle
