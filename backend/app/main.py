import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.services.cache import init_db, is_duplicate_of_any
from app.scheduler import start_scheduler, shutdown_scheduler
from app.pipeline import run_pipeline
from app.models import DashboardPayload, RefreshRequest, Article

from pool.article_pool_fetcher import ensure_fresh_pool_on_startup
from pool.keyword_extractor import load_keywords_cache, get_cached_keywords
from app.services.pinned_store import load_pinned_articles, pin_article, unpin_article

# Setup logging config
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class PinRequest(BaseModel):
    article: Article
    keyword: Optional[str] = None

class UnpinRequest(BaseModel):
    url: str
    keyword: Optional[str] = None

def overlay_pinned_articles(payload: dict) -> dict:
    """
    Dynamically integrates the pinned-articles JSON store with the pipeline results:
    1. Read all currently pinned articles from JSON.
    2. Set is_pinned = True on these articles.
    3. For any other article in the payload's 'articles' or 'pinned_articles',
       if its URL is not in the JSON store, set is_pinned = False.
    4. Remove any articles from 'articles' if they are now in the JSON store (since they are pinned).
    5. Deduplicate and return:
       - 'pinned_articles': all articles currently in the JSON store.
       - 'articles': all other articles in the payload, preserving their relative order.
    """
    pinned = load_pinned_articles()
    incoming_articles = payload.get("articles", [])
    incoming_pinned = payload.get("pinned_articles", [])
    
    # Initialize the store if it has never been populated and there are default pinned articles
    if not pinned and incoming_pinned:
        from app.services.pinned_store import save_pinned_articles
        initialized_pinned = []
        for a in incoming_pinned:
            art_dict = a if isinstance(a, dict) else a.dict()
            art_dict["is_pinned"] = True
            initialized_pinned.append(art_dict)
        save_pinned_articles(initialized_pinned)
        pinned = initialized_pinned

    pinned_urls = {a["url"] for a in pinned if a.get("url")}
    
    # Group them by URL to look up details
    url_to_article = {}
    for a in incoming_articles + incoming_pinned:
        url = a.get("url") if isinstance(a, dict) else getattr(a, "url", None)
        if url:
            art_dict = a if isinstance(a, dict) else a.dict()
            url_to_article[url] = art_dict
            
    final_pinned = []
    for p in pinned:
        url = p.get("url")
        if url:
            art_dict = dict(p)
            art_dict["is_pinned"] = True
            if url in url_to_article:
                for k, v in url_to_article[url].items():
                    if k != "is_pinned":
                        art_dict[k] = v
            final_pinned.append(art_dict)
            
    final_unpinned = []
    seen_unpinned = []
    for a in incoming_articles + incoming_pinned:
        art_dict = a if isinstance(a, dict) else a.dict()
        url = art_dict.get("url")
        if not url:
            continue
            
        # Check if it is a duplicate of any pinned article
        if is_duplicate_of_any(art_dict, final_pinned):
            continue
            
        # Check if it is a duplicate of any already added unpinned article
        if is_duplicate_of_any(art_dict, seen_unpinned):
            continue
            
        art_dict["is_pinned"] = False
        final_unpinned.append(art_dict)
        seen_unpinned.append(art_dict)
            
    new_payload = dict(payload)
    new_payload["articles"] = final_unpinned
    new_payload["pinned_articles"] = final_pinned
    return new_payload

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle event handler for database initialization and background scheduler."""
    logger.info("Initializing database and tables...")
    init_db()
    
    logger.info("Validating Gemini API configuration...")
    try:
        from app.services.gemini_client import validate_gemini_config
        await validate_gemini_config()
    except Exception as e:
        logger.error(f"Error during startup Gemini config validation: {e}")
    
    logger.info("Ensuring fresh article pool on startup...")
    topics = [
        "Dalmia Cement",
        "AI",
        "machine learning",
        "robotics & automation",
        "manufacturing",
        "cement industry"
    ]
    try:
        await ensure_fresh_pool_on_startup(topics)
        load_keywords_cache()
    except Exception as e:
        logger.error(f"Failed to ensure fresh pool on startup: {str(e)}")
    
    logger.info("Starting background scheduler...")
    start_scheduler()
    
    yield
    
    logger.info("Shutting down background scheduler...")
    shutdown_scheduler()


app = FastAPI(
    title="AI-Powered Industry News Dashboard PoC Backend",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend communication (Vite default is 5173, CRA default is 3000, allow specific origins)
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/keywords/suggest")
async def suggest_keywords(q: str = Query("", description="Prefix search term for autocomplete suggestions")):
    from app.services.cache import get_all_aggregated_keywords
    aggregated_list = get_all_aggregated_keywords()
    
    # If the list is empty or has very few items (e.g. startup), merge with old cached list
    if len(aggregated_list) < 10:
        fallback_kws = get_cached_keywords()
        seen = set(aggregated_list)
        for kw in fallback_kws:
            if kw not in seen:
                aggregated_list.append(kw)
                seen.add(kw)
                
    q_clean = q.lower().strip()
    
    if not q_clean:
        return {"suggestions": aggregated_list}
        
    # 1. Prefix match (case-insensitive)
    prefix_matches = [kw for kw in aggregated_list if kw.lower().startswith(q_clean)]
    
    # 2. Substring match fallback (if prefix matches are less than 5)
    if len(prefix_matches) < 5:
        seen = set(prefix_matches)
        substring_matches = [kw for kw in aggregated_list if q_clean in kw.lower() and kw not in seen]
        matches = prefix_matches + substring_matches
    else:
        matches = prefix_matches
        
    return {"suggestions": matches[:10]}

@app.get("/api/news", response_model=DashboardPayload)
async def get_news(keyword: str = Query(None, description="Search keyword or topic")):
    """
    Retrieve dashboard payload (summarized feed + pinned technology sector news).
    Tries to hit SQLite cache first.
    """
    try:
        payload = await run_pipeline(keyword=keyword, force_refresh=False)
        return overlay_pinned_articles(payload)
    except Exception as e:
        logger.error(f"Error in GET /api/news: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")

@app.post("/api/news/refresh", response_model=DashboardPayload)
async def refresh_news(request: RefreshRequest):
    """
    Force execute pipeline execution for keyword, bypassing/updating SQLite caches.
    """
    try:
        payload = await run_pipeline(keyword=request.keyword, force_refresh=True)
        return overlay_pinned_articles(payload)
    except Exception as e:
        logger.error(f"Error in POST /api/news/refresh: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Pipeline refresh error: {str(e)}")

@app.post("/api/news/pin", response_model=DashboardPayload)
async def pin_article_endpoint(request: PinRequest):
    """
    Pin an article to the pinned-articles store and update cache state.
    """
    try:
        pin_article(request.article.dict())
        payload = await run_pipeline(keyword=request.keyword, force_refresh=False)
        return overlay_pinned_articles(payload)
    except Exception as e:
        logger.error(f"Error in POST /api/news/pin: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Pin error: {str(e)}")

@app.post("/api/news/unpin", response_model=DashboardPayload)
async def unpin_article_endpoint(request: UnpinRequest):
    """
    Unpin an article from the pinned-articles store and update cache state.
    """
    try:
        unpin_article(request.url)
        payload = await run_pipeline(keyword=request.keyword, force_refresh=False)
        return overlay_pinned_articles(payload)
    except Exception as e:
        logger.error(f"Error in POST /api/news/unpin: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unpin error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
