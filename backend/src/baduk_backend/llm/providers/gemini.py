import os

from google import genai
from google.genai import types

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

DEFAULT_MODEL = "gemini-3.6-flash"

_FUNCTION_DECLARATION = types.FunctionDeclaration(
    name=EXPLANATION_TOOL_NAME,
    description=EXPLANATION_TOOL_DESCRIPTION,
    parameters=EXPLANATION_TOOL_PARAMETERS,
)


class GeminiProvider:
    def __init__(self, client: genai.Client | None = None, model: str | None = None):
        self._client = client or genai.Client(
            api_key=os.environ["BADUK_GEMINI_API_KEY"],
            http_options=types.HttpOptions(timeout=60_000),
        )
        self._model = model or os.environ.get("BADUK_GEMINI_MODEL", DEFAULT_MODEL)

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

        response = self._client.models.generate_content(
            model=self._model,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[types.Tool(function_declarations=[_FUNCTION_DECLARATION])],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode="ANY", allowed_function_names=[EXPLANATION_TOOL_NAME]
                    )
                ),
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        for call in response.function_calls or []:
            if call.name == EXPLANATION_TOOL_NAME:
                return Explanation.model_validate(call.args)
        raise RuntimeError("Gemini did not call record_explanation")
