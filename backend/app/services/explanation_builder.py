"""Phase 11: turn one stored Phase 10 score into a What / How / Why explanation.

Pure functions, no database, no network, no LLM. Every sentence is produced by
a fixed template from fields that are already in the stored score, so the
explanation can never contain a number or claim that the score does not. It
re-derives the overall score from the stored indicator rows as a cross-check
and reports whether it matches; a mismatch is shown, never hidden.

  WHAT - what the score is and what it came out as (including coverage and
         what was left out).
  HOW  - exactly how each number was produced: input value, anchors,
         sub-score, weights, and the arithmetic that adds up to the total.
  WHY  - why the number came out as it did (which inputs added and which cost
         the most points), why each indicator is in the method, why anything
         was excluded, and the assumptions and limits behind it.

What this is NOT: it does not interpret the score, grade it, or recommend any
action. It describes the method and its arithmetic. Wording that would sound
like advice (buy, sell, hold, recommend, should, attractive, ...) must not
appear outside the fixed disclaimer and limits; tests guard this.
"""

TEMPLATE_VERSION = "1"

TOLERANCE = 1e-6  # arithmetic cross-check tolerance, in score points

_COMPONENT_LABELS = {
    "fundamental": "Fundamentals",
    "technical": "Technical",
    "sentiment": "Sentiment",
    "risk": "Risk",
}


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_value(value: float, unit: str) -> str:
    """Format a value in the unit its indicator is defined in."""
    if unit == "fraction":
        return f"{value * 100:.1f}%"
    if unit.startswith("score"):
        return f"{value:+.2f}"
    return f"{value:.2f}"


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _pts(x: float) -> str:
    return f"{x:.1f}"


# ---------------------------------------------------------------------------
# Per-indicator sentences
# ---------------------------------------------------------------------------


def _anchor_sentence(ind: dict) -> str:
    poor = format_value(ind["poor"], ind["unit"])
    good = format_value(ind["good"], ind["unit"])
    direction = (
        "a higher value is treated as more favourable"
        if ind["direction"] == "higher_is_better"
        else "a lower value is treated as more favourable"
    )
    return f"The method maps {poor} to 0 and {good} to 100 in a straight line ({direction})."


def how_indicator(ind: dict) -> str:
    if ind["status"] != "AVAILABLE":
        return f"{ind['label']}: not used. {ind.get('reason') or 'No value available.'}"
    value = format_value(ind["value"], ind["unit"])
    parts = [f"{ind['label']} was {value} ({ind['note']}).", _anchor_sentence(ind)]
    if ind.get("saturated") == "good":
        parts.append("The value is beyond the 100-point anchor, so the sub-score is capped at 100.")
    elif ind.get("saturated") == "poor":
        parts.append("The value is beyond the 0-point anchor, so the sub-score is floored at 0.")
    if ind.get("weight_in_component") is None:
        # The indicator had a value, but its component was unavailable (too few
        # indicators), so the value carries no weight anywhere.
        parts.append(
            f"Sub-score {_pts(ind['sub_score'])}, but its component was unavailable, so this value carries no weight."
        )
    else:
        parts.append(
            f"Sub-score {_pts(ind['sub_score'])}; weight inside its component {_pct(ind['weight_in_component'])}."
        )
    return " ".join(parts)


def _indicator_points(component: dict, ind: dict) -> tuple[float, float] | None:
    """(points contributed to the overall score, points lost versus a perfect
    100) for one indicator, or None when it is not in the overall score.
    """
    if not component.get("in_overall") or ind["status"] != "AVAILABLE":
        return None
    share = component["weight_effective"] * ind["weight_in_component"]
    return ind["sub_score"] * share, (100.0 - ind["sub_score"]) * share


# ---------------------------------------------------------------------------
# Cross-check
# ---------------------------------------------------------------------------


def recompute_overall(components: list[dict]) -> float | None:
    """Re-derive the overall score from indicator rows and effective weights
    only (not from the stored component scores or contributions).
    """
    total = 0.0
    any_in = False
    for comp in components:
        if not comp.get("in_overall"):
            continue
        any_in = True
        for ind in comp["indicators"]:
            if ind["status"] == "AVAILABLE":
                total += ind["sub_score"] * ind["weight_in_component"] * comp["weight_effective"]
    return total if any_in else None


def arithmetic_check(stored_overall: float | None, components: list[dict]) -> dict:
    recomputed = recompute_overall(components)
    if stored_overall is None or recomputed is None:
        return {
            "stored_overall": stored_overall,
            "recomputed_overall": recomputed,
            "difference": None,
            "matches": stored_overall is None and recomputed is None,
        }
    diff = abs(stored_overall - recomputed)
    return {
        "stored_overall": stored_overall,
        "recomputed_overall": recomputed,
        "difference": diff,
        "matches": diff <= TOLERANCE,
    }


# ---------------------------------------------------------------------------
# The three sections
# ---------------------------------------------------------------------------


def _label(key: str, components: list[dict]) -> str:
    for c in components:
        if c["key"] == key:
            return c["label"]
    return _COMPONENT_LABELS.get(key, key)


def build_what(score: dict) -> dict:
    overall = score["overall"]
    components = score["components"]
    sym = score["symbol"]

    if overall.get("score") is not None:
        summary = (
            f"For {sym}, the explainable score is {overall['score']:.1f} out of 100, built from "
            f"{len(overall['contributing_components'])} of {len(components)} components covering "
            f"{_pct(overall['weight_coverage'])} of the configured weight. It is a summary of how "
            "already-computed indicators sit against fixed reference ranges; it is not a rating, "
            "a forecast or advice."
        )
    else:
        summary = (
            f"For {sym}, no overall score could be produced. {overall.get('reason') or ''} "
            "The components that could be scored are shown below."
        ).replace("  ", " ")

    rows = []
    for c in components:
        if c["status"] == "AVAILABLE":
            sentence = (
                f"{c['label']} scored {_pts(c['score'])} from {c['available_indicators']} of "
                f"{c['total_indicators']} indicators"
                + (f", as of {c['as_of']}" if c.get("as_of") else "")
                + "."
            )
            if not c.get("in_overall"):
                sentence += " It does not count toward the overall score (weight 0 or overall not produced)."
        else:
            sentence = f"{c['label']} was not scored. {c.get('reason') or ''}".strip()
        rows.append(
            {"key": c["key"], "label": c["label"], "status": c["status"], "score": c["score"], "sentence": sentence}
        )

    return {
        "summary": summary,
        "overall_score": overall.get("score"),
        "weight_coverage": overall.get("weight_coverage"),
        "contributing_components": list(overall.get("contributing_components", [])),
        "excluded_components": dict(overall.get("excluded_components", {})),
        "components": rows,
    }


def build_how(score: dict) -> dict:
    components = score["components"]
    weights = score["weights"]
    overall = score["overall"]

    kind = "custom" if score.get("weights_customised") else "default equal"
    weight_text = ", ".join(f"{_label(k, components)} {_pct(w)}" for k, w in weights.items())

    steps = [
        "Step 1 - Each indicator value is read exactly as stored by the earlier phase; nothing is recomputed or repaired.",
        "Step 2 - Each value becomes a 0-100 sub-score: 100 x clamp((value - poor) / (good - poor), 0, 1). "
        "The value at the 'poor' anchor scores 0, at the 'good' anchor 100, linear in between, flat beyond.",
        "Step 3 - A component score is the equal-weighted mean of the sub-scores that are available; a missing "
        "indicator is dropped and the rest are re-weighted, never filled in.",
        f"Step 4 - Component weights ({kind}): {weight_text}. Components that are unavailable or weight 0 are "
        "left out and the remaining weights are rescaled to sum to 100%.",
        "Step 5 - The overall score is the sum of (effective weight x component score) over contributing components.",
    ]

    comp_rows = []
    for c in components:
        entry = {
            "key": c["key"],
            "label": c["label"],
            "status": c["status"],
            "score": c["score"],
            "weight_configured": c["weight_configured"],
            "weight_effective": c["weight_effective"],
            "contribution_to_overall": c["contribution_to_overall"],
            "source": c["source"],
            "source_ref": c["source_ref"],
            "indicators": [{"key": i["key"], "label": i["label"], "sentence": how_indicator(i)} for i in c["indicators"]],
        }
        if c["status"] == "AVAILABLE" and c.get("in_overall"):
            entry["sentence"] = (
                f"{c['label']}: component score {_pts(c['score'])} x effective weight "
                f"{_pct(c['weight_effective'])} = {_pts(c['contribution_to_overall'])} points of the overall score."
            )
        elif c["status"] == "AVAILABLE":
            entry["sentence"] = f"{c['label']}: component score {_pts(c['score'])}; not part of the overall score."
        else:
            entry["sentence"] = f"{c['label']}: unavailable. {c.get('reason') or ''}".strip()
        comp_rows.append(entry)

    check = arithmetic_check(overall.get("score"), components)
    if overall.get("score") is None:
        check_sentence = "There is no overall score, so there is no arithmetic to check."
    elif check["matches"]:
        check_sentence = (
            f"Cross-check: re-deriving the overall score from the indicator rows gives "
            f"{check['recomputed_overall']:.4f}, which matches the stored {check['stored_overall']:.4f}."
        )
    else:
        check_sentence = (
            f"Cross-check FAILED: re-deriving the overall score gives {check['recomputed_overall']:.4f} but the "
            f"stored value is {check['stored_overall']:.4f}. Treat this score as unreliable."
        )

    return {
        "steps": steps,
        "components": comp_rows,
        "arithmetic_check": {**check, "sentence": check_sentence},
        "method_version": score["scoring_version"],
    }


def build_why(score: dict) -> dict:
    components = score["components"]
    overall = score["overall"]
    method_components = (score.get("method") or {}).get("components", {})

    contributions = []  # (points_added, points_lost, component, indicator)
    for c in components:
        for ind in c["indicators"]:
            pts = _indicator_points(c, ind)
            if pts is not None:
                contributions.append((pts[0], pts[1], c, ind))

    def drivers(index: int, label_fn) -> list[dict]:
        ranked = sorted(contributions, key=lambda t: (-t[index], t[3]["key"]))
        out = []
        for t in ranked[:3]:
            c, ind = t[2], t[3]
            out.append(
                {
                    "component": c["key"],
                    "indicator": ind["key"],
                    "points": t[index],
                    "sentence": label_fn(c, ind, t[index]),
                }
            )
        return out

    largest_contributors = drivers(
        0,
        lambda c, i, p: (
            f"{i['label']} ({format_value(i['value'], i['unit'])}) added {_pts(p)} points "
            f"(sub-score {_pts(i['sub_score'])})."
        ),
    )
    largest_losses = drivers(
        1,
        lambda c, i, p: (
            f"{i['label']} ({format_value(i['value'], i['unit'])}) cost {_pts(p)} points versus a "
            f"sub-score of 100 (its sub-score was {_pts(i['sub_score'])})."
        ),
    )
    if overall.get("score") is not None and contributions:
        total_lost = sum(t[1] for t in contributions)
        accounting = (
            f"Accounting: the overall score {overall['score']:.1f} = 100 - {_pts(total_lost)} points lost "
            "across the indicators that contributed."
        )
    else:
        accounting = None

    reasons = []
    for c in components:
        spec = method_components.get(c["key"], {})
        for ind in c["indicators"]:
            reasons.append(
                {
                    "component": c["key"],
                    "indicator": ind["key"],
                    "sentence": f"{ind['label']} is part of the method (definition: {ind['note']}).",
                }
            )
        if spec.get("excluded_on_purpose"):
            reasons.append(
                {
                    "component": c["key"],
                    "indicator": None,
                    "sentence": f"Deliberately left out of {c['label']}: {spec['excluded_on_purpose']}",
                }
            )

    missing = []
    for key, reason in overall.get("excluded_components", {}).items():
        missing.append(f"{_label(key, components)} is not in the overall score: {reason}")
    for c in components:
        if c["status"] == "AVAILABLE":
            for ind in c["indicators"]:
                if ind["status"] == "MISSING":
                    missing.append(f"{ind['label']} was not used: {ind.get('reason') or 'no value available'}")

    assumptions = [
        "'Favourable' means the end of each indicator's range that the method treats as favourable; this is a "
        "design assumption, not a finding.",
        "The 'poor' and 'good' anchors are illustrative round numbers, not calibrated on data or by industry.",
        "Equal weights are a no-information default; changing them changes the score by exactly the amounts shown.",
    ]

    return {
        "largest_contributors": largest_contributors,
        "largest_point_losses": largest_losses,
        "accounting": accounting,
        "why_these_indicators": reasons,
        "missing_or_excluded": missing,
        "assumptions": assumptions,
        "limits": list((score.get("method") or {}).get("limits", [])),
    }


def build_explanation(score: dict) -> dict:
    """`score` is a stored Phase 10 result as a plain dict (id, symbol,
    scoring_version, notice, weights, weights_customised, overall, components,
    warnings, method, created_at). Must be a COMPLETE result.
    """
    return {
        "template_version": TEMPLATE_VERSION,
        "symbol": score["symbol"],
        "score_id": score["id"],
        "scoring_version": score["scoring_version"],
        "score_created_at": score.get("created_at"),
        "notice": score["notice"],
        "what": build_what(score),
        "how": build_how(score),
        "why": build_why(score),
        "warnings": list(score.get("warnings", [])),
    }
