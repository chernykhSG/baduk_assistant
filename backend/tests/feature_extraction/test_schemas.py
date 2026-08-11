from pydantic import TypeAdapter

from baduk_backend.feature_extraction.schemas import Finding, MistakeFinding, WeakGroupFinding

_ADAPTER: TypeAdapter = TypeAdapter(Finding)


def test_finding_discriminates_weak_group():
    parsed = _ADAPTER.validate_python(
        {
            "finding_id": "f1",
            "type": "weak_group",
            "turn_number": 1,
            "stones": [[4, 4]],
            "color": "B",
            "weak_score": 0.8,
            "own_certainty": 0.1,
            "boundary_certainty": 0.2,
            "liberties": 3,
            "severity": "high",
            "confidence": 0.5,
        }
    )
    assert isinstance(parsed, WeakGroupFinding)


def test_finding_discriminates_mistake():
    parsed = _ADAPTER.validate_python(
        {
            "finding_id": "f2",
            "type": "mistake",
            "turn_number": 10,
            "color": "W",
            "move": "Q4",
            "delta_score": 3.0,
            "stage": "middlegame",
            "severity": "medium",
            "confidence": 0.6,
        }
    )
    assert isinstance(parsed, MistakeFinding)
