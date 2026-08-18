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

RAG_SEARCH_INSTRUCTIONS = """\
У тебя есть доступ к базе знаний Го через retrieve_knowledge. Если находка \
напоминает известный принцип или распространённую ошибку, поиск поможет дать \
более обоснованное объяснение. Если сомневаешься - лучше поискать. Если явной \
связи с базой знаний нет - отвечай record_explanation сразу, без поиска.
"""

EXPLANATION_WITH_RAG_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        **EXPLANATION_TOOL_PARAMETERS["properties"],  # summary, claims
        "rag_doc_id": {"type": ["string", "null"]},
    },
    "required": ["summary", "claims"],
}

RAG_DECISION_TOOL_PARAMETERS = {
    "oneOf": [
        {
            "type": "object",
            "properties": {"tool": {"const": "retrieve_knowledge"}},
            "required": ["tool"],
        },
        {
            "type": "object",
            "properties": {
                "tool": {"const": "record_explanation"},
                **EXPLANATION_WITH_RAG_TOOL_PARAMETERS["properties"],
            },
            "required": ["tool", "summary", "claims"],
        },
    ]
}


RAG_TOP_K = 3


def build_rag_query(finding: Finding) -> str:
    match finding.type:
        case "weak_group":
            return "слабая группа камней с недостатком глаз и территории"
        case "mistake":
            return f"ошибка хода, потеря очков на стадии {finding.stage}"
        case "opening_loss":
            return "ошибки в дебюте, потеря очков в начале партии"
        case _:
            raise AssertionError(f"unhandled finding type: {finding.type}")


def build_user_prompt(finding: Finding, analysis: AnalyzeResponse, board_size: int) -> str:
    root = (
        f"rootInfo: winrate={analysis.rootInfo.winrate}, scoreLead={analysis.rootInfo.scoreLead}, "
        f"visits={analysis.rootInfo.visits}\n"
        "Объясни эту находку игроку через record_explanation."
    )
    match finding.type:
        case "weak_group":
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
        case "mistake":
            color_ru = "чёрных" if finding.color == "B" else "белых"
            return (
                f"Находка о ходе {color_ru} (finding_id={finding.finding_id}):\n"
                f"Сыгранный ход: {finding.move} (ход №{finding.turn_number}, стадия: {finding.stage})\n"
                f"delta_score={finding.delta_score}, confidence={finding.confidence}\n"
                "(scoreLead и winrate - всегда с точки зрения чёрных; delta_score - потеря очков "
                "для игрока, сделавшего ход)\n"
                f"{root}"
            )
        case "opening_loss":
            color_ru = "чёрных" if finding.color == "B" else "белых"
            return (
                f"Находка о накопленной потере очков {color_ru} в дебюте "
                f"(finding_id={finding.finding_id}):\n"
                f"Диапазон ходов: {finding.move_range[0]}-{finding.move_range[1]}\n"
                f"delta_score={finding.delta_score} (суммарная потеря очков за диапазон), "
                f"confidence={finding.confidence}\n"
                "(scoreLead и winrate - всегда с точки зрения чёрных; delta_score - суммарная "
                "потеря очков для игрока за диапазон ходов)\n"
                f"{root}"
            )
        case _:
            raise AssertionError(f"unhandled finding type: {finding.type}")


ASK_SYSTEM_PROMPT = """\
Ты - тренер по игре в го, отвечающий на вопрос игрока кю-уровня о текущей \
позиции на русском языке. Тебе даны числа из анализа KataGo для этой позиции \
и, возможно, для нескольких ходов-кандидатов. Правила:
1. Обязательно цитируй числа только из переданных данных через инструмент \
record_answer - никогда не выдумывай новые числа.
2. Каждое утверждение (claim) должно ссылаться на конкретное поле (winrate, \
scoreLead, visits или prior) и точное число из данных; если утверждение о \
конкретном ходе-кандидате, укажи его координату в cited_move, иначе оставь \
cited_move пустым (null) - тогда утверждение сверяется с общей оценкой позиции.
3. Отвечай по существу вопроса игрока, не уходи в сторону.
4. Никогда не переоценивай позицию против чисел KataGo - твоя роль объяснить \
то, что уже посчитал движок, а не заново оценить позицию.
"""

ANSWER_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "description": "Ответ на вопрос игрока на русском."},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cited_field": {
                        "type": "string",
                        "enum": ["winrate", "scoreLead", "visits", "prior"],
                    },
                    "cited_number": {"type": "number"},
                    "cited_move": {"type": ["string", "null"]},
                },
                "required": ["cited_field", "cited_number"],
            },
        },
    },
    "required": ["answer", "claims"],
}

ANSWER_WITH_RAG_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        **ANSWER_TOOL_PARAMETERS["properties"],  # answer, claims
        "rag_doc_id": {"type": ["string", "null"]},
    },
    "required": ["answer", "claims"],
}

ASK_DECISION_TOOL_PARAMETERS = {
    "oneOf": [
        {
            "type": "object",
            "properties": {"tool": {"const": "retrieve_knowledge"}},
            "required": ["tool"],
        },
        {
            "type": "object",
            "properties": {
                "tool": {"const": "record_answer"},
                **ANSWER_WITH_RAG_TOOL_PARAMETERS["properties"],
            },
            "required": ["tool", "answer", "claims"],
        },
    ]
}

# Cap on how many candidate moves are rendered into the prompt - moveInfos is
# already sorted by KataGo's own ranking (most-visited first), the same
# assumption feature_extraction/weak_group.py's pv_focus_top_k relies on.
ASK_TOP_MOVE_INFOS = 5


def build_ask_user_prompt(question: str, analysis: AnalyzeResponse, board_size: int) -> str:
    root = (
        f"rootInfo (общая оценка позиции): winrate={analysis.rootInfo.winrate}, "
        f"scoreLead={analysis.rootInfo.scoreLead}, visits={analysis.rootInfo.visits}\n"
    )
    top_moves = analysis.moveInfos[:ASK_TOP_MOVE_INFOS]
    if top_moves:
        move_lines = [
            f"- {m.move}: winrate={m.winrate}, scoreLead={m.scoreLead}, visits={m.visits}, prior={m.prior}"
            for m in top_moves
        ]
        moves_block = "Ходы-кандидаты (moveInfos):\n" + "\n".join(move_lines) + "\n"
    else:
        moves_block = ""
    return f"{root}{moves_block}Вопрос игрока: {question}\nОтветь на вопрос через record_answer."
