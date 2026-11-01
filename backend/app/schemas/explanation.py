from pydantic import BaseModel


class ExplanationResponse(BaseModel):
    """What-How-Why explanation of one stored score. The three sections are
    structured dicts whose human-readable text is in their `sentence`/`summary`
    fields; see docs/EXPLANATION_MODULE.md for the shape.
    """

    template_version: str
    symbol: str
    score_id: str
    scoring_version: str
    score_created_at: str | None = None
    notice: str
    what: dict
    how: dict
    why: dict
    warnings: list[str] = []
