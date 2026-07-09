import logging
import time
import json
import httpx
import hashlib
import asyncio
from typing import List, Dict, Any, Optional

from app.config import settings
from app.services.cache import get_cached_llm_insights, save_cached_llm_insights

logger = logging.getLogger(__name__)

# Fallback insights in case of JSON parse failure after retries
DEFAULT_LLM_INSIGHTS = {
    "executive_summary": "This article discusses key industrial developments and technological advancements in the sector.",
    "business_implications": [
        "Provides insights into operational improvements and potential efficiency gains.",
        "Highlights automation and digital transformation opportunities.",
        "Illustrates market dynamics and competitor strategies in the industry."
    ],
    "ai_relevance": "Not AI-focused",
    "industry_categories": ["Manufacturing"],
    "innovation_score": 50,
    "sentiment": "Neutral"
}

def get_article_cache_key(art: Dict[str, Any]) -> str:
    """Generate a stable, unique cache key for an article based on its immutable properties."""
    url = art.get("canonical_url") or art.get("url") or ""
    title = art.get("title") or ""
    pub = art.get("published_at") or ""
    data = f"{url.strip()}||{title.strip()}||{pub.strip()}"
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

def _get_article_tags(art: Dict[str, Any]) -> List[str]:
    """Dynamically extract relevant tags/keywords matching the article using the pool keywords."""
    try:
        from pool.keyword_extractor import get_cached_keywords
        from app.pipeline import has_whole_word_match
        
        cached_kws = get_cached_keywords()
        if not cached_kws:
            return [art.get("keyword") or "Technology"]
            
        title = art.get("title", "")
        summary = art.get("summary", "")
        content = art.get("scraped_content", "") or ""
        text_to_check = f"{title} {summary} {content[:1000]}".lower()
        
        matched_tags = []
        # Check top 40 extracted keywords for relevance
        for kw in cached_kws[:40]:
            if has_whole_word_match(text_to_check, kw.lower()):
                matched_tags.append(kw)
                if len(matched_tags) >= 4:
                    break
                    
        if not matched_tags and art.get("keyword"):
            matched_tags.append(art["keyword"].title())
            
        return matched_tags if matched_tags else ["Industry"]
    except Exception as e:
        logger.warning(f"Error generating tags: {e}")
        return [art.get("keyword") or "Technology"]

def validate_llm_output(data: Any) -> bool:
    """Validate that the parsed JSON matches the expected schema and constraints."""
    if not isinstance(data, dict):
        return False
    required_keys = {
        "executive_summary", "business_implications", "ai_relevance",
        "industry_categories", "innovation_score", "sentiment"
    }
    if not required_keys.issubset(data.keys()):
        return False
    if not isinstance(data["executive_summary"], str) or not data["executive_summary"].strip():
        return False
    if not isinstance(data["business_implications"], list) or len(data["business_implications"]) < 1:
        return False
    if not all(isinstance(x, str) and x.strip() for x in data["business_implications"]):
        return False
    if not isinstance(data["ai_relevance"], str) or not data["ai_relevance"].strip():
        return False
    if not isinstance(data["industry_categories"], list) or len(data["industry_categories"]) < 1:
        return False
    if not all(isinstance(x, str) and x.strip() for x in data["industry_categories"]):
        return False
    if not isinstance(data["innovation_score"], (int, float)):
        return False
    
    data["innovation_score"] = int(data["innovation_score"])
    if not (0 <= data["innovation_score"] <= 100):
        return False
    if data["sentiment"] not in {"Positive", "Neutral", "Negative", "Mixed"}:
        return False
    return True

# Phi-3 Mini optimized prompt templates
BATCH_SYSTEM_PROMPT = """You are a business intelligence assistant analyzing industrial news.
You must analyze the provided articles and return a JSON object containing an array of analyses under the key "results".
Do not output any markdown code blocks, explanation, or notes. Output ONLY the raw JSON.

Each article analysis MUST match this JSON structure:
{
  "url": "must match the input article URL exactly",
  "executive_summary": "Concise business-focused summary of industrial/manufacturing impact and market implications.",
  "business_implications": [
    "first implication for industrial professionals (e.g. automation, cost)",
    "second implication",
    "third implication"
  ],
  "ai_relevance": "Description of AI technologies involved (e.g. Robotics, Computer Vision) or 'Not AI-focused'",
  "industry_categories": ["Category 1", "Category 2"],
  "innovation_score": 0 to 100 integer,
  "sentiment": "Positive, Neutral, Negative, or Mixed"
}

Your entire output must follow this schema exactly:
{
  "results": [
    ...
  ]
}"""

BATCH_USER_PROMPT = """Analyze the following {count} articles:

{articles_text}

Remember: Return strictly the JSON object. Do not wrap in markdown or add explanation."""

async def query_ollama_batch(
    articles: List[Dict[str, Any]], 
    client: httpx.AsyncClient, 
    stats: Dict[str, Any]
) -> Dict[str, Any]:
    """Query local Ollama with a batch of articles, implementing a single retry on parsing failure."""
    count = len(articles)
    articles_inputs = []
    for idx, art in enumerate(articles):
        # Gather all metadata to reuse
        quality_score = round(len(art.get("scraped_content", "") or "") * 0.1 + len(art.get("summary", "") or "") * 0.5 + (art.get("relevance_score", 0.0) or 0.0) * 10.0, 1)
        ranking_score = art.get("relevance_score", 0.0)
        relevance_score = art.get("validation_relevance_score", 80.0)
        tags = _get_article_tags(art)
        
        articles_inputs.append(
            f"Index: {idx}\n"
            f"URL: {art.get('url')}\n"
            f"Headline: {art.get('title')}\n"
            f"Source: {art.get('source')}\n"
            f"Published Date: {art.get('published_at')}\n"
            f"Keyword: {art.get('keyword') or 'General'}\n"
            f"Category: {art.get('keyword') or 'General'}\n"
            f"Generated Tags: {', '.join(tags)}\n"
            f"Quality Score: {quality_score}\n"
            f"Relevance Score: {relevance_score}\n"
            f"Ranking Score: {ranking_score}\n"
            f"Article Summary: {art.get('summary')}\n"
            f"Text: {(art.get('scraped_content', '') or '')[:1200]}\n"
        )
    
    articles_text = "\n---\n".join(articles_inputs)
    prompt = f"System: {BATCH_SYSTEM_PROMPT}\n\nUser: {BATCH_USER_PROMPT.format(count=count, articles_text=articles_text)}"
    
    ollama_payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.0
        }
    }
    
    timeout_cfg = httpx.Timeout(connect=3.0, read=settings.OLLAMA_TIMEOUT, write=3.0, pool=5.0)
    
    attempt = 0
    max_attempts = 2
    
    while attempt < max_attempts:
        stats["ollama_requests"] += 1
        t0 = time.perf_counter()
        try:
            response = await client.post(
                f"{settings.ollama_url_resolved}/api/generate",
                json=ollama_payload,
                timeout=timeout_cfg
            )
            duration = time.perf_counter() - t0
            stats["ollama_duration"] += duration
            
            if response.status_code == 200:
                res_data = response.json()
                raw_response = res_data.get("response", "").strip()
                parsed = json.loads(raw_response)
                
                # Check structure
                if "results" in parsed and isinstance(parsed["results"], list):
                    valid_results = 0
                    batch_urls = {art["url"] for art in articles}
                    for item in parsed["results"]:
                        if item.get("url") in batch_urls:
                            if validate_llm_output(item):
                                valid_results += 1
                    
                    if valid_results > 0:
                        return parsed
                    else:
                        logger.warning(f"Ollama response results failed schema validation: {raw_response}")
                        stats["json_validation_failures"] += 1
                else:
                    logger.warning(f"Ollama response missing 'results' array: {raw_response}")
                    stats["json_validation_failures"] += 1
            else:
                logger.warning(f"Ollama returned HTTP status {response.status_code}")
                
        except httpx.HTTPError as e:
            logger.warning(f"Ollama network request failed: {e}")
        except json.JSONDecodeError as e:
            logger.warning(f"Ollama JSON decode failed: {e}")
            stats["json_validation_failures"] += 1
        except Exception as e:
            logger.warning(f"Ollama error: {e}")
            
        attempt += 1
        if attempt < max_attempts:
            stats["retry_count"] += 1
            logger.info("Retrying Ollama batch request...")
            # Slight sleep before retry
            await asyncio.sleep(0.5)
            
    return {"results": []}

async def enrich_articles_with_llm(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Enrich the list of articles with LLM intelligence insights, using batching, caching, and graceful fallbacks."""
    if not settings.ENABLE_LLM_REASONING or not articles:
        # If disabled, ensure fields are initialized to None
        for art in articles:
            art["executive_summary"] = None
            art["business_implications"] = None
            art["ai_relevance"] = None
            art["industry_categories"] = None
            art["innovation_score"] = None
            art["sentiment"] = None
        return articles

    stats = {
        "cache_hits": 0,
        "cache_misses": 0,
        "ollama_requests": 0,
        "ollama_duration": 0.0,
        "retry_count": 0,
        "json_validation_failures": 0,
        "enriched_count": 0
    }
    
    start_time = time.perf_counter()
    
    # 1. Check cache first
    cache_miss_articles = []
    article_keys = {}
    
    for art in articles:
        key = get_article_cache_key(art)
        article_keys[art["url"]] = key
        
        cached_insights = None
        if settings.LLM_CACHE_ENABLED:
            cached_insights = get_cached_llm_insights(key)
            
        if cached_insights and validate_llm_output(cached_insights):
            stats["cache_hits"] += 1
            # Apply insights
            for k, v in cached_insights.items():
                art[k] = v
            stats["enriched_count"] += 1
        else:
            stats["cache_misses"] += 1
            cache_miss_articles.append(art)
            
    # 2. Batch process cache misses
    if cache_miss_articles:
        batch_size = max(1, settings.LLM_BATCH_SIZE)
        client_timeout = httpx.Timeout(connect=3.0, read=settings.OLLAMA_TIMEOUT, write=3.0, pool=5.0)
        
        try:
            async with httpx.AsyncClient(timeout=client_timeout, follow_redirects=True) as client:
                for i in range(0, len(cache_miss_articles), batch_size):
                    batch = cache_miss_articles[i:i+batch_size]
                    batch_res = await query_ollama_batch(batch, client, stats)
                    
                    # Map results back by URL
                    url_to_result = {}
                    for res in batch_res.get("results", []):
                        url = res.get("url")
                        if url:
                            url_to_result[url] = res
                            
                    for art in batch:
                        url = art["url"]
                        res = url_to_result.get(url)
                        
                        if res and validate_llm_output(res):
                            # Extract schema properties
                            insights = {
                                "executive_summary": res["executive_summary"],
                                "business_implications": res["business_implications"],
                                "ai_relevance": res["ai_relevance"],
                                "industry_categories": res["industry_categories"],
                                "innovation_score": res["innovation_score"],
                                "sentiment": res["sentiment"]
                            }
                            # Update article
                            for k, v in insights.items():
                                art[k] = v
                            # Save to cache
                            if settings.LLM_CACHE_ENABLED:
                                save_cached_llm_insights(article_keys[url], insights)
                            stats["enriched_count"] += 1
                        else:
                            # Fallback gracefully for this single article
                            logger.info(f"Using default fallback insights for article: {art['title']}")
                            for k, v in DEFAULT_LLM_INSIGHTS.items():
                                art[k] = v
                                
        except Exception as e:
            logger.error(f"Failed to connect to local Ollama or execute batch enrichment: {e}")
            # Ollama completely down fallback - set default insights so UI doesn't look empty
            for art in cache_miss_articles:
                # Set default fallback
                for k, v in DEFAULT_LLM_INSIGHTS.items():
                    art[k] = v
                
    total_duration = time.perf_counter() - start_time
    
    # 3. Log Performance & Metrics
    logger.info("=" * 60)
    logger.info("LLM INTELLIGENCE ENRICHMENT METRICS")
    logger.info("=" * 60)
    logger.info(f"Total Enrichment Duration:      {total_duration:.3f} seconds")
    logger.info(f"Articles Processed:             {len(articles)}")
    logger.info(f"Successfully Enriched:          {stats['enriched_count']}")
    logger.info(f"Cache Hits:                     {stats['cache_hits']}")
    logger.info(f"Cache Misses:                   {stats['cache_misses']}")
    logger.info(f"Ollama API Calls:               {stats['ollama_requests']}")
    logger.info(f"Ollama Cumulative Duration:     {stats['ollama_duration']:.3f} seconds")
    logger.info(f"Ollama Retry Count:             {stats['retry_count']}")
    logger.info(f"JSON Validation Failures:       {stats['json_validation_failures']}")
    logger.info("=" * 60)
    
    return articles
