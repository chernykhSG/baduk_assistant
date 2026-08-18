from baduk_backend.llm.schemas import Explanation, QuestionAnswer, QuestionClaim


def test_explanation_rag_doc_id_defaults_to_none():
    explanation = Explanation(summary="...", claims=[])
    assert explanation.rag_doc_id is None


def test_explanation_rag_doc_id_can_be_set():
    explanation = Explanation(summary="...", claims=[], rag_doc_id="two-eyes-necessary")
    assert explanation.rag_doc_id == "two-eyes-necessary"


def test_question_claim_cited_move_defaults_to_none():
    claim = QuestionClaim(cited_field="winrate", cited_number=0.6)
    assert claim.cited_move is None


def test_question_claim_can_cite_a_specific_move():
    claim = QuestionClaim(cited_field="prior", cited_number=0.3, cited_move="Q4")
    assert claim.cited_move == "Q4"


def test_question_answer_rag_doc_id_defaults_to_none():
    answer = QuestionAnswer(answer="...", claims=[])
    assert answer.rag_doc_id is None
