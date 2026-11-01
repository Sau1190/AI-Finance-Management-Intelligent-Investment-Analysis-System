"""Generate API-shaped fixtures for the dashboard browser test by running the REAL
backend calculation code (the parts that need no database or web framework):
fundamentals, sentiment, technical, risk, scoring and the Phase 11 explanation.

Run from the project root:   python frontend/e2e/make_fixtures.py
Needs pandas (already in backend/requirements.txt). Writes frontend/e2e/fixtures.json.
"""
import csv
import io
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import pandas as pd  # noqa: E402

from app.services import (  # noqa: E402
    explanation_builder, financial_normalization as fn, fundamental_metrics as fm, risk_report,
    scoring_config as cfg, scoring_engine, sentiment_engine, technical_report,
)

# The same sample the dashboard creates (frontend/src/lib/sample.js).
sample_js = (ROOT / "frontend/src/lib/sample.js").read_text()
csv_lines = sample_js.split("export const SAMPLE_CSV = [")[1].split("].join")[0]
SAMPLE_CSV = "\n".join(l.strip().strip(",").strip('"') for l in csv_lines.strip().splitlines() if l.strip().startswith('"'))
head_block = sample_js.split("export const SAMPLE_HEADLINES = [")[1].split("].join")[0]
HEADLINES = [l.strip().rstrip(",").strip('"') for l in head_block.strip().splitlines() if l.strip().startswith('"')]
NOW = "2025-01-10T12:00:00+00:00"

# ---- Fundamentals (real Phase 5 code on the real Phase 2 normalisation) ----
raw = pd.read_csv(io.StringIO(SAMPLE_CSV), dtype=str)
mapping, ambiguous = fn.build_normalization_mapping(list(raw.columns))
cleaned = raw.rename(columns=mapping)
sheet, metrics_csv = fm.analyze_sheet(cleaned, ambiguous)
sheet["sheet_name"] = "sample_financials_AAA"
sheet["metrics_storage_key"] = "analysis/fundamentals-demo.csv"
metric_rows = list(csv.DictReader(io.StringIO(metrics_csv)))
latest = max(metric_rows, key=lambda r: r["date"])

# ---- Sentiment (real Phase 8 engine) ----
items = []
for i, text in enumerate(HEADLINES):
    s = sentiment_engine.score_text(text)
    items.append({"index": i, "text": text, "text_truncated": False, "source": None, "published_at": None, "url": None, **s})
agg = sentiment_engine.aggregate([{"score": it["score"], "label": it["label"]} for it in items])
sentiment = {
    "id": "sent-1", "symbol": "AAA", "source_type": "TEXT", "provider": None, "query": None, "status": "COMPLETE",
    "created_at": NOW, "error_code": None, "error_message": None, "lexicon_version": "demo", "received_count": len(items),
    "duplicates_removed": 0, "skipped": {}, **agg, "earliest_published": None, "latest_published": None, "items": items,
}

# ---- Prices -> technical + risk (real Phase 7 / 9 code) ----
bars = []
price = 100.0
import random
rng = random.Random(7)
d = pd.Timestamp("2024-01-02")
while len(bars) < 260:
    if d.weekday() < 5:
        price *= 1 + rng.gauss(0.0004, 0.012)
        o = price * (1 + rng.gauss(0, 0.002))
        bars.append({"date": d.strftime("%Y-%m-%d"), "open": round(o, 4), "high": round(max(o, price) * 1.004, 4),
                     "low": round(min(o, price) * 0.996, 4), "close": round(price, 4), "volume": 1000000 + rng.randint(0, 500000)})
    d += pd.Timedelta(days=1)
tech_indicators, tech_rows, _ = technical_report.build_report(bars)
risk_metrics, risk_warnings, n_returns = risk_report.build_report("AAA", bars)

# ---- Scoring + explanation (real Phase 10 / 11 code) ----
def fundamental_input():
    values, missing = {}, {}
    for ind in cfg.COMPONENTS["fundamental"]["indicators"]:
        v = latest.get(ind["key"], "")
        if v not in ("", None):
            values[ind["key"]] = float(v)
        else:
            missing[ind["key"]] = "The latest period has no value for this metric."
    return {"unavailable_reason": None, "values": values, "missing": missing, "warnings": [], "as_of": latest["date"],
            "source_ref": {"kind": "fundamental", "file_id": "file-1", "sheet_name": sheet["sheet_name"]}}

def sentiment_input():
    return {"unavailable_reason": None, "values": {"sentiment_mean": agg["mean_score"]}, "missing": {}, "warnings": [],
            "as_of": None, "source_ref": {"kind": "sentiment", "result_id": "sent-1"}}

def build_score(component_inputs, weights, score_id):
    full = {k: component_inputs.get(k, {"unavailable_reason": f"No successful {k} analysis exists for AAA. Run it first."}) for k in cfg.COMPONENT_ORDER}
    built = scoring_engine.build_scores(full, weights)
    rec = {"id": score_id, "symbol": "AAA", "file_id": "file-1" if "fundamental" in component_inputs else None,
           "sheet_name": None, "status": "COMPLETE", "created_at": NOW, "error_code": None, "error_message": None,
           "scoring_version": cfg.SCORING_VERSION, "notice": cfg.NOTICE, "weights": built["weights"],
           "weights_customised": weights is not None, "overall": built["overall"], "components": built["components"],
           "warnings": [], "method": cfg.describe_method(built["weights"])}
    return rec, explanation_builder.build_explanation({**rec})

score_one, expl_one = build_score({"sentiment": sentiment_input()}, None, "score-3")
CUSTOM = {"fundamental": 3, "technical": 1, "sentiment": 1, "risk": 1}
score_default, expl_default = build_score({"fundamental": fundamental_input(), "sentiment": sentiment_input()}, None, "score-1")
score_custom, expl_custom = build_score({"fundamental": fundamental_input(), "sentiment": sentiment_input()}, CUSTOM, "score-2")

def check(cond, msg):
    if not cond:
        raise SystemExit("FIXTURE CHECK FAILED: " + msg)

check(sentiment["scored_count"] >= cfg.MIN_SENTIMENT_SCORED_TEXTS, f"sample headlines: only {sentiment['scored_count']} carry a signal")
check({"net_profit_margin", "debt_to_equity", "liabilities_to_assets"} <= set(fundamental_input()["values"]), "sample CSV does not yield the 3 fundamentals used by the score")
check(score_default["overall"]["score"] is not None, "sample path produces no overall score")
check(score_one["overall"]["score"] is None, "single component must not produce an overall score")
check(expl_default["how"]["arithmetic_check"]["matches"], "explanation arithmetic mismatch")

out = {
    "sample_csv": SAMPLE_CSV, "headlines": HEADLINES, "sheet": sheet, "sentiment": sentiment,
    "bars": bars, "tech_indicators": tech_indicators, "tech_rows": tech_rows,
    "risk_metrics": risk_metrics, "risk_warnings": risk_warnings, "risk_returns": n_returns,
    "score_default": score_default, "expl_default": expl_default, "score_custom": score_custom, "expl_custom": expl_custom,
    "score_one": score_one, "expl_one": expl_one, "custom_weights": CUSTOM, "scoring_method": cfg.describe_method(),
}
Path(__file__).with_name("fixtures.json").write_text(json.dumps(out, default=str, indent=1, allow_nan=False))
print("fixtures ok:", f"overall={score_default['overall']['score']:.2f} custom={score_custom['overall']['score']:.2f}",
      f"fund_values={fundamental_input()['values']}", f"sentiment scored={sentiment['scored_count']}/{sentiment['text_count']} mean={agg['mean_score']}")
