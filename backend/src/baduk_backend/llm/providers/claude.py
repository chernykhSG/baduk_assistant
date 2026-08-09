import os

import anthropic

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.prompts import (
    EXPLANATION_TOOL_DESCRIPTION,
    EXPLANATION_TOOL_NAME,
    EXPLANATION_TOOL_PARAMETERS,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from baduk_backend.llm.schemas import Explanation

DEFAULT_MODEL = "claude-sonnet-5"

_TOOL_SCHEMA = {
    "name": EXPLANATION_TOOL_NAME,
    "description": EXPLANATION_TOOL_DESCRIPTION,
    "input_schema": EXPLANATION_TOOL_PARAMETERS,
}


class ClaudeProvider:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str | None = None):
        self._client = client or anthropic.Anthropic(
            api_key=os.environ["BADUK_CLAUDE_API_KEY"], timeout=60.0
        )
        self._model = model or os.environ.get("BADUK_CLAUDE_MODEL", DEFAULT_MODEL)

    def complete(
        self,
        finding: Finding,
        analysis: AnalyzeResponse,
        board_size: int,
        corrections: list[str] | None = None,
    ) -> Explanation:
        user_content = build_user_prompt(finding, analysis, board_size)
        if corrections:
            user_content += "\n\nИсправь предыдущий ответ:\n" + "\n".join(corrections)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            thinking={"type": "disabled"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": EXPLANATION_TOOL_NAME},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == EXPLANATION_TOOL_NAME:
                return Explanation.model_validate(block.input)
        raise RuntimeError("Claude did not call record_explanation")
