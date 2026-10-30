"""News provider adapters (headline source for sentiment analysis).

Same philosophy as market_providers.py: adapters only fetch and reshape — they
never score, filter by opinion, or invent articles. Differences worth knowing:

  * NewsAPI accepts its key in the `X-Api-Key` HEADER, so the key is never part
    of the URL (unlike Alpha Vantage). It is still never logged, echoed, or
    stored; errors map to fixed messages and the underlying exception is
    dropped (`from None`); httpx/httpcore loggers are pinned to WARNING;
    redirects are not followed; the response size is capped.
  * Article text is third-party content, handled as data: it is length-limited
    downstream and never executed, rendered as HTML, or used in file paths.
"""

import logging
from typing import Protocol

import httpx

from app.services.market_providers import MAX_RESPONSE_BYTES, ProviderError

for _noisy_logger in ("httpx", "httpcore"):
    logging.getLogger(_noisy_logger).setLevel(logging.WARNING)


class NewsProvider(Protocol):
    name: str

    def fetch_headlines(self, query: str, page_size: int) -> list[dict]:
        """Return articles as dicts with keys title, description, source,
        published_at, url (values exactly as the vendor sent them; may be
        None). Raise ProviderError for any failure.
        """
        ...


class NewsApiProvider:
    name = "newsapi"
    BASE_URL = "https://newsapi.org/v2/everything"

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        base_url: str = BASE_URL,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ProviderError(
                "NEWS_NOT_CONFIGURED",
                "No news API key is configured. Set NEWS_API_KEY in the server environment.",
            )
        self._api_key = api_key.strip()
        self._timeout = timeout
        self._transport = transport
        self._base_url = base_url

    def fetch_headlines(self, query: str, page_size: int) -> list[dict]:
        params = {
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "searchIn": "title,description",
            "pageSize": page_size,
        }
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport, follow_redirects=False) as client:
                response = client.get(self._base_url, params=params, headers={"X-Api-Key": self._api_key})
        except httpx.TimeoutException:
            raise ProviderError("PROVIDER_TIMEOUT", "The news provider did not respond in time.") from None
        except httpx.HTTPError:
            raise ProviderError("PROVIDER_UNREACHABLE", "The news provider could not be reached.") from None

        if response.status_code in (401, 403):
            raise ProviderError("PROVIDER_REJECTED_REQUEST", "The news provider rejected the API key or the request.")
        if response.status_code == 429:
            raise ProviderError(
                "PROVIDER_DECLINED_REQUEST",
                "The news provider declined the request (rate limit or quota). Try again later.",
            )
        if response.status_code != 200:
            raise ProviderError(
                "PROVIDER_HTTP_ERROR",
                f"The news provider returned an error (HTTP {response.status_code}).",
            )
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ProviderError("PROVIDER_BAD_RESPONSE", "The news provider's response was too large.")
        try:
            payload = response.json()
        except ValueError:
            raise ProviderError("PROVIDER_BAD_RESPONSE", "The news provider sent a response that could not be read.") from None
        if not isinstance(payload, dict) or payload.get("status") != "ok" or not isinstance(payload.get("articles"), list):
            raise ProviderError("PROVIDER_BAD_RESPONSE", "The news provider sent an unexpected response.")

        articles: list[dict] = []
        for item in payload["articles"]:
            item = item if isinstance(item, dict) else {}
            source = item.get("source")
            articles.append(
                {
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "source": source.get("name") if isinstance(source, dict) else None,
                    "published_at": item.get("publishedAt"),
                    "url": item.get("url"),
                }
            )
        return articles


def build_news_provider(provider_name: str, api_key: str, timeout: float) -> NewsProvider:
    if provider_name == "newsapi":
        return NewsApiProvider(api_key, timeout=timeout)
    raise ProviderError("NEWS_NOT_CONFIGURED", "The configured news provider is not supported.")
