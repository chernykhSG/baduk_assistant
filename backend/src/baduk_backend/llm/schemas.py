from typing import Literal

from pydantic import BaseModel

CitedField = Literal[
    "weak_score", "own_certainty", "boundary_certainty", "liberties", "visits", "winrate", "scoreLead"
]


class Claim(BaseModel):
    text: str
    finding_id: str
    cited_field: CitedField
    cited_number: float


class Explanation(BaseModel):
    summary: str
    claims: list[Claim]
