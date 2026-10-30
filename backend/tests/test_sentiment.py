"""Phase 8 — sentiment analysis tests.

The scoring arithmetic is tested with a tiny injected lexicon (so the maths is
independent of the word list), the shipped lexicon is checked for integrity
and for documented behaviour including its documented limitations, the news
adapter is tested through httpx.MockTransport (no network), and the API
through dependency overrides. These tests establish that the scoring is
correct and explainable — NOT that it is accurate on real financial text;
that has not been measured.
"""

import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.routes.sentiment import get_news_provider
from app.core import database
from app.core.config import get_settings
from app.main import app
from app.models.sentiment_result import SentimentResult
from app.services import sentiment_engine as eng
from app.services import sentiment_lexicon as lex
from app.services import sentiment_service
from app.services.market_providers import MAX_RESPONSE_BYTES, ProviderError
from app.services.news_providers import NewsApiProvider, build_news_provider

KEY = "NEWSKEY-SECRET-12345"

# A tiny lexicon so the arithmetic tests do not depend on the shipped word list.
WORDS = {"good": 1, "great": 2, "bad": -1, "awful": -2, "poor": -1, "sell-off": -1}
PHRASES = {("poor", "outlook"): -2, ("price", "target"): 1, ("price", "target", "raised"): 2}
NEGATORS = frozenset({"not", "no", "never"})


def score(text: str) -> dict:
    return eng.score_text(text, words=WORDS, phrases=PHRASES, negators=NEGATORS)


def terms(result: dict) -> list[tuple[str, int]]:
    return [(m["term"], m["contribution"]) for m in result["matches"]]


# ---------------------------------------------------------------------------
# Engine — arithmetic (injected lexicon)
# ---------------------------------------------------------------------------


def test_score_is_the_balance_of_positive_and_negative_evidence() -> None:
    r = score("good great")
    assert (r["positive"], r["negative"], r["evidence"], r["score"], r["label"]) == (3.0, 0.0, 3.0, 1.0, "positive")

    r = score("great but bad awful")  # P = 2, N = 3
    assert r["score"] == pytest.approx((2 - 3) / 5)
    assert r["label"] == "negative"


def test_balanced_evidence_is_neutral_not_missing() -> None:
    r = score("good bad")
    assert r["score"] == 0.0 and r["label"] == "neutral" and r["evidence"] == 2.0


def test_a_text_with_no_known_terms_has_no_signal_rather_than_a_neutral_score() -> None:
    r = score("the board met on tuesday")
    assert r["score"] is None and r["label"] == "no_signal"
    assert r["evidence"] == 0.0 and r["matches"] == []
    assert score("")["label"] == "no_signal"


@pytest.mark.parametrize(
    "value, label",
    [(0.05, "positive"), (0.0499, "neutral"), (0.0, "neutral"), (-0.0499, "neutral"),
     (-0.05, "negative"), (1.0, "positive"), (-1.0, "negative"), (None, "no_signal")],
)
def test_label_thresholds(value, label) -> None:
    assert eng.label_for(value) == label


def test_repeated_terms_each_count() -> None:
    assert score("good good good")["positive"] == 3.0


def test_matching_ignores_case_punctuation_numbers_and_keeps_hyphenated_words() -> None:
    r = score("GOOD!!! Revenue up 12.5% -- sell-off, though?")
    assert terms(r) == [("good", 1), ("sell-off", -1)]


def test_text_beyond_the_character_limit_is_not_scored() -> None:
    r = score("filler " * 400 + "good")  # the only term lies past MAX_TEXT_CHARS
    assert len("filler " * 400) > eng.MAX_TEXT_CHARS
    assert r["label"] == "no_signal"


# ---------------------------------------------------------------------------
# Engine — negation
# ---------------------------------------------------------------------------


def test_negation_flips_the_sign_and_is_recorded() -> None:
    r = score("not good")
    assert r["matches"] == [{"term": "good", "weight": 1, "negated": True, "contribution": -1}]
    assert r["score"] == -1.0
    assert score("no bad news")["score"] == 1.0
    assert score("never awful")["matches"][0]["contribution"] == 2


def test_negation_window_is_three_tokens() -> None:
    assert score("not very very good")["matches"][0]["negated"] is True  # negator 3 tokens back
    assert score("not very very very good")["matches"][0]["negated"] is False  # 4 tokens back


@pytest.mark.parametrize("text", ["it didn't look good", "isn't good", "it wasn\u2019t good", "can't be good"])
def test_contractions_negate_including_curly_apostrophes(text) -> None:
    assert score(text)["matches"][-1]["negated"] is True


@pytest.mark.parametrize("separator", [". ", "; ", ": ", "! ", "? ", "\n"])
def test_negation_never_crosses_a_sentence_boundary(separator) -> None:
    assert score(f"It was not{separator}good")["matches"][0]["negated"] is False


def test_negators_are_not_themselves_sentiment_terms() -> None:
    assert score("not")["label"] == "no_signal"


# ---------------------------------------------------------------------------
# Engine — phrases
# ---------------------------------------------------------------------------


def test_phrases_take_precedence_and_do_not_double_count_their_words() -> None:
    assert terms(score("poor outlook")) == [("poor outlook", -2)]  # not poor(-1) + outlook
    assert terms(score("poor results")) == [("poor", -1)]


def test_the_longest_phrase_wins() -> None:
    assert terms(score("price target raised")) == [("price target raised", 2)]
    assert terms(score("price target")) == [("price target", 1)]


def test_phrases_can_be_negated() -> None:
    assert terms(score("not poor outlook")) == [("poor outlook", 2)]


def test_phrases_do_not_span_sentences() -> None:
    assert score("poor. outlook")["matches"][0]["term"] == "poor"


# ---------------------------------------------------------------------------
# Engine — aggregation, dedup, purity
# ---------------------------------------------------------------------------


def test_aggregate_averages_only_texts_that_carry_a_signal() -> None:
    scored = [score("good"), score("good bad awful"), score("nothing here")]  # 1.0, -0.5*? compute below
    summary = eng.aggregate(scored)
    assert summary["text_count"] == 3 and summary["scored_count"] == 2
    expected = (1.0 + (1 - 3) / 4) / 2
    assert summary["mean_score"] == pytest.approx(expected)
    assert summary["coverage"] == pytest.approx(2 / 3)
    assert summary["counts"] == {"positive": 1, "negative": 1, "neutral": 0, "no_signal": 1}


def test_aggregate_of_nothing_is_no_signal() -> None:
    assert eng.aggregate([]) == {
        "text_count": 0, "scored_count": 0, "coverage": None, "mean_score": None, "label": "no_signal",
        "counts": {"positive": 0, "negative": 0, "neutral": 0, "no_signal": 0},
    }
    only_empty = eng.aggregate([score("nothing"), score("also nothing")])
    assert only_empty["mean_score"] is None and only_empty["coverage"] == 0.0


def test_a_neutral_mean_can_hide_disagreement_so_counts_are_reported() -> None:
    summary = eng.aggregate([score("good"), score("bad")])
    assert summary["mean_score"] == 0.0 and summary["label"] == "neutral"
    assert summary["counts"]["positive"] == 1 and summary["counts"]["negative"] == 1


def test_dedup_key_ignores_case_and_spacing() -> None:
    assert eng.normalize_for_dedup("  IBM  Beats\tEstimates ") == eng.normalize_for_dedup("ibm beats estimates")


def test_scoring_is_deterministic_and_uses_native_types() -> None:
    first, second = score("good not bad awful"), score("good not bad awful")
    assert first == second
    assert type(first["positive"]) is float and type(first["evidence"]) is float
    assert all(type(m["weight"]) is int and type(m["negated"]) is bool for m in first["matches"])


# ---------------------------------------------------------------------------
# The shipped lexicon
# ---------------------------------------------------------------------------


def test_lexicon_integrity() -> None:
    assert lex.LEXICON_VERSION
    positive = set(lex.POSITIVE_STRONG + lex.POSITIVE)
    negative = set(lex.NEGATIVE_STRONG + lex.NEGATIVE)
    assert not positive & negative, "a word may have only one polarity"
    all_words = lex.POSITIVE_STRONG + lex.POSITIVE + lex.NEGATIVE_STRONG + lex.NEGATIVE
    assert len(all_words) == len(set(all_words)), "no duplicate entries"
    assert set(lex.WORD_WEIGHTS.values()) == {-2, -1, 1, 2}
    for word in lex.WORD_WEIGHTS:
        assert word == word.lower() and eng.tokenize(word) == [word], f"{word!r} could never be matched"
    assert not set(lex.WORD_WEIGHTS) & lex.NEGATORS


def test_every_phrase_is_reachable_by_the_tokenizer() -> None:
    for phrase, weight in lex.PHRASES.items():
        assert len(phrase) >= 2 and weight in (-2, -1, 1, 2)
        assert eng.tokenize(" ".join(phrase)) == list(phrase), f"{phrase} can never match"


def test_ambiguous_generic_words_are_deliberately_absent() -> None:
    assert {"risk", "cut", "up", "record", "debt", "dividend", "short"}.isdisjoint(lex.WORD_WEIGHTS)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Company beats expectations as profits surge", "positive"),
        ("Shares plunge after profit warning and fraud probe", "negative"),
        ("The company is not profitable", "negative"),
        ("No losses reported this quarter", "positive"),
        ("It didn't miss estimates", "positive"),
        ("The board met on Tuesday to discuss the agenda", "no_signal"),
        ("Stock hits record high but warns of headwinds", "neutral"),
    ],
)
def test_shipped_lexicon_on_unambiguous_examples(text, expected) -> None:
    assert eng.score_text(text)["label"] == expected


def test_known_limitation_negation_beyond_three_tokens_is_missed() -> None:
    # Semantically negative, but the negator is 4 tokens before "growth".
    # Pinned so any future improvement is a deliberate change, and documented.
    assert eng.score_text("Not a single analyst expects growth")["label"] == "positive"


def test_known_limitation_context_is_not_understood() -> None:
    assert eng.score_text("Rising costs worry investors")["label"] == "positive"  # "rising" read as good


# ---------------------------------------------------------------------------
# News adapter (simulated transport, documented NewsAPI response shape)
# ---------------------------------------------------------------------------


def article(title="IBM beats estimates", description="Strong quarter", name="Wire", at="2024-05-02T10:00:00Z",
            url="https://example.com/a") -> dict:
    return {"source": {"id": None, "name": name}, "title": title, "description": description,
            "url": url, "publishedAt": at}


def newsapi(handler, key: str = KEY) -> NewsApiProvider:
    return NewsApiProvider(key, transport=httpx.MockTransport(handler))


def ok_payload(*articles) -> dict:
    return {"status": "ok", "totalResults": len(articles), "articles": list(articles)}


def test_news_adapter_sends_the_key_in_a_header_never_in_the_url() -> None:
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=ok_payload(article()))

    result = newsapi(handler).fetch_headlines("IBM", 25)
    request = seen[0]
    assert request.headers["X-Api-Key"] == KEY
    assert KEY not in str(request.url)
    assert request.url.host == "newsapi.org"
    assert dict(request.url.params) == {
        "q": "IBM", "language": "en", "sortBy": "publishedAt", "searchIn": "title,description", "pageSize": "25",
    }
    assert result == [{"title": "IBM beats estimates", "description": "Strong quarter", "source": "Wire",
                       "published_at": "2024-05-02T10:00:00Z", "url": "https://example.com/a"}]


def test_news_adapter_tolerates_missing_and_malformed_fields() -> None:
    def handler(request):
        return httpx.Response(200, json=ok_payload({"title": "x", "source": None}, "garbage", {}))

    result = newsapi(handler).fetch_headlines("IBM", 10)
    assert result[0] == {"title": "x", "description": None, "source": None, "published_at": None, "url": None}
    assert result[1] == result[2] == {"title": None, "description": None, "source": None, "published_at": None, "url": None}


@pytest.mark.parametrize(
    "response, code",
    [
        (httpx.Response(401, json={"status": "error", "code": "apiKeyInvalid", "message": "bad " + KEY}), "PROVIDER_REJECTED_REQUEST"),
        (httpx.Response(403, text="forbidden"), "PROVIDER_REJECTED_REQUEST"),
        (httpx.Response(429, json={"status": "error"}), "PROVIDER_DECLINED_REQUEST"),
        (httpx.Response(500, text="oops"), "PROVIDER_HTTP_ERROR"),
        (httpx.Response(503, text="down"), "PROVIDER_HTTP_ERROR"),
        (httpx.Response(302, headers={"location": "https://evil.example/?x=1"}), "PROVIDER_HTTP_ERROR"),
        (httpx.Response(200, text="<html>not json</html>"), "PROVIDER_BAD_RESPONSE"),
        (httpx.Response(200, json=[1, 2]), "PROVIDER_BAD_RESPONSE"),
        (httpx.Response(200, json={"status": "error", "code": "x", "message": "m"}), "PROVIDER_BAD_RESPONSE"),
        (httpx.Response(200, json={"status": "ok", "articles": "nope"}), "PROVIDER_BAD_RESPONSE"),
        (httpx.Response(200, json={"status": "ok"}), "PROVIDER_BAD_RESPONSE"),
    ],
)
def test_news_adapter_maps_failures_to_safe_errors(response, code) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return response

    with pytest.raises(ProviderError) as excinfo:
        newsapi(handler).fetch_headlines("IBM", 10)
    error = excinfo.value
    assert error.code == code
    assert len(calls) == 1, "redirects must not be followed"
    assert KEY not in error.message and KEY not in str(error)
    assert error.__cause__ is None and (error.__context__ is None or error.__suppress_context__)


@pytest.mark.parametrize(
    "raised, code",
    [
        (httpx.ConnectError("connect failed to https://newsapi.org/?x-api-key=" + KEY), "PROVIDER_UNREACHABLE"),
        (httpx.ReadTimeout("timed out " + KEY), "PROVIDER_TIMEOUT"),
    ],
)
def test_news_adapter_network_errors_never_leak_the_key(raised, code) -> None:
    def handler(request):
        raise raised

    with pytest.raises(ProviderError) as excinfo:
        newsapi(handler).fetch_headlines("IBM", 10)
    error = excinfo.value
    assert error.code == code and KEY not in error.message and KEY not in str(error)
    assert error.__cause__ is None and (error.__context__ is None or error.__suppress_context__)


def test_news_adapter_rejects_oversized_responses(monkeypatch) -> None:
    monkeypatch.setattr("app.services.news_providers.MAX_RESPONSE_BYTES", 50)

    def handler(request):
        return httpx.Response(200, json=ok_payload(article()))

    with pytest.raises(ProviderError) as excinfo:
        newsapi(handler).fetch_headlines("IBM", 10)
    assert excinfo.value.code == "PROVIDER_BAD_RESPONSE" and MAX_RESPONSE_BYTES == 10 * 1024 * 1024


@pytest.mark.parametrize("key", ["", "   "])
def test_news_adapter_requires_a_key(key) -> None:
    with pytest.raises(ProviderError) as excinfo:
        NewsApiProvider(key)
    assert excinfo.value.code == "NEWS_NOT_CONFIGURED"


def test_build_news_provider() -> None:
    assert isinstance(build_news_provider("newsapi", KEY, 5.0), NewsApiProvider)
    with pytest.raises(ProviderError) as excinfo:
        build_news_provider("mystery", KEY, 5.0)
    assert excinfo.value.code == "NEWS_NOT_CONFIGURED"


def test_news_request_logging_never_contains_the_key(caplog) -> None:
    caplog.set_level(logging.DEBUG)

    def handler(request):
        return httpx.Response(200, json=ok_payload(article()))

    newsapi(handler).fetch_headlines("IBM", 10)
    assert KEY not in caplog.text


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


class FakeNews:
    name = "fake_news"

    def __init__(self, articles=None, error: Exception | None = None):
        self.articles = articles if articles is not None else []
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def fetch_headlines(self, query: str, page_size: int) -> list[dict]:
        self.calls.append((query, page_size))
        if self.error is not None:
            raise self.error
        return self.articles


def fake_article(title, description=None, source="Wire", published="2024-05-02T10:00:00Z", url="https://example.com/x"):
    return {"title": title, "description": description, "source": source, "published_at": published, "url": url}


@pytest.fixture
def use_news():
    def install(provider):
        app.dependency_overrides[get_news_provider] = lambda: provider
        return provider

    yield install
    app.dependency_overrides.pop(get_news_provider, None)


def post_texts(client: TestClient, texts, symbol: str = "IBM"):
    return client.post(f"/api/sentiment/{symbol}/text", json={"texts": texts})


def all_results() -> list[SentimentResult]:
    db = database.SessionLocal()
    try:
        return db.query(SentimentResult).all()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# API — submitted text
# ---------------------------------------------------------------------------


def test_submitted_texts_are_scored_and_explained(client: TestClient) -> None:
    response = post_texts(client, ["IBM beats estimates as profits surge", "Shares plunge after fraud probe", "Board meets Tuesday"], "ibm")
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["status"] == "COMPLETE" and body["symbol"] == "IBM"
    assert body["source_type"] == "text" and body["provider"] is None and body["query"] is None
    assert body["lexicon_version"] == lex.LEXICON_VERSION
    assert (body["received_count"], body["text_count"], body["scored_count"]) == (3, 3, 2)
    assert body["counts"] == {"positive": 1, "negative": 1, "neutral": 0, "no_signal": 1}
    assert body["coverage"] == pytest.approx(2 / 3)
    assert body["mean_score"] == pytest.approx(0.0) and body["label"] == "neutral"

    first, second, third = body["items"]
    assert [i["index"] for i in body["items"]] == [0, 1, 2]
    assert first["label"] == "positive" and first["score"] == 1.0 and first["evidence"] == 5.0
    assert [(m["term"], m["contribution"]) for m in first["matches"]] == [("beats estimates", 2), ("profits", 1), ("surge", 2)]
    assert second["label"] == "negative" and third["label"] == "no_signal" and third["score"] is None


def test_duplicate_texts_are_counted_once_and_the_removal_is_reported(client: TestClient) -> None:
    body = post_texts(client, ["Profits surge", "  profits   SURGE ", "Profits fall"]).json()
    assert body["received_count"] == 3 and body["duplicates_removed"] == 1 and body["text_count"] == 2
    assert [i["text"] for i in body["items"]] == ["Profits surge", "Profits fall"]  # first occurrence kept


def test_long_text_is_scored_in_full_but_displayed_truncated(client: TestClient) -> None:
    text = "filler " * 60 + "profits surge"  # ~433 chars; the terms sit beyond the 300-char preview
    item = post_texts(client, [text]).json()["items"][0]
    assert item["text_truncated"] is True and len(item["text"]) == 300
    assert item["label"] == "positive"


def test_untrusted_markup_is_returned_as_plain_data(client: TestClient) -> None:
    text = "<script>alert(1)</script> profits surge"
    item = post_texts(client, [text]).json()["items"][0]
    assert item["text"] == text and item["label"] == "positive"


@pytest.mark.parametrize(
    "payload",
    [
        {"texts": []},
        {"texts": ["   "]},
        {"texts": ["ok", ""]},
        {"texts": ["x" * 2001]},
        {"texts": ["x"] * 101},
        {"texts": "not a list"},
        {"texts": [1, 2]},
        {},
    ],
)
def test_invalid_text_requests_use_the_standard_error_envelope(client: TestClient, payload) -> None:
    response = client.post("/api/sentiment/IBM/text", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_REQUEST"
    assert all_results() == []


def test_the_text_limits_are_inclusive(client: TestClient) -> None:
    assert post_texts(client, ["x" * 2000]).status_code == 201
    assert post_texts(client, [f"headline {i}" for i in range(100)]).status_code == 201


@pytest.mark.parametrize("symbol", ["A%20B", "-AAPL", "TOOLONGSYMBOL", "AAP%24"])
def test_invalid_symbols_are_rejected(client: TestClient, symbol) -> None:
    for response in (post_texts(client, ["profits surge"], symbol), client.get(f"/api/sentiment/{symbol}")):
        assert response.status_code == 400 and response.json()["detail"]["code"] == "INVALID_SYMBOL"
    assert all_results() == []


def test_database_failure_propagates_and_stores_nothing(client: TestClient, monkeypatch) -> None:
    db = database.SessionLocal()
    try:
        def failing_commit():
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(db, "commit", failing_commit)
        with pytest.raises(RuntimeError):
            sentiment_service.score_submitted_texts(db, "IBM", ["profits surge"])
    finally:
        db.close()
    assert all_results() == []


# ---------------------------------------------------------------------------
# API — news
# ---------------------------------------------------------------------------


def test_news_headlines_are_fetched_scored_and_attributed(client: TestClient, use_news) -> None:
    provider = use_news(FakeNews([
        fake_article("IBM beats expectations on cloud growth", "Strong quarter.", "Wire A", "2024-05-02T10:00:00Z", "https://a.example/1"),
        fake_article("IBM faces lawsuit and layoffs", "Analysts voice concern.", "Blog", "2024-04-30T09:30:00+02:00", "https://b.example/2"),
        fake_article("IBM schedules annual meeting", None, "Desk", None, None),
    ]))
    response = client.post("/api/sentiment/ibm/news")
    body = response.json()

    assert response.status_code == 201 and body["status"] == "COMPLETE"
    assert provider.calls == [("IBM", get_settings().news_page_size)]  # query defaults to the symbol
    assert body["source_type"] == "news" and body["provider"] == "fake_news" and body["query"] == "IBM"
    assert (body["text_count"], body["scored_count"]) == (3, 2)
    assert body["counts"] == {"positive": 1, "negative": 1, "neutral": 0, "no_signal": 1}
    first, second, third = body["items"]
    assert first["source"] == "Wire A" and first["url"] == "https://a.example/1"
    assert first["label"] == "positive" and second["label"] == "negative" and third["label"] == "no_signal"
    assert second["published_at"] == "2024-04-30T07:30:00+00:00"  # offset converted to UTC
    assert body["earliest_published"] == "2024-04-30T07:30:00+00:00"
    assert body["latest_published"] == "2024-05-02T10:00:00+00:00"
    # Title and description are both scored: "concern" comes from the description.
    assert "concern" in [m["term"] for m in second["matches"]]


def test_removed_and_titleless_articles_are_skipped_and_counted(client: TestClient, use_news) -> None:
    use_news(FakeNews([
        fake_article("[Removed]", "[Removed]"),
        fake_article(None, "orphan description with profits surge"),
        fake_article("   "),
        fake_article("Profits surge", "[Removed]"),
    ]))
    body = client.post("/api/sentiment/IBM/news").json()
    assert body["received_count"] == 4 and body["skipped"] == {"no usable title": 3}
    assert body["text_count"] == 1 and body["items"][0]["text"] == "Profits surge"


def test_syndicated_headlines_are_counted_once(client: TestClient, use_news) -> None:
    use_news(FakeNews([
        fake_article("IBM Beats Expectations", "Version one", "Wire A"),
        fake_article("  ibm beats   expectations ", "Different description", "Wire B"),
    ]))
    body = client.post("/api/sentiment/IBM/news").json()
    assert body["duplicates_removed"] == 1 and body["text_count"] == 1 and body["items"][0]["source"] == "Wire A"


def test_unsafe_or_malformed_article_fields_are_neutralised(client: TestClient, use_news) -> None:
    use_news(FakeNews([
        fake_article("Profits surge", url="javascript:alert(1)", published="not-a-date"),
        fake_article("Profits fall", url="https://ok.example/" + "x" * 600),
        {"title": 12345, "description": ["x"], "source": 7, "published_at": 9, "url": 3},
    ]))
    body = client.post("/api/sentiment/IBM/news").json()
    assert [i["url"] for i in body["items"]] == [None, None]
    assert body["items"][0]["published_at"] is None
    assert body["skipped"] == {"no usable title": 1}


def test_custom_query_is_passed_through(client: TestClient, use_news) -> None:
    provider = use_news(FakeNews([fake_article("Profits surge")]))
    body = client.post("/api/sentiment/IBM/news", params={"query": "International Business Machines"}).json()
    assert provider.calls[0][0] == "International Business Machines"
    assert body["query"] == "International Business Machines" and body["symbol"] == "IBM"


@pytest.mark.parametrize("query", ["   ", "x" * 101, "bad\x00query", "line\nbreak"])
def test_invalid_queries_are_rejected_before_any_provider_call(client: TestClient, use_news, query) -> None:
    provider = use_news(FakeNews())
    response = client.post("/api/sentiment/IBM/news", params={"query": query})
    assert response.status_code == 400 and response.json()["detail"]["code"] == "INVALID_QUERY"
    assert provider.calls == [] and all_results() == []


def test_zero_articles_is_a_successful_empty_result_not_a_failure(client: TestClient, use_news) -> None:
    use_news(FakeNews([]))
    body = client.post("/api/sentiment/IBM/news").json()
    assert body["status"] == "COMPLETE" and body["text_count"] == 0
    assert body["mean_score"] is None and body["coverage"] is None and body["label"] == "no_signal"


@pytest.mark.parametrize("code", ["PROVIDER_DECLINED_REQUEST", "PROVIDER_REJECTED_REQUEST", "PROVIDER_TIMEOUT", "PROVIDER_UNREACHABLE"])
def test_provider_errors_become_failed_results(client: TestClient, use_news, code) -> None:
    use_news(FakeNews(error=ProviderError(code, "A safe message.")))
    response = client.post("/api/sentiment/IBM/news")
    body = response.json()
    assert response.status_code == 201 and body["status"] == "FAILED"
    assert body["error_code"] == code and body["error_message"] == "A safe message."
    assert body["items"] == [] and body["mean_score"] is None
    assert client.get("/api/sentiment/IBM").json()["status"] == "FAILED"


def test_unexpected_provider_exception_fails_without_leaking(client: TestClient, use_news, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    use_news(FakeNews(error=RuntimeError(f"boom https://x/?k={KEY}")))
    response = client.post("/api/sentiment/IBM/news")
    body = response.json()
    assert body["status"] == "FAILED" and body["error_code"] == "NEWS_FETCH_FAILURE"
    assert KEY not in response.text and "boom" not in response.text
    assert KEY not in caplog.text and "boom" not in caplog.text


def test_unconfigured_news_provider_returns_503_and_records_nothing(client: TestClient) -> None:
    response = client.post("/api/sentiment/IBM/news")
    assert response.status_code == 503 and response.json()["detail"]["code"] == "NEWS_NOT_CONFIGURED"
    assert all_results() == []


def test_unsupported_provider_setting_returns_503(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("NEWS_PROVIDER", "mystery")
    monkeypatch.setenv("NEWS_API_KEY", KEY)
    get_settings.cache_clear()
    response = client.post("/api/sentiment/IBM/news")
    assert response.status_code == 503 and KEY not in response.text


def test_a_configured_key_builds_the_newsapi_provider(monkeypatch) -> None:
    monkeypatch.setenv("NEWS_API_KEY", KEY)
    get_settings.cache_clear()
    assert isinstance(get_news_provider(), NewsApiProvider)


def test_news_key_never_appears_in_responses_database_or_logs(client: TestClient, use_news, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    outputs = []

    def server_error(request):
        return httpx.Response(401, json={"status": "error", "message": "bad key " + KEY})

    def network_down(request):
        raise httpx.ConnectError("failed " + KEY)

    def fine(request):
        return httpx.Response(200, json=ok_payload(article("IBM profits surge", "Great news")))

    for handler in (server_error, network_down, fine):
        use_news(newsapi(handler))
        response = client.post("/api/sentiment/IBM/news")
        assert response.status_code == 201
        outputs.append(response.text)
        outputs.append(client.get("/api/sentiment/IBM").text)
    for result in all_results():
        outputs.append(json.dumps({c.name: str(getattr(result, c.name)) for c in result.__table__.columns}))
    assert len(all_results()) == 3
    assert not any(KEY in text for text in outputs)
    assert KEY not in caplog.text


# ---------------------------------------------------------------------------
# API — reading results
# ---------------------------------------------------------------------------


def test_get_returns_the_latest_result_optionally_by_source(client: TestClient, use_news) -> None:
    text_result = post_texts(client, ["profits surge"]).json()
    use_news(FakeNews([fake_article("Shares plunge")]))
    news_result = client.post("/api/sentiment/IBM/news").json()

    assert client.get("/api/sentiment/IBM").json()["id"] == news_result["id"]
    assert client.get("/api/sentiment/IBM?source=text").json()["id"] == text_result["id"]
    assert client.get("/api/sentiment/IBM?source=news").json()["id"] == news_result["id"]


def test_get_before_any_analysis_returns_404_and_unknown_source_422(client: TestClient) -> None:
    response = client.get("/api/sentiment/IBM")
    assert response.status_code == 404 and response.json()["detail"]["code"] == "SENTIMENT_RESULT_NOT_FOUND"
    assert client.get("/api/sentiment/IBM?source=rumour").status_code == 422
    post_texts(client, ["profits surge"], "MSFT")
    assert client.get("/api/sentiment/IBM").status_code == 404  # results are per symbol


def test_sentiment_needs_no_uploaded_file_or_market_data(client: TestClient) -> None:
    assert client.get("/api/files").json()["items"] == []
    assert post_texts(client, ["profits surge"]).status_code == 201
