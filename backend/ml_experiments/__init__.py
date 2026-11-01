"""Phase 13 - ML experiments (EXPERIMENTAL, offline, not part of the API).

Nothing in `app/` imports this package, no endpoint exposes it, and it writes
nothing to the database. The deterministic analysis and the Phase 10 score stay
the only source of truth. Everything here is research tooling that answers one
question honestly: "on a labelled dataset I can reproduce, does a simple ML
model do better than the existing deterministic method, or than a naive
baseline?" It never produces buy/sell/hold output or a price forecast.
"""

EXPERIMENTAL_NOTICE = (
    "EXPERIMENTAL. Offline research output, not part of the scoring system. "
    "Not investment advice, not a recommendation, not a forecast of returns. "
    "It does not replace or alter any stored analysis or score."
)
