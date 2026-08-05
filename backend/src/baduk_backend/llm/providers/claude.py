import os

import anthropic

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.board.gtp_coords import xy_to_gtp
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.schemas import Explanation

DEFAULT_MODEL = "claude-sonnet-5"

_SYSTEM_PROMPT = """\
Ты - тренер по игре в го, объясняющий позицию игроку кю-уровня на русском языке.
Тебе дана находка о слабой группе камней и числа из анализа KataGo. Правила:
1. Обязательно цитируй числа только из переданных данных через инструмент \
record_explanation - никогда не выдумывай новые числа.
2. Каждое утверждение (claim) должно ссылаться на конкретное поле \
(weak_score, own_certainty, boundary_certainty, liberties, visits, winrate \
или scoreLead) и точное число из данных.
3. Если уверенность (confidence) находки ниже 0.7, используй смягчающий \
язык ("похоже", "вероятно", "возможно").
4. Никогда не переоценивай позицию против чисел KataGo - твоя роль объяснить \
то, что уже посчитал движок, а не заново оценить позицию.
"""

_TOOL_SCHEMA = {
    "name": "record_explanation",
    "description": "Записывает структурированное объяснение слабой группы для игрока.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Объяснение на русском для игрока."},
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "finding_id": {"type": "string"},
                        "cited_field": {
                            "type": "string",
                            "enum": [
                                "weak_score",
                                "own_certainty",
                                "boundary_certainty",
                                "liberties",
                                "visits",
                                "winrate",
                                "scoreLead",
                            ],
                        },
                        "cited_number": {"type": "number"},
                    },
                    "required": ["text", "finding_id", "cited_field", "cited_number"],
                },
            },
        },
        "required": ["summary", "claims"],
    },
}


def _user_prompt(finding: Finding, analysis: AnalyzeResponse, board_size: int) -> str:
    color_ru = "чёрных" if finding.color == "B" else "белых"
    coords = ", ".join(xy_to_gtp(x, y, board_size) for x, y in finding.stones)
    return (
        f"Находка о слабой группе {color_ru} (finding_id={finding.finding_id}):\n"
        f"Камни группы: {coords}\n"
        f"weak_score={finding.weak_score}, own_certainty={finding.own_certainty}, "
        f"boundary_certainty={finding.boundary_certainty}, liberties={finding.liberties}, "
        f"confidence={finding.confidence}, turn_number={finding.turn_number}\n"
        f"rootInfo: winrate={analysis.rootInfo.winrate}, scoreLead={analysis.rootInfo.scoreLead}, "
        f"visits={analysis.rootInfo.visits}\n"
        "Объясни эту находку игроку через record_explanation."
    )


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
        user_content = _user_prompt(finding, analysis, board_size)
        if corrections:
            user_content += "\n\nИсправь предыдущий ответ:\n" + "\n".join(corrections)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            thinking={"type": "disabled"},
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "record_explanation"},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "record_explanation":
                return Explanation.model_validate(block.input)
        raise RuntimeError("Claude did not call record_explanation")
