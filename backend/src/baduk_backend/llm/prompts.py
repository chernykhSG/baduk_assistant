from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.board.gtp_coords import xy_to_gtp
from baduk_backend.feature_extraction.schemas import Finding

SYSTEM_PROMPT = """\
Ты - тренер по игре в го, объясняющий позицию игроку кю-уровня на русском языке.
Тебе дана находка о позиции и числа из анализа KataGo. Правила:
1. Обязательно цитируй числа только из переданных данных через инструмент \
record_explanation - никогда не выдумывай новые числа.
2. Каждое утверждение (claim) должно ссылаться на конкретное поле находки \
и точное число из данных.
3. Если уверенность (confidence) находки ниже 0.7, используй смягчающий \
язык ("похоже", "вероятно", "возможно").
4. Никогда не переоценивай позицию против чисел KataGo - твоя роль объяснить \
то, что уже посчитал движок, а не заново оценить позицию.
"""

EXPLANATION_TOOL_NAME = "record_explanation"
EXPLANATION_TOOL_DESCRIPTION = "Записывает структурированное объяснение находки для игрока."
EXPLANATION_TOOL_PARAMETERS = {
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
                            "delta_score",
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
}


def build_user_prompt(finding: Finding, analysis: AnalyzeResponse, board_size: int) -> str:
    root = (
        f"rootInfo: winrate={analysis.rootInfo.winrate}, scoreLead={analysis.rootInfo.scoreLead}, "
        f"visits={analysis.rootInfo.visits}\n"
        "Объясни эту находку игроку через record_explanation."
    )
    if finding.type == "weak_group":
        color_ru = "чёрных" if finding.color == "B" else "белых"
        coords = ", ".join(xy_to_gtp(x, y, board_size) for x, y in finding.stones)
        return (
            f"Находка о слабой группе {color_ru} (finding_id={finding.finding_id}):\n"
            f"Камни группы: {coords}\n"
            f"weak_score={finding.weak_score}, own_certainty={finding.own_certainty}, "
            f"boundary_certainty={finding.boundary_certainty}, liberties={finding.liberties}, "
            f"confidence={finding.confidence}, turn_number={finding.turn_number}\n"
            f"{root}"
        )
    color_ru = "чёрных" if finding.color == "B" else "белых"
    return (
        f"Находка о ходе {color_ru} (finding_id={finding.finding_id}):\n"
        f"Сыгранный ход: {finding.move} (ход №{finding.turn_number}, стадия: {finding.stage})\n"
        f"delta_score={finding.delta_score}, confidence={finding.confidence}\n"
        "(scoreLead и winrate - всегда с точки зрения чёрных; delta_score - потеря очков "
        "для игрока, сделавшего ход)\n"
        f"{root}"
    )
