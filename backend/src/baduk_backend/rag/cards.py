import re
from pathlib import Path

from baduk_backend.rag.schemas import ParsedCard

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def parse_card_file(path: Path, wiki_root: Path) -> ParsedCard:
    import yaml

    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"malformed card {path}: no YAML frontmatter block found")

    frontmatter = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).strip()

    for field in ("type", "category", "status"):
        if field not in frontmatter:
            raise ValueError(f"malformed card {path}: missing frontmatter field '{field}'")

    title_match = _TITLE_RE.search(body)
    if not title_match:
        raise ValueError(f"malformed card {path}: no '# Title' heading found in body")

    return ParsedCard(
        doc_id=path.stem,
        type=frontmatter["type"],
        category=frontmatter["category"],
        status=frontmatter["status"],
        title=title_match.group(1).strip(),
        source=str(path.relative_to(wiki_root)).replace("\\", "/"),
        body=body,
    )
