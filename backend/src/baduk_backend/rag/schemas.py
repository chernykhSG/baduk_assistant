from pydantic import BaseModel


class ParsedCard(BaseModel):
    doc_id: str
    type: str
    category: str
    status: str
    title: str
    source: str
    body: str


class RagSnippet(BaseModel):
    doc_id: str
    title: str
    source: str
    text_snippet: str
    relevance_score: float
