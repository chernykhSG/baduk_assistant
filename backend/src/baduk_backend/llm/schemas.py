from typing import Literal

from pydantic import BaseModel

CitedField = Literal[
    "weak_score",
    "own_certainty",
    "boundary_certainty",
    "liberties",
    "delta_score",
    "visits",
    "winrate",
    "scoreLead",
]


class Claim(BaseModel):
    text: str
    finding_id: str
    cited_field: CitedField
    cited_number: float


class Explanation(BaseModel):
    summary: str
    claims: list[Claim]
    rag_doc_id: str | None = None


QuestionCitedField = Literal["winrate", "scoreLead", "visits", "prior"]


class QuestionClaim(BaseModel):
    cited_field: QuestionCitedField
    cited_number: float
    # None -> the claim cites analysis.rootInfo (the position's overall
    # evaluation). A GTP move string (e.g. "Q4") -> the claim cites the
    # matching entry in analysis.moveInfos (a specific candidate move).
    cited_move: str | None = None


class QuestionAnswer(BaseModel):
    answer: str
    claims: list[QuestionClaim]
    rag_doc_id: str | None = None
