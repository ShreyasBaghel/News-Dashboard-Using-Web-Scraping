from pydantic import BaseModel
from typing import List, Optional

class Article(BaseModel):
    title: str
    url: str
    source: str
    published_at: str
    summary: str
    scraped_content: Optional[str] = None
    keyword: Optional[str] = None
    is_pinned: bool = False
    company: Optional[str] = None  # NVIDIA, Microsoft, OpenAI for pinned articles

class DashboardPayload(BaseModel):
    keyword: str
    articles: List[Article]
    pinned_articles: List[Article]
    last_updated: str
    next_update: str

class RefreshRequest(BaseModel):
    keyword: Optional[str] = None
