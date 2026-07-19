import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Query, HTTPException, Header, BackgroundTasks
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

async def validate_ollama_config() -> bool:
    """
    Validates that Ollama is running and that the configured model is installed.
    If the model is missing or Ollama is unreachable, raises a startup error.
    """
    import httpx
    url = f"{settings.ollama_url_resolved}/api/tags"
    model = settings.OLLAMA_MODEL
    logger.info(f"Validating Ollama configuration at {url} for model '{model}'...")
    try:
        timeout = httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            if response.status_code != 200:
                raise RuntimeError(f"Ollama returned status {response.status_code} when listing models.")
            
            data = response.json()
            models = data.get("models", [])
            installed_model_names = []
            for m in models:
                if "name" in m:
                    installed_model_names.append(m["name"])
                if "model" in m:
                    installed_model_names.append(m["model"])
            
            model_lower = model.lower()
            model_with_latest = model_lower if ":" in model_lower else f"{model_lower}:latest"
            
            model_installed = False
            for installed in installed_model_names:
                inst_lower = installed.lower()
                if inst_lower == model_lower or inst_lower == model_with_latest or inst_lower.startswith(model_lower + ":"):
                    model_installed = True
                    break
                    
            if not model_installed:
                error_msg = f"Ollama model '{model}' is NOT installed. Installed models: {list(set(installed_model_names))}."
                logger.error(error_msg)
                raise RuntimeError(error_msg)
                
            logger.info(f"Ollama model '{model}' successfully validated on startup.")
            return True
    except Exception as e:
        error_msg = f"Ollama startup validation failed: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle event handler for database initialization and background scheduler."""
    logger.info("Initializing database and tables...")
    init_db()
    
    logger.info("Pruning stale fallback/placeholder keywords from cache...")
    try:
        from app.services.cache import cleanup_stale_keywords_in_cache, migrate_caches
        migrate_caches()
        cleanup_stale_keywords_in_cache()
    except Exception as e:
        logger.error(f"Error during startup cache validation: {e}")
    
    logger.info("Validating Ollama configuration...")
    try:
        await validate_ollama_config()
    except Exception as e:
        logger.error(f"Error during startup Ollama validation: {e}")
        raise e
    
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
        await ensure_fresh_pool_on_startup(topics, max_age_hours=0)
        load_keywords_cache()
        from app.services.cache import build_in_memory_index
        build_in_memory_index()
        from app.services.cache import get_all_aggregated_keywords, get_global_keyword_counts
        agg = get_all_aggregated_keywords()
        kw_counts = get_global_keyword_counts()
        logger.info(f"[STARTUP] Total unique keywords available: {len(agg)} from article_keywords table, {len(kw_counts)} from cache.json.")
    except Exception as e:
        logger.error(f"Failed to ensure fresh pool on startup: {str(e)}")
    
    logger.info("Loading ACTIVE_DATASET snapshot from SQLite authoritative store...")
    from app.services.dataset_manager import dataset_manager
    dataset_manager.load_startup_snapshot()

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

# Enable CORS for frontend communication using settings config
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
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

import datetime

def get_news_from_cache_or_default(keyword: Optional[str]) -> dict:
    from app.services.dataset_manager import dataset_manager
    from app.services.validator import normalize_text_for_matching
    
    active_dataset = dataset_manager.get_active_dataset()
    keyword_clean = keyword.strip() if keyword else ""
    
    if not keyword_clean:
        return active_dataset
        
    keyword_norm = normalize_text_for_matching(keyword_clean)
    
    matching_articles = []
    for art in active_dataset.get("articles", []):
        matched = False
        # 1. Exact or Normalized Tag Match
        tags = art.get("keywords", [])
        for tag in tags:
            if normalize_text_for_matching(tag) == keyword_norm:
                matched = True
                break
                
        # 2. Title / Summary Substring Match
        if not matched:
            title_norm = normalize_text_for_matching(art.get("title", ""))
            summary_norm = normalize_text_for_matching(art.get("summary", ""))
            if keyword_norm and (keyword_norm in title_norm or keyword_norm in summary_norm):
                matched = True
                
        if matched:
            matching_articles.append(art)
            
    matching_pinned = []
    for art in active_dataset.get("pinned_articles", []):
        matched = False
        tags = art.get("keywords", [])
        for tag in tags:
            if normalize_text_for_matching(tag) == keyword_norm:
                matched = True
                break
        if not matched:
            title_norm = normalize_text_for_matching(art.get("title", ""))
            summary_norm = normalize_text_for_matching(art.get("summary", ""))
            if keyword_norm and (keyword_norm in title_norm or keyword_norm in summary_norm):
                matched = True
        if matched:
            matching_pinned.append(art)
            
    return {
        "keyword": keyword_clean,
        "articles": matching_articles,
        "pinned_articles": matching_pinned,
        "last_updated": active_dataset.get("last_updated"),
        "next_update": active_dataset.get("next_update"),
        "keyword_counts": active_dataset.get("keyword_counts", {})
    }


@app.get("/api/news", response_model=DashboardPayload)
async def get_news(keyword: str = Query(None, description="Search keyword or topic")):
    """
    Retrieve news payload instantly from cache, avoiding live scraping and LLM invocation.
    """
    try:
        payload = get_news_from_cache_or_default(keyword)
        return overlay_pinned_articles(payload)
    except Exception as e:
        logger.error(f"Error in GET /api/news: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Cache retrieval error: {str(e)}")

@app.post("/api/news/refresh", response_model=DashboardPayload)
async def refresh_news(request: RefreshRequest, x_user_role: Optional[str] = Header(None)):
    """
    Force manual execution of the pipeline (Admin only).
    """
    await verify_admin_role(x_user_role)
    try:
        payload = await run_pipeline(keyword=request.keyword, force_refresh=True)
        return overlay_pinned_articles(payload)
    except Exception as e:
        logger.error(f"Error in POST /api/news/refresh: {str(e)}. Attempting cached fallback recovery...")
        try:
            payload = get_news_from_cache_or_default(request.keyword)
            logger.warning(f"Successfully fell back to cached dashboard for POST /api/news/refresh after error: {str(e)}")
            return overlay_pinned_articles(payload)
        except Exception as cache_err:
            logger.error(f"Cache fallback lookup also failed: {str(cache_err)}")
            raise HTTPException(
                status_code=500, 
                detail=f"Pipeline refresh error: {str(e)}. Cache fallback also failed: {str(cache_err)}"
            )

@app.post("/api/news/pin", response_model=DashboardPayload)
async def pin_article_endpoint(request: PinRequest):
    """
    Pin an article to the pinned-articles store and update cache state.
    """
    try:
        pin_article(request.article.dict())
        payload = get_news_from_cache_or_default(request.keyword)
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
        payload = get_news_from_cache_or_default(request.keyword)
        return overlay_pinned_articles(payload)
    except Exception as e:
        logger.error(f"Error in POST /api/news/unpin: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unpin error: {str(e)}")

# --- ROLE-BASED AUTHENTICATION & ADMIN DASHBOARD ENDPOINTS ---
async def verify_admin_role(x_user_role: Optional[str] = Header(None)):
    if not x_user_role or x_user_role.lower() != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admin access required.")

class AddKeywordRequest(BaseModel):
    keyword: str

@app.get("/api/admin/keywords")
async def get_monitored_keywords_endpoint(x_user_role: Optional[str] = Header(None)):
    await verify_admin_role(x_user_role)
    from app.services.monitored_keywords import load_monitored_keywords
    return {"keywords": load_monitored_keywords()}

@app.post("/api/admin/keywords")
async def add_monitored_keyword_endpoint(
    request: AddKeywordRequest,
    background_tasks: BackgroundTasks,
    x_user_role: Optional[str] = Header(None)
):
    await verify_admin_role(x_user_role)
    from app.services.monitored_keywords import load_monitored_keywords, save_monitored_keywords
    
    keyword_to_add = request.keyword.strip()
    if not keyword_to_add:
        raise HTTPException(status_code=400, detail="Keyword cannot be empty.")
        
    keywords = load_monitored_keywords()
    if keyword_to_add.lower() in [k.lower() for k in keywords]:
        return {"message": f"Keyword '{keyword_to_add}' is already monitored.", "keywords": keywords}
        
    keywords.append(keyword_to_add)
    save_monitored_keywords(keywords)
    
    # Spawn pipeline run specifically for the new keyword in the background
    background_tasks.add_task(run_pipeline_in_background, keyword=keyword_to_add)
    
    return {
        "message": f"Keyword '{keyword_to_add}' added successfully. Scraping pipeline started.",
        "keywords": keywords
    }

@app.delete("/api/admin/keywords")
async def delete_monitored_keyword_endpoint(
    keyword: str = Query(..., description="Keyword to remove"),
    x_user_role: Optional[str] = Header(None)
):
    await verify_admin_role(x_user_role)
    from app.services.monitored_keywords import load_monitored_keywords, save_monitored_keywords
    
    keyword_to_remove = keyword.strip()
    keywords = load_monitored_keywords()
    
    updated_kws = [k for k in keywords if k.lower() != keyword_to_remove.lower()]
    if len(updated_kws) == len(keywords):
        raise HTTPException(status_code=404, detail=f"Keyword '{keyword_to_remove}' not found in monitored list.")
        
    save_monitored_keywords(updated_kws)
    return {"message": f"Keyword '{keyword_to_remove}' removed successfully.", "keywords": updated_kws}

@app.post("/api/admin/pipeline/run")
async def run_pipeline_endpoint(
    background_tasks: BackgroundTasks,
    x_user_role: Optional[str] = Header(None)
):
    await verify_admin_role(x_user_role)
    from app.pipeline import pipeline_status
    if pipeline_status["status"] == "running":
        return {"message": "Pipeline is already running.", "status": pipeline_status}
        
    background_tasks.add_task(run_pipeline_in_background, keyword=None)
    return {"message": "Pipeline run started in background.", "status": pipeline_status}

@app.post("/api/admin/pipeline/run/incremental")
async def run_incremental_pipeline_endpoint(
    background_tasks: BackgroundTasks,
    x_user_role: Optional[str] = Header(None)
):
    await verify_admin_role(x_user_role)
    from app.pipeline import pipeline_status
    if pipeline_status["status"] == "running":
        return {"message": "Pipeline is already running.", "status": pipeline_status}
        
    background_tasks.add_task(run_incremental_pipeline_in_background)
    return {"message": "Incremental pipeline started for new keywords.", "status": pipeline_status}

@app.get("/api/admin/pipeline/status")
async def get_pipeline_status_endpoint(x_user_role: Optional[str] = Header(None)):
    await verify_admin_role(x_user_role)
    from app.pipeline import pipeline_status
    return {"status": pipeline_status}

async def run_pipeline_in_background(keyword: Optional[str] = None):
    from app.pipeline import pipeline_status, run_pipeline
    from app.services.monitored_keywords import mark_keyword_processed
    try:
        await run_pipeline(keyword=keyword, force_refresh=True)
        if keyword:
            mark_keyword_processed(keyword, True)
    except Exception as e:
        logger.error(f"Background pipeline execution failed: {e}")

async def run_incremental_pipeline_in_background():
    from app.pipeline import pipeline_status, run_pipeline
    from app.services.monitored_keywords import load_monitored_keywords_detailed, mark_keyword_processed
    from datetime import datetime, timezone
    
    pipeline_status["status"] = "running"
    pipeline_status["started_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    pipeline_status["progress"] = 5
    pipeline_status["message"] = "Starting incremental pipeline for new keywords..."
    
    try:
        detailed_keywords = load_monitored_keywords_detailed()
        unprocessed = [d["keyword"] for d in detailed_keywords if not d.get("is_processed", False)]
        
        if not unprocessed:
            pipeline_status["status"] = "completed"
            pipeline_status["progress"] = 100
            pipeline_status["message"] = "No new keywords to process."
            return
            
        total = len(unprocessed)
        logger.info(f"Incremental pipeline starting for {total} unprocessed keywords: {unprocessed}")
        
        for idx, kw in enumerate(unprocessed):
            pipeline_status["progress"] = int(5 + (idx / total) * 90)
            pipeline_status["message"] = f"Processing keyword {idx+1}/{total}: '{kw}'..."
            pipeline_status["current_keyword"] = kw
            
            logger.info(f"Incremental pipeline: Processing '{kw}' ({idx+1}/{total})")
            await run_pipeline(keyword=kw, force_refresh=False)
            mark_keyword_processed(kw, True)
            
        pipeline_status["status"] = "completed"
        pipeline_status["progress"] = 100
        pipeline_status["message"] = f"Successfully processed {total} new keywords."
        logger.info("Incremental pipeline completed successfully.")
        
    except Exception as e:
        logger.error(f"Incremental pipeline failed: {e}")
        pipeline_status["status"] = "failed"
        pipeline_status["message"] = f"Incremental pipeline failed: {str(e)}"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
