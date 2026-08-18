from typing import Literal

from pydantic import BaseModel, Field, model_validator

from baduk_backend.feature_extraction.config_loader import DEFAULT_CONFIG
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.schemas import Explanation


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


class ExplainRequest(BaseModel):
    moves: list[list[str]] = Field(default_factory=list)
    boardXSize: int = Field(ge=2, le=25)
    boardYSize: int = Field(ge=2, le=25)
    analysis: AnalyzeResponse
    analysisAfter: AnalyzeResponse | None = None
    nextMove: tuple[Literal["B", "W"], str] | None = None

    @model_validator(mode="after")
    def _ownership_matches_board_size(self) -> "ExplainRequest":
        ownership = self.analysis.ownership
        if ownership is not None and len(ownership) != self.boardXSize * self.boardYSize:
            raise ValueError(
                "analysis.ownership length must equal boardXSize * boardYSize "
                f"({self.boardXSize * self.boardYSize}), got {len(ownership)}"
            )
        return self

    @model_validator(mode="after")
    def _analysis_after_and_next_move_together(self) -> "ExplainRequest":
        if (self.analysisAfter is None) != (self.nextMove is None):
            raise ValueError("analysisAfter and nextMove must both be set or both be None")
        return self


class OpeningTurnEval(BaseModel):
    turnNumber: int
    scoreLead: float
    visits: int


class ExplainOpeningRequest(BaseModel):
    moves: list[list[str]] = Field(default_factory=list)
    boardXSize: int = Field(ge=2, le=25)
    boardYSize: int = Field(ge=2, le=25)
    color: Literal["B", "W"]
    openingSequence: list[OpeningTurnEval]
    analysisAtEnd: AnalyzeResponse

    @model_validator(mode="after")
    def _sequence_matches_opening_window(self) -> "ExplainOpeningRequest":
        board_area = self.boardXSize * self.boardYSize
        window_end = min(int(board_area * DEFAULT_CONFIG.k_open), len(self.moves))
        expected_turns = list(range(window_end + 1))
        got_turns = [t.turnNumber for t in self.openingSequence]
        if got_turns != expected_turns:
            raise ValueError(f"openingSequence must cover turns {expected_turns}, got {got_turns}")
        return self


class RagCitation(BaseModel):
    doc_id: str
    title: str
    source: str
    text_snippet: str


class ExplainResponse(BaseModel):
    finding: Finding | None = None
    explanation: Explanation | None = None
    verified: bool | None = None
    message: str | None = None
    citation: RagCitation | None = None


class AskRequest(BaseModel):
    moves: list[list[str]] = Field(default_factory=list)
    boardXSize: int = Field(ge=2, le=25)
    boardYSize: int = Field(ge=2, le=25)
    analysis: AnalyzeResponse
    question: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _ownership_matches_board_size(self) -> "AskRequest":
        ownership = self.analysis.ownership
        if ownership is not None and len(ownership) != self.boardXSize * self.boardYSize:
            raise ValueError(
                "analysis.ownership length must equal boardXSize * boardYSize "
                f"({self.boardXSize * self.boardYSize}), got {len(ownership)}"
            )
        return self


class AskResponse(BaseModel):
    answer: str | None = None
    verified: bool | None = None
    message: str | None = None
    citation: RagCitation | None = None
