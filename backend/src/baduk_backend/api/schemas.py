from typing import Literal

from pydantic import BaseModel, Field


class MoveInfo(BaseModel):
    move: str
    winrate: float
    scoreLead: float
    visits: int
    prior: float
    pv: list[str]


class RootInfo(BaseModel):
    winrate: float
    scoreLead: float
    visits: int


class _BaseAnalyzeRequest(BaseModel):
    moves: list[list[str]] = Field(default_factory=list)
    rules: str
    komi: float = Field(ge=-150, le=150)
    boardXSize: int = Field(ge=2, le=25)
    boardYSize: int = Field(ge=2, le=25)
    maxVisits: int = Field(gt=0, le=100_000)
    includeOwnership: bool = False


class AnalyzeRequest(_BaseAnalyzeRequest):
    analyzeTurns: list[int] = Field(min_length=1, max_length=1)


class AnalyzeResponse(BaseModel):
    id: str
    turnNumber: int | None = None
    moveInfos: list[MoveInfo]
    rootInfo: RootInfo
    ownership: list[float] | None = None


class StreamAnalyzeRequest(_BaseAnalyzeRequest):
    turnNumbers: list[int] = Field(min_length=1, max_length=1000)


class ProgressMessage(BaseModel):
    type: Literal["progress"] = "progress"
    turnNumber: int
    total: int
    result: AnalyzeResponse


class DoneMessage(BaseModel):
    type: Literal["done"] = "done"


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    detail: str
