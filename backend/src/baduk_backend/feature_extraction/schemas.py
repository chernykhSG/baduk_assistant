from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class WeakGroupFinding(BaseModel):
    finding_id: str
    type: Literal["weak_group"] = "weak_group"
    turn_number: int
    stones: list[tuple[int, int]]
    color: Literal["B", "W"]
    weak_score: float
    own_certainty: float
    boundary_certainty: float
    liberties: int
    severity: Literal["low", "medium", "high"]
    confidence: float


class MistakeFinding(BaseModel):
    finding_id: str
    type: Literal["mistake"] = "mistake"
    turn_number: int
    color: Literal["B", "W"]
    move: str
    delta_score: float
    stage: Literal["opening", "middlegame", "endgame"]
    severity: Literal["low", "medium", "high"]
    confidence: float


Finding = Annotated[Union[WeakGroupFinding, MistakeFinding], Field(discriminator="type")]
