from baduk_backend.api.schemas import AnalyzeResponse, RootInfo, MoveInfo
from baduk_backend.feature_extraction.schemas import MistakeFinding, WeakGroupFinding
from baduk_backend.llm.prompts import (
    EXPLANATION_TOOL_DESCRIPTION,
    EXPLANATION_TOOL_PARAMETERS,
    build_user_prompt,
    build_rag_query,
    ANSWER_TOOL_PARAMETERS,
    ANSWER_WITH_RAG_TOOL_PARAMETERS,
    ASK_DECISION_TOOL_PARAMETERS,
    build_ask_user_prompt,
)


def _analysis() -> AnalyzeResponse:
    return AnalyzeResponse(
        id="x", moveInfos=[], rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=250), ownership=[0.0] * 81
    )


def test_cited_field_enum_includes_delta_score_and_keeps_existing_fields():
    enum = EXPLANATION_TOOL_PARAMETERS["properties"]["claims"]["items"]["properties"]["cited_field"]["enum"]
    assert "delta_score" in enum
    assert "weak_score" in enum


def test_tool_description_is_generalized_not_weak_group_specific():
    assert "слабой группы" not in EXPLANATION_TOOL_DESCRIPTION


def test_build_user_prompt_for_weak_group_mentions_group_fields():
    finding = WeakGroupFinding(
        finding_id="f1",
        turn_number=5,
        stones=[(4, 4)],
        color="B",
        weak_score=0.85,
        own_certainty=0.0,
        boundary_certainty=0.0,
        liberties=4,
        severity="high",
        confidence=0.5,
    )
    prompt = build_user_prompt(finding, _analysis(), 9)
    assert "weak_score=0.85" in prompt
    assert "f1" in prompt


def test_build_user_prompt_for_mistake_mentions_delta_move_and_stage():
    finding = MistakeFinding(
        finding_id="f2",
        turn_number=10,
        color="W",
        move="Q4",
        delta_score=3.0,
        stage="middlegame",
        severity="medium",
        confidence=0.6,
    )
    prompt = build_user_prompt(finding, _analysis(), 9)
    assert "delta_score=3.0" in prompt
    assert "Q4" in prompt
    assert "middlegame" in prompt
    # Clarifies the two different sign conventions mixed in this branch:
    # scoreLead/winrate are always Black's-perspective, delta_score is the
    # mover's own perspective.
    assert "scoreLead и winrate - всегда с точки зрения чёрных" in prompt
    assert "delta_score - потеря очков" in prompt


def test_build_rag_query_for_weak_group():
    from baduk_backend.llm.prompts import build_rag_query

    finding = WeakGroupFinding(
        finding_id="f1",
        turn_number=5,
        stones=[(4, 4)],
        color="B",
        weak_score=0.85,
        own_certainty=0.0,
        boundary_certainty=0.0,
        liberties=4,
        severity="high",
        confidence=0.5,
    )
    query = build_rag_query(finding)
    assert query == "слабая группа камней с недостатком глаз и территории"


def test_build_rag_query_for_mistake():
    from baduk_backend.llm.prompts import build_rag_query

    finding = MistakeFinding(
        finding_id="f2",
        turn_number=10,
        color="W",
        move="Q4",
        delta_score=3.0,
        stage="middlegame",
        severity="medium",
        confidence=0.6,
    )
    query = build_rag_query(finding)
    assert query == "ошибка хода, потеря очков на стадии middlegame"


def test_explanation_with_rag_tool_parameters_extends_base_schema():
    from baduk_backend.llm.prompts import EXPLANATION_TOOL_PARAMETERS, EXPLANATION_WITH_RAG_TOOL_PARAMETERS

    assert "summary" in EXPLANATION_WITH_RAG_TOOL_PARAMETERS["properties"]
    assert "claims" in EXPLANATION_WITH_RAG_TOOL_PARAMETERS["properties"]
    assert "rag_doc_id" in EXPLANATION_WITH_RAG_TOOL_PARAMETERS["properties"]
    assert EXPLANATION_WITH_RAG_TOOL_PARAMETERS["required"] == ["summary", "claims"]
    # extension, not a fork: the base schema's own claims/summary shape is untouched
    assert (
        EXPLANATION_WITH_RAG_TOOL_PARAMETERS["properties"]["claims"]
        == EXPLANATION_TOOL_PARAMETERS["properties"]["claims"]
    )


def test_rag_decision_tool_parameters_has_two_branches():
    from baduk_backend.llm.prompts import RAG_DECISION_TOOL_PARAMETERS

    branches = RAG_DECISION_TOOL_PARAMETERS["oneOf"]
    assert len(branches) == 2
    tools = {branch["properties"]["tool"]["const"] for branch in branches}
    assert tools == {"retrieve_knowledge", "record_explanation"}
    search_branch = next(b for b in branches if b["properties"]["tool"]["const"] == "retrieve_knowledge")
    assert search_branch["required"] == ["tool"]
    finalize_branch = next(b for b in branches if b["properties"]["tool"]["const"] == "record_explanation")
    assert "rag_doc_id" in finalize_branch["properties"]
    assert set(finalize_branch["required"]) == {"tool", "summary", "claims"}


from baduk_backend.feature_extraction.schemas import OpeningLossFinding


def _opening_loss_finding() -> OpeningLossFinding:
    return OpeningLossFinding(
        finding_id="f3",
        type="opening_loss",
        color="B",
        move_range=(1, 9),
        delta_score=7.0,
        severity="medium",
        confidence=0.8,
    )


def test_build_user_prompt_for_opening_loss_mentions_range_color_and_delta():
    prompt = build_user_prompt(_opening_loss_finding(), _analysis(), 9)
    assert "delta_score=7.0" in prompt
    assert "1-9" in prompt
    assert "f3" in prompt


def test_build_rag_query_for_opening_loss():
    query = build_rag_query(_opening_loss_finding())
    assert query == "ошибки в дебюте, потеря очков в начале партии"


def _analysis_with_moves() -> AnalyzeResponse:
    return AnalyzeResponse(
        id="x",
        moveInfos=[
            MoveInfo(move="Q4", winrate=0.55, scoreLead=1.5, visits=300, prior=0.2, pv=["Q4"]),
        ],
        rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=250),
        ownership=[0.0] * 81,
    )


def test_answer_tool_parameters_cited_field_enum_matches_question_cited_field():
    enum = ANSWER_TOOL_PARAMETERS["properties"]["claims"]["items"]["properties"]["cited_field"]["enum"]
    assert set(enum) == {"winrate", "scoreLead", "visits", "prior"}


def test_answer_tool_parameters_claims_support_cited_move():
    cited_move_schema = ANSWER_TOOL_PARAMETERS["properties"]["claims"]["items"]["properties"]["cited_move"]
    assert cited_move_schema["type"] == ["string", "null"]


def test_answer_with_rag_tool_parameters_adds_rag_doc_id():
    assert "rag_doc_id" in ANSWER_WITH_RAG_TOOL_PARAMETERS["properties"]
    assert "answer" in ANSWER_WITH_RAG_TOOL_PARAMETERS["properties"]


def test_ask_decision_tool_parameters_offers_retrieve_knowledge_and_record_answer():
    tool_consts = [
        branch["properties"]["tool"]["const"] for branch in ASK_DECISION_TOOL_PARAMETERS["oneOf"]
    ]
    assert set(tool_consts) == {"retrieve_knowledge", "record_answer"}


def test_build_ask_user_prompt_includes_question_and_root_info():
    prompt = build_ask_user_prompt("почему белые слабы?", _analysis(), 9)
    assert "почему белые слабы?" in prompt
    assert "winrate=0.5" in prompt


def test_build_ask_user_prompt_lists_move_candidates_with_gtp_coords_not_converted_again():
    prompt = build_ask_user_prompt("что насчёт Q4?", _analysis_with_moves(), 9)
    # move_info.move is already a GTP string straight from KataGo - it must
    # appear verbatim, not be passed through xy_to_gtp() a second time.
    assert "Q4" in prompt
    assert "prior=0.2" in prompt


def test_build_ask_user_prompt_omits_move_candidates_block_when_there_are_none():
    prompt = build_ask_user_prompt("вопрос", _analysis(), 9)
    assert "Ходы-кандидаты" not in prompt
