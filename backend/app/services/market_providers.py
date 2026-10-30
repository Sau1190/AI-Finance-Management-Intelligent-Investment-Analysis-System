"""Market data provider adapters.

Beginner view:
  An "adapter" hides the quirks of one data vendor behind a simple question:
  "give me this symbol's daily prices". Everything after that (checking the
  numbers, storing them) is the same no matter which vendor answered.

Technical view:
  * Adapters only fetch and reshape — they never validate, repair, estimate,
    or fabricate prices. Validation lives in market_validation.py so every
    future provider is held to the same rules.
  * Alpha Vantage puts the API key in the query string. httpx errors and
    status exceptions can embed the full URL, so NOTHING here ever formats,
    logs, or re-raises an underlying exception's text: errors are mapped to
    ProviderError with fixed, vendor-neutral messages, and the original
    exception is dropped (`from None`).
  * The vendor is a trusted-but-fallible third party: timeouts are bounded,
    redirects are not followed (so the key can't be forwarded to another
    host), and the response size is capped.
"""

import logging
from typing import Protocol

import httpx

MAX_RESPONSE_BYTES = 10 * 1024 * 1024

# httpx logs every request at INFO *including the full URL*, and Alpha
# Vantage's URL carries the API key as a query parameter. Keep those loggers
# quiet so the key can never reach a log sink, even if INFO logging is enabled.
for _noisy_logger in ("httpx", "httpcore"):
    logging.getLogger(_noisy_logger).setLevel(logging.WARNING)


class ProviderError(Exception):
    """A provider could not supply data. `code` and `message` are authored
    here and safe to show users; they never contain URLs, keys, or raw vendor
    text.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class MarketDataProvider(Protocol):
    name: str

    def fetch_daily(self, symbol: str, history: str) -> list[dict]:
        """Return raw daily bars for `symbol` as dicts with keys
        date/open/high/low/close/volume (values exactly as the vendor sent
        them). `history` is "compact" (recent) or "full". Raise ProviderError
        for any failure.
        """
        ...


class AlphaVantageProvider:
    name = "alpha_vantage"
    BASE_URL = "https://www.alphavantage.co/query"

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
                "MARKET_DATA_NOT_CONFIGURED",
                "No market data API key is configured. Set ALPHA_VANTAGE_API_KEY in the server environment.",
            )
        self._api_key = api_key.strip()
        self._timeout = timeout
        self._transport = transport
        self._base_url = base_url

    def fetch_daily(self, symbol: str, history: str) -> list[dict]:
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": "full" if history == "full" else "compact",
            "datatype": "json",
            "apikey": self._api_key,
        }
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport, follow_redirects=False) as client:
                response = client.get(self._base_url, params=params)
        except httpx.TimeoutException:
            raise ProviderError("PROVIDER_TIMEOUT", "The market data provider did not respond in time.") from None
        except httpx.HTTPError:
            raise ProviderError("PROVIDER_UNREACHABLE", "The market data provider could not be reached.") from None

        if response.status_code != 200:
            raise ProviderError(
                "PROVIDER_HTTP_ERROR",
                f"The market data provider returned an error (HTTP {response.status_code}).",
            )
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ProviderError("PROVIDER_BAD_RESPONSE", "The market data provider's response was too large.")
        try:
            payload = response.json()
        except ValueError:
            raise ProviderError("PROVIDER_BAD_RESPONSE", "The market data provider sent a response that could not be read.") from None
        if not isinstance(payload, dict):
            raise ProviderError("PROVIDER_BAD_RESPONSE", "The market data provider sent an unexpected response.")

        # Alpha Vantage reports failures inside an HTTP 200 body.
        if "Error Message" in payload:
            raise ProviderError(
                "PROVIDER_REJECTED_REQUEST",
                "The provider rejected the request (the symbol may be unknown, or the API key invalid).",
            )
        if "Note" in payload or "Information" in payload:
            raise ProviderError(
                "PROVIDER_DECLINED_REQUEST",
                "The provider declined the request (rate limit, quota, or plan restriction). Try again later.",
            )

        series = payload.get("Time Series (Daily)")
        if not isinstance(series, dict):
            raise ProviderError("PROVIDER_BAD_RESPONSE", "The market data provider sent an unexpected response.")

        bars: list[dict] = []
        for date, row in series.items():
            row = row if isinstance(row, dict) else {}
            bars.append(
                {
                    "date": date,
                    "open": row.get("1. open"),
                    "high": row.get("2. high"),
                    "low": row.get("3. low"),
                    "close": row.get("4. close"),
                    "volume": row.get("5. volume"),
                }
            )
        return bars


def build_provider(provider_name: str, api_key: str, timeout: float) -> MarketDataProvider:
    """Create the configured provider. Raises ProviderError if the provider is
    unsupported or not configured.
    """
    if provider_name == "alpha_vantage":
        return AlphaVantageProvider(api_key, timeout=timeout)
    raise ProviderError("MARKET_DATA_NOT_CONFIGURED", "The configured market data provider is not supported.")
