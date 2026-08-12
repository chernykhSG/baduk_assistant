from baduk_backend.llm.schemas import Explanation


def test_explanation_rag_doc_id_defaults_to_none():
    explanation = Explanation(summary="...", claims=[])
    assert explanation.rag_doc_id is None


def test_explanation_rag_doc_id_can_be_set():
    explanation = Explanation(summary="...", claims=[], rag_doc_id="two-eyes-necessary")
    assert explanation.rag_doc_id == "two-eyes-necessary"
