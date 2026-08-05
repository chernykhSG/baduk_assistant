from typing import Literal

from pydantic import BaseModel


class Finding(BaseModel):
    finding_id: str
    type: Literal["weak_group"]
    turn_number: int
    stones: list[tuple[int, int]]
    weak_score: float
    own_certainty: float
    boundary_certainty: float
    liberties: int
    severity: Literal["low", "medium", "high"]
    confidence: float
