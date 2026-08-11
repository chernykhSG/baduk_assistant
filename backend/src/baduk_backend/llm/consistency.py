from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.orchestrator import LLMProvider
from baduk_backend.llm.schemas import Claim, Explanation

MAX_CONSISTENCY_RETRIES = 2
FLOAT_TOLERANCE = 0.01

_FINDING_FIELDS: dict[str, set[str]] = {
    "weak_group": {"weak_score", "own_certainty", "boundary_certainty", "liberties"},
    "mistake": {"delta_score"},
}

_EMPTY_CLAIMS_CORRECTION = (
    "Твой ответ не содержит ни одного утверждения (claims), ссылающегося на конкретное число. "
    "Добавь хотя бы одно утверждение с точной ссылкой на поле и число из переданных данных."
)


def _true_value(field: str, finding: Finding, analysis: AnalyzeResponse) -> float:
    if field in _FINDING_FIELDS[finding.type]:
        return getattr(finding, field)
    return getattr(analysis.rootInfo, field)


def _claim_matches(claim: Claim, finding: Finding, analysis: AnalyzeResponse) -> bool:
    if claim.finding_id != finding.finding_id:
        return False
    true_value = _true_value(claim.cited_field, finding, analysis)
    if claim.cited_field in ("liberties", "visits"):
        return int(claim.cited_number) == int(true_value)
    return abs(claim.cited_number - true_value) <= FLOAT_TOLERANCE


def _mismatches(explanation: Explanation, finding: Finding, analysis: AnalyzeResponse) -> list[Claim]:
    return [c for c in explanation.claims if not _claim_matches(c, finding, analysis)]


def _correction_message(claim: Claim, finding: Finding, analysis: AnalyzeResponse) -> str:
    if claim.finding_id != finding.finding_id:
        return (
            f'Ты сослался на находку с finding_id="{claim.finding_id}", но это утверждение должно '
            f'ссылаться на текущую находку с finding_id="{finding.finding_id}". Исправь finding_id.'
        )
    true_value = _true_value(claim.cited_field, finding, analysis)
    return (
        f'Ты сослался на число {claim.cited_number} для поля "{claim.cited_field}", '
        f"но настоящее значение - {true_value}. Используй точное число или убери это утверждение."
    )


def _fallback_explanation(finding: Finding) -> Explanation:
    if finding.type == "weak_group":
        summary = (
            f"Обнаружена слабая группа (ход {finding.turn_number}): "
            f"показатель уязвимости {finding.weak_score:.2f}, уверенность {finding.confidence:.2f}. "
            "Не удалось получить проверенное текстовое объяснение - "
            "эти числа стоит свериться с ходами-кандидатами вручную."
        )
    else:
        summary = (
            f"Обнаружена потеря очков на ходе {finding.turn_number}: "
            f"Δ={finding.delta_score:.2f}, уверенность {finding.confidence:.2f}. "
            "Не удалось получить проверенное текстовое объяснение - "
            "эти числа стоит свериться с ходами-кандидатами вручную."
        )
    return Explanation(summary=summary, claims=[])


def _is_verified(explanation: Explanation, finding: Finding, analysis: AnalyzeResponse) -> bool:
    # An explanation with zero claims makes no checkable assertions at all -
    # treat it the same as a numeric mismatch rather than trivially passing,
    # otherwise citation-based verification is defeated by simply omitting
    # claims. `_fallback_explanation` legitimately returns claims=[] too, but
    # that value is only ever constructed and returned directly as the final
    # result below - it never flows back through this check.
    return bool(explanation.claims) and not _mismatches(explanation, finding, analysis)


def verify_and_retry(
    provider: LLMProvider, finding: Finding, analysis: AnalyzeResponse, board_size: int
) -> tuple[Explanation, bool]:
    explanation = provider.complete(finding, analysis, board_size)
    for _ in range(MAX_CONSISTENCY_RETRIES):
        if _is_verified(explanation, finding, analysis):
            return explanation, True
        mismatches = _mismatches(explanation, finding, analysis)
        corrections = (
            [_correction_message(c, finding, analysis) for c in mismatches]
            if mismatches
            else [_EMPTY_CLAIMS_CORRECTION]
        )
        explanation = provider.complete(finding, analysis, board_size, corrections=corrections)
    if _is_verified(explanation, finding, analysis):
        return explanation, True
    return _fallback_explanation(finding), False
