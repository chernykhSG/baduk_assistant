from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
from baduk_backend.feature_extraction.schemas import MistakeFinding, WeakGroupFinding
from baduk_backend.llm.prompts import (
    EXPLANATION_TOOL_DESCRIPTION,
    EXPLANATION_TOOL_PARAMETERS,
    build_user_prompt,
    build_rag_query,
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
