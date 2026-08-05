from typing import Protocol

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.schemas import Explanation


class LLMProvider(Protocol):
    def complete(
        self,
        finding: Finding,
        analysis: AnalyzeResponse,
        corrections: list[str] | None = None,
    ) -> Explanation: ...
