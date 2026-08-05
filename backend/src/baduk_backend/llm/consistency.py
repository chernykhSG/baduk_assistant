from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.orchestrator import LLMProvider
from baduk_backend.llm.schemas import Claim, Explanation

MAX_CONSISTENCY_RETRIES = 2
FLOAT_TOLERANCE = 0.01

_FINDING_FIELDS = {"weak_score", "own_certainty", "boundary_certainty", "liberties"}


def _true_value(field: str, finding: Finding, analysis: AnalyzeResponse) -> float:
    if field in _FINDING_FIELDS:
        return getattr(finding, field)
    return getattr(analysis.rootInfo, field)


def _claim_matches(claim: Claim, finding: Finding, analysis: AnalyzeResponse) -> bool:
    true_value = _true_value(claim.cited_field, finding, analysis)
    if claim.cited_field in ("liberties", "visits"):
        return int(claim.cited_number) == int(true_value)
    return abs(claim.cited_number - true_value) <= FLOAT_TOLERANCE


def _mismatches(explanation: Explanation, finding: Finding, analysis: AnalyzeResponse) -> list[Claim]:
    return [c for c in explanation.claims if not _claim_matches(c, finding, analysis)]


def _correction_message(claim: Claim, finding: Finding, analysis: AnalyzeResponse) -> str:
    true_value = _true_value(claim.cited_field, finding, analysis)
    return (
        f'Ты сослался на число {claim.cited_number} для поля "{claim.cited_field}", '
        f"но настоящее значение - {true_value}. Используй точное число или убери это утверждение."
    )


def _fallback_explanation(finding: Finding) -> Explanation:
    return Explanation(
        summary=(
            f"Обнаружена слабая группа (ход {finding.turn_number}): "
            f"показатель уязвимости {finding.weak_score:.2f}, уверенность {finding.confidence:.2f}. "
            "Не удалось получить проверенное текстовое объяснение - "
            "эти числа стоит свериться с ходами-кандидатами вручную."
        ),
        claims=[],
    )


def verify_and_retry(
    provider: LLMProvider, finding: Finding, analysis: AnalyzeResponse
) -> tuple[Explanation, bool]:
    explanation = provider.complete(finding, analysis)
    for _ in range(MAX_CONSISTENCY_RETRIES):
        mismatches = _mismatches(explanation, finding, analysis)
        if not mismatches:
            return explanation, True
        corrections = [_correction_message(c, finding, analysis) for c in mismatches]
        explanation = provider.complete(finding, analysis, corrections=corrections)
    if not _mismatches(explanation, finding, analysis):
        return explanation, True
    return _fallback_explanation(finding), False
