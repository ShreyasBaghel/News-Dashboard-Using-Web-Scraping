import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.services.cache import init_db
from app.scheduler import start_scheduler, shutdown_scheduler
from app.pipeline import run_pipeline
from app.models import DashboardPayload, RefreshRequest

from pool.article_pool_fetcher import ensure_fresh_pool_on_startup
from pool.keyword_extractor import load_keywords_cache, get_cached_keywords

# Setup logging config
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle event handler for database initialization and background scheduler."""
    logger.info("Initializing database and tables...")
    init_db()
    
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
    q_clean = q.lower().strip()
    if len(q_clean) < 2:
        return {"suggestions": []}
        
    cached_list = get_cached_keywords()
    
    # 1. Prefix match
    prefix_matches = [kw for kw in cached_list if kw.startswith(q_clean)]
    
    # 2. Substring match fallback (if prefix matches are less than 5)
    if len(prefix_matches) < 5:
        seen = set(prefix_matches)
        substring_matches = [kw for kw in cached_list if q_clean in kw and kw not in seen]
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
        return payload
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
        return payload
    except Exception as e:
        logger.error(f"Error in POST /api/news/refresh: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Pipeline refresh error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
