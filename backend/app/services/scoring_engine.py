"""Deterministic, explainable scoring arithmetic.

Beginner view:
  Take indicator values that earlier phases already computed, place each one
  on a 0-100 scale between a "poor" and a "good" reference value, average
  them within each component, then combine the components using weights. Every
  step is recorded so the final number can be traced back, point by point, to
  the inputs that produced it. The score summarises; it does not advise.

Technical view:
  Pure functions, no I/O, no randomness, no model. The method (indicators,
  anchors, thresholds) is read from scoring_config.py. Properties the tests
  rely on:
    * sub-score = 100 * clamp((value - poor) / (good - poor), 0, 1) — linear
      between the anchors, flat beyond them (the result says when a value was
      beyond an anchor);
    * missing data is EXCLUDED and the remaining weights are renormalized; it
      is never filled in or treated as 0 or 50;
    * the overall score is computed as the sum of the per-component
      contributions, so contributions add up to the score exactly;
    * the same inputs always give the same output.
"""

import math

from app.services import scoring_config as cfg


def normalize(value: float, poor: float, good: float) -> tuple[float, str | None]:
    """Return (sub_score 0-100, saturated). `saturated` is "poor"/"good" when
    the value lies strictly beyond that anchor (so the sub-score is clipped),
    otherwise None.
    """
    t = (value - poor) / (good - poor)
    if t < 0:
        return 0.0, "poor"
    if t > 1:
        return 100.0, "good"
    return 100.0 * t, None


def resolve_weights(requested: dict | None) -> dict[str, float]:
    """Validate user weights (all four components, finite, non-negative, not
    all zero) and normalize them to sum to 1. None -> the documented defaults.
    Raises ValueError with a user-safe message.
    """
    if requested is None:
        return dict(cfg.DEFAULT_WEIGHTS)
    if set(requested) != set(cfg.COMPONENT_ORDER):
        raise ValueError(
            "Weights must be given for exactly these components: " + ", ".join(cfg.COMPONENT_ORDER) + "."
        )
    cleaned: dict[str, float] = {}
    for key in cfg.COMPONENT_ORDER:
        value = requested[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"The weight for '{key}' must be a finite number that is zero or greater.")
        cleaned[key] = float(value)
    total = sum(cleaned.values())
    if total <= 0:
        raise ValueError("At least one weight must be greater than zero.")
    return {key: cleaned[key] / total for key in cfg.COMPONENT_ORDER}


def _indicator_row(spec: dict, value: float | None, missing_reason: str | None) -> dict:
    row = {
        "key": spec["key"],
        "label": spec["label"],
        "note": spec["note"],
        "unit": spec["unit"],
        "poor": spec["poor"],
        "good": spec["good"],
        "direction": "higher_is_better" if spec["good"] > spec["poor"] else "lower_is_better",
        "status": "MISSING",
        "reason": missing_reason or "No value available.",
        "value": None,
        "sub_score": None,
        "saturated": None,
        "weight_in_component": None,
        "contribution_to_component": None,
    }
    if value is not None:
        sub, saturated = normalize(float(value), spec["poor"], spec["good"])
        row.update(status="AVAILABLE", reason=None, value=float(value), sub_score=sub, saturated=saturated)
    return row


def score_component(key: str, inputs: dict) -> dict:
    """Score one component.

    `inputs`: {"unavailable_reason": str|None, "as_of": str|None,
               "source_ref": dict, "warnings": list[str],
               "values": {indicator_key: float|None},
               "missing": {indicator_key: reason}}
    """
    spec = cfg.COMPONENTS[key]
    unavailable_reason = inputs.get("unavailable_reason")
    values = {} if unavailable_reason else inputs.get("values", {})
    missing = inputs.get("missing", {})

    rows = [
        _indicator_row(
            ind,
            values.get(ind["key"]),
            unavailable_reason or missing.get(ind["key"]),
        )
        for ind in spec["indicators"]
    ]
    available = [r for r in rows if r["status"] == "AVAILABLE"]

    status, reason, score = "AVAILABLE", None, None
    if unavailable_reason:
        status, reason = "UNAVAILABLE", unavailable_reason
    elif len(available) < spec["min_indicators"]:
        status = "UNAVAILABLE"
        reason = (
            f"Only {len(available)} of {len(rows)} indicators are available; "
            f"at least {spec['min_indicators']} are needed."
        )
    else:
        weight = 1.0 / len(available)
        for row in available:
            row["weight_in_component"] = weight
            row["contribution_to_component"] = row["sub_score"] * weight
        score = sum(row["contribution_to_component"] for row in available)

    return {
        "key": key,
        "label": spec["label"],
        "source": spec["source"],
        "status": status,
        "reason": reason,
        "score": score,
        "as_of": inputs.get("as_of"),
        "source_ref": inputs.get("source_ref") or {},
        "warnings": list(inputs.get("warnings", [])),
        "min_indicators": spec["min_indicators"],
        "available_indicators": len(available),
        "total_indicators": len(rows),
        "indicators": rows,
        "weight_configured": None,
        "weight_effective": None,
        "contribution_to_overall": None,
        "in_overall": False,
    }


def combine(components: list[dict], weights: dict[str, float]) -> dict:
    """Combine component scores into the overall score (mutates the component
    dicts to add their weights and contributions) and return the overall block.
    """
    for component in components:
        component["weight_configured"] = weights[component["key"]]

    contributing = [c for c in components if c["status"] == "AVAILABLE" and weights[c["key"]] > 0]
    coverage = float(sum(weights[c["key"]] for c in contributing))
    excluded: dict[str, str] = {}
    for c in components:
        if c in contributing:
            continue
        if c["status"] != "AVAILABLE":
            excluded[c["key"]] = c["reason"] or "Unavailable."
        else:
            excluded[c["key"]] = "Weight is 0, so it does not contribute."

    overall = {
        "score": None,
        "reason": None,
        "weight_coverage": coverage,
        "contributing_components": [c["key"] for c in contributing],
        "excluded_components": excluded,
    }
    if len(contributing) < cfg.MIN_COMPONENTS_FOR_OVERALL:
        overall["reason"] = (
            f"Only {len(contributing)} component(s) contributed; at least "
            f"{cfg.MIN_COMPONENTS_FOR_OVERALL} are needed for an overall score."
        )
        return overall
    if coverage < cfg.MIN_WEIGHT_COVERAGE_FOR_OVERALL:
        overall["reason"] = (
            f"The contributing components carry {coverage:.0%} of the configured weight; "
            f"at least {cfg.MIN_WEIGHT_COVERAGE_FOR_OVERALL:.0%} is needed for an overall score."
        )
        return overall

    for c in contributing:
        c["in_overall"] = True
        c["weight_effective"] = weights[c["key"]] / coverage
        c["contribution_to_overall"] = c["weight_effective"] * c["score"]
    overall["score"] = float(sum(c["contribution_to_overall"] for c in contributing))
    return overall


def build_scores(component_inputs: dict[str, dict], requested_weights: dict | None = None) -> dict:
    """Score every component and combine them. Returns
    {"weights", "components", "overall"}.
    """
    weights = resolve_weights(requested_weights)
    components = [score_component(key, component_inputs.get(key, {"unavailable_reason": "No input was provided."}))
                  for key in cfg.COMPONENT_ORDER]
    overall = combine(components, weights)
    return {"weights": weights, "components": components, "overall": overall}
