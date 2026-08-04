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


class AnalyzeRequest(BaseModel):
    moves: list[list[str]] = Field(default_factory=list)
    rules: str
    komi: float
    boardXSize: int
    boardYSize: int
    analyzeTurns: list[int] = Field(min_length=1, max_length=1)
    maxVisits: int
    includeOwnership: bool = False


class AnalyzeResponse(BaseModel):
    id: str
    turnNumber: int | None = None
    moveInfos: list[MoveInfo]
    rootInfo: RootInfo
    ownership: list[float] | None = None


class StreamAnalyzeRequest(BaseModel):
    moves: list[list[str]] = Field(default_factory=list)
    rules: str
    komi: float
    boardXSize: int
    boardYSize: int
    turnNumbers: list[int] = Field(min_length=1)
    maxVisits: int
    includeOwnership: bool = False


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
