from pathlib import Path

import pytest

from baduk_backend.rag.cards import parse_card_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_card_file_extracts_all_fields():
    card = parse_card_file(FIXTURES / "valid_principle.md", FIXTURES)

    assert card.doc_id == "valid_principle"
    assert card.type == "principle"
    assert card.category == "тест"
    assert card.status == "reviewed"
    assert card.title == "Тестовый принцип"
    assert card.source == "valid_principle.md"
    assert "Обоснование" in card.body
    assert not card.body.startswith("---")


def test_parse_card_file_preserves_non_reviewed_status():
    card = parse_card_file(FIXTURES / "valid_draft.md", FIXTURES)

    assert card.status == "draft"


def test_parse_card_file_raises_on_missing_frontmatter_field():
    with pytest.raises(ValueError, match="category"):
        parse_card_file(FIXTURES / "missing_field.md", FIXTURES)


def test_parse_card_file_raises_on_missing_title():
    with pytest.raises(ValueError, match="Title"):
        parse_card_file(FIXTURES / "missing_title.md", FIXTURES)
