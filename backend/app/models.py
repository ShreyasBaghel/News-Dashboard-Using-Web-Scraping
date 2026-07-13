from pydantic import BaseModel
from typing import List, Optional, Dict

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
    relevance_score: Optional[float] = 0.0
    canonical_url: Optional[str] = None
    keywords: List[str] = []
    
    # LLM Intelligence enrichment fields
    executive_summary: Optional[str] = None
    business_implications: Optional[List[str]] = None
    ai_relevance: Optional[str] = None
    industry_categories: Optional[List[str]] = None
    innovation_score: Optional[int] = None
    sentiment: Optional[str] = None

class DashboardPayload(BaseModel):
    keyword: str
    articles: List[Article]
    pinned_articles: List[Article]
    last_updated: str
    next_update: str
    keyword_counts: Optional[Dict[str, int]] = None

class RefreshRequest(BaseModel):
    keyword: Optional[str] = None
