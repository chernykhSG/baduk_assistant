from pydantic import BaseModel


class ParsedCard(BaseModel):
    doc_id: str
    type: str
    category: str
    status: str
    title: str
    source: str
    body: str
