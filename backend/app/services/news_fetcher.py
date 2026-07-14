import httpx
import logging
import asyncio
from typing import List, Dict, Any, Optional
from app.config import settings
from app.services.cache import is_url_seen

logger = logging.getLogger(__name__)

# Providers tracking for quota error fallback/rotation
_failed_providers = set()

def reset_failed_providers():
    """Reset the set of failed/quota-exceeded providers (e.g. for a new pipeline run)."""
    _failed_providers.clear()

async def fetch_from_newsapi(phrase: str, page: int = 1) -> List[Dict[str, Any]]:
    """
    Fetch news from NewsAPI.
    Returns normalized list of {title, url, source, published_at, description}.
    """
    key = settings.news_api_key_resolved
    if not key:
        logger.warning("NewsAPI key is not configured.")
        return []
    
    if "newsapi" in _failed_providers:
        logger.info("NewsAPI is marked as failed/quota-exceeded. Skipping.")
        return []

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": phrase,
        "apiKey": key,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 10,
        "page": page
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            
            # Detect quota / rate limit errors
            if response.status_code in (429, 403):
                logger.error(f"NewsAPI quota limit reached (Status {response.status_code}). Triggering fallback/rotation.")
                _failed_providers.add("newsapi")
                return []
                
            if response.status_code == 200:
                data = response.json()
                articles = []
                for item in data.get("articles", []):
                    if item.get("title") and item.get("url"):
                        articles.append({
                            "title": item["title"],
                            "url": item["url"],
                            "source": item.get("source", {}).get("name", "NewsAPI"),
                            "published_at": item.get("publishedAt", ""),
                            "description": item.get("description", "") or ""
                        })
                return articles
            else:
                logger.warning(f"NewsAPI returned status {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Failed to query NewsAPI: {str(e)}")
    return []

async def fetch_from_gnews(phrase: str, page: int = 1) -> List[Dict[str, Any]]:
    """
    Fetch news from GNews.
    Returns normalized list of {title, url, source, published_at, description}.
    """
    key = settings.gnews_key_resolved
    if not key:
        logger.warning("GNews key is not configured.")
        return []

    if "gnews" in _failed_providers:
        logger.info("GNews is marked as failed/quota-exceeded. Skipping.")
        return []

    url = "https://gnews.io/api/v4/search"
    params = {
        "q": phrase,
        "apikey": key,
        "lang": "en",
        "max": 10,
        "page": page
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            
            # Detect quota / rate limit errors
            if response.status_code in (429, 403):
                logger.error(f"GNews quota limit reached (Status {response.status_code}). Triggering fallback/rotation.")
                _failed_providers.add("gnews")
                return []

            if response.status_code == 200:
                data = response.json()
                articles = []
                for item in data.get("articles", []):
                    if item.get("title") and item.get("url"):
                        articles.append({
                            "title": item["title"],
                            "url": item["url"],
                            "source": item.get("source", {}).get("name", "GNews"),
                            "published_at": item.get("publishedAt", ""),
                            "description": item.get("description", "") or ""
                        })
                return articles
            else:
                logger.warning(f"GNews returned status {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Failed to query GNews: {str(e)}")
    return []

async def fetch_from_mediastack(phrase: str, page: int = 1) -> List[Dict[str, Any]]:
    """
    Fetch news from Mediastack.
    Returns normalized list of {title, url, source, published_at, description}.
    """
    key = settings.mediastack_key_resolved
    if not key:
        logger.warning("Mediastack key is not configured.")
        return []

    if "mediastack" in _failed_providers:
        logger.info("Mediastack is marked as failed/quota-exceeded. Skipping.")
        return []

    url = "http://api.mediastack.com/v1/news"
    limit = 10
    offset = (page - 1) * limit
    params = {
        "access_key": key,
        "keywords": phrase,
        "languages": "en",
        "limit": limit,
        "offset": offset
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                
                # Mediastack quota errors come in response JSON with 200 status
                if "error" in data:
                    err = data["error"]
                    logger.error(f"Mediastack quota limit reached or error: {err.get('code')} - {err.get('message')}. Triggering fallback/rotation.")
                    _failed_providers.add("mediastack")
                    return []
                    
                articles = []
                for item in data.get("data", []):
                    if item.get("title") and item.get("url"):
                        articles.append({
                            "title": item["title"],
                            "url": item["url"],
                            "source": item.get("source", "Mediastack"),
                            "published_at": item.get("published_at", ""),
                            "description": item.get("description", "") or ""
                        })
                return articles
            else:
                logger.warning(f"Mediastack returned status {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Failed to query Mediastack: {str(e)}")
    return []

async def fetch_news_for_phrases(phrases: List[str], page: int = 1) -> List[Dict[str, Any]]:
    """
    Fetch news for all expanded phrases using configured APIs.
    Filters out already seen URLs. Falls back to mock news if no APIs are configured
    or if all configured APIs hit quota limits.
    """
    has_keys = any([settings.news_api_key_resolved, settings.gnews_key_resolved, settings.mediastack_key_resolved])
    
    if not has_keys:
        if page == 1:
            logger.warning("No news API keys found in configuration. Generating mock articles.")
            return _generate_mock_news(phrases)
        else:
            return []
        
    all_articles = []
    seen_urls = set()
    
    # Reset failed providers for a new pipeline fetch session (only on page 1)
    if page == 1:
        reset_failed_providers()
    
    for phrase in phrases:
        logger.info(f"Fetching news articles for query phrase: '{phrase}' (page {page})")
        
        # Build list of active tasks based on rotation/fallback state
        tasks = []
        providers = []
        
        if settings.news_api_key_resolved and "newsapi" not in _failed_providers:
            tasks.append(fetch_from_newsapi(phrase, page=page))
            providers.append("newsapi")
        if settings.gnews_key_resolved and "gnews" not in _failed_providers:
            tasks.append(fetch_from_gnews(phrase, page=page))
            providers.append("gnews")
        if settings.mediastack_key_resolved and "mediastack" not in _failed_providers:
            tasks.append(fetch_from_mediastack(phrase, page=page))
            providers.append("mediastack")
            
        if not tasks:
            logger.warning("All configured news APIs have failed or hit quota limits.")
            continue
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for provider, result in zip(providers, results):
            if isinstance(result, Exception):
                logger.error(f"{provider} fetch error: {str(result)}")
                continue
            if result:
                for art in result:
                    url = art.get("url")
                    if url and url not in seen_urls and not is_url_seen(url):
                        seen_urls.add(url)
                        all_articles.append(art)
                        
    # If API requests returned nothing, fall back to mock news so the PoC works (only on page 1)
    if not all_articles:
        if page == 1:
            logger.warning("API fetches returned 0 articles. Falling back to mock articles.")
            return _generate_mock_news(phrases)
        else:
            return []
        
    return all_articles

def _generate_mock_news(phrases: List[str]) -> List[Dict[str, Any]]:
    """Generate realistic placeholder industry/tech news matching the phrases."""
    mock_db = [
        {
            "keyword_match": "cement",
            "articles": [
                {
                    "title": "Dalmia Cement Unveils Carbon Capture Pilot Plant in India",
                    "url": "https://www.cementnews-mock.com/dalmia-carbon-capture-2026",
                    "source": "Cement & Concrete Journal",
                    "published_at": "2026-06-29T10:00:00Z",
                    "description": "Dalmia Cement has commissioned a carbon capture pilot facility at its major manufacturing unit to explore sustainable kiln operations."
                },
                {
                    "title": "Decarbonizing the Cement Sector: New H2-Based Kilns Show Promise",
                    "url": "https://www.cementnews-mock.com/decarbonizing-kilns-hydrogen",
                    "source": "Global Green Build",
                    "published_at": "2026-06-28T14:30:00Z",
                    "description": "Hydrogen-fueled kilns are demonstrating promising thermal efficiency improvements and carbon reduction in early test trials."
                },
                {
                    "title": "Green Cement Market size projected to reach $65B by 2030",
                    "url": "https://www.cementnews-mock.com/green-cement-market-2030",
                    "source": "Eco-Industry Analysis",
                    "published_at": "2026-06-27T08:15:00Z",
                    "description": "Market forecasts indicate robust growth for green, low-carbon cement products, driven by global infrastructure demand."
                },
                {
                    "title": "AI in Concrete Mix Design: Reducing Costs While Boosting Strength",
                    "url": "https://www.cementnews-mock.com/ai-concrete-strength-mixes",
                    "source": "Structure Tech Weekly",
                    "published_at": "2026-06-26T11:00:00Z",
                    "description": "Machine learning algorithms optimize raw materials proportioning, reducing cement consumption while maintaining performance."
                }
            ]
        },
        {
            "keyword_match": "ai",
            "articles": [
                {
                    "title": "The Rise of Agentic AI: How Autonomous Workflows are Transforming Enterprise",
                    "url": "https://www.technews-mock.com/rise-of-agentic-ai-2026",
                    "source": "TechCrunch Mock",
                    "published_at": "2026-06-29T09:00:00Z",
                    "description": "Agentic workflows automate complex industrial processes, reasoning and correcting errors autonomously without constant user guidance."
                },
                {
                    "title": "Google DeepMind's Next-Gen Architecture Tackles Zero-Shot Coding Tasks",
                    "url": "https://www.technews-mock.com/deepmind-zero-shot-coding-gemini",
                    "source": "AI Frontiers",
                    "published_at": "2026-06-28T16:45:00Z",
                    "description": "DeepMind releases new model metrics showing massive gains in complex task execution, logical reasoning, and programming pipelines."
                },
                {
                    "title": "Neuromorphic Chips Promise 100x Efficiency Boost for Local LLMs",
                    "url": "https://www.technews-mock.com/neuromorphic-chips-local-llms",
                    "source": "Silicon Insider",
                    "published_at": "2026-06-27T12:00:00Z",
                    "description": "Hardware architectures mimicking brain synapses allow running complex large language models locally on consumer-grade hardware."
                }
            ]
        },
        {
            "keyword_match": "manufacturing",
            "articles": [
                {
                    "title": "Smart Factory Adoption Rates Climb in Heavy Industry Sector",
                    "url": "https://www.factorynews-mock.com/smart-factory-heavy-industry",
                    "source": "Industrial IoT",
                    "published_at": "2026-06-29T07:30:00Z",
                    "description": "IoT connected sensors, advanced edge computing, and real-time visualization dashboards are seeing widespread adoption in smart plants."
                },
                {
                    "title": "Predictive Maintenance Algorithms Prevent Costly Kiln Shutdowns",
                    "url": "https://www.factorynews-mock.com/predictive-maintenance-kiln",
                    "source": "Factory Operations Today",
                    "published_at": "2026-06-28T13:00:00Z",
                    "description": "Thermal imaging cameras and acoustic sensors combined with AI predict equipment anomalies before physical breakdown occurs."
                }
            ]
        },
        {
            "keyword_match": "automation",
            "articles": [
                {
                    "title": "Robotic Automation Reaches Historic Highs in Dry Mortar Plants",
                    "url": "https://www.factorynews-mock.com/robotic-automation-mortar-plants",
                    "source": "Robotics World",
                    "published_at": "2026-06-29T11:20:00Z",
                    "description": "Robotic arms and automated guided vehicles streamline material handling and packaging processes in dry mortar manufacturing facilities."
                },
                {
                    "title": "Hyperautomation in Logistics: Optimizing Cement Fleet Delivery Schedules",
                    "url": "https://www.factorynews-mock.com/hyperautomation-cement-logistics",
                    "source": "SupplyChain Digest",
                    "published_at": "2026-06-27T15:10:00Z",
                    "description": "AI-driven route planning and dynamic scheduling optimize concrete mixer truck dispatching, cutting fuel costs significantly."
                }
            ]
        }
    ]
    
    # Select articles that match the phrases or keywords
    selected = []
    seen = set()
    
    # Check phrases for keyword matching
    for phrase in phrases:
        p_lower = phrase.lower()
        matched_any = False
        for category in mock_db:
            if category["keyword_match"] in p_lower:
                matched_any = True
                for art in category["articles"]:
                    url = art["url"]
                    if url not in seen and not is_url_seen(url):
                        seen.add(url)
                        selected.append(art)
                        
        if not matched_any:
            # Generate generic mock article
            url = f"https://www.genericnews-mock.com/{hash(phrase) % 10000}"
            if url not in seen and not is_url_seen(url):
                seen.add(url)
                selected.append({
                    "title": f"New Trends and Opportunities in {phrase.title()}",
                    "url": url,
                    "source": "Industry Insights Daily",
                    "published_at": "2026-06-29T12:00:00Z",
                    "description": f"An analysis of the key forces shaping {phrase} in modern manufacturing and industrial sectors."
                })
                
    # Return at least some default mock news if list is still empty
    if not selected:
        for category in mock_db:
            for art in category["articles"]:
                url = art["url"]
                if url not in seen and not is_url_seen(url):
                    seen.add(url)
                    selected.append(art)
                    
    return selected


async def fetch_articles(
    phrases: List[str],
    page: int = 1,
    limit: Optional[int] = None,
    sources: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Stable, provider-agnostic public interface to retrieve news articles.
    All provider fallback, quota errors, rotation and API selection logic are encapsulated here.
    Returns a normalized list of raw article dictionary structures:
    {
        "title": str,
        "url": str,
        "source": str,
        "published_at": str,
        "description": str
    }
    """
    # Delegate to the existing fetch orchestration flow, which currently handles fallbacks
    # and mock fallbacks under the hood. In the next phase, RSS/Hacker News/NewsData.io 
    # integration will be added strictly inside this module.
    articles = await fetch_news_for_phrases(phrases, page=page)
    
    if sources:
        # Case-insensitive source filtering if requested
        sources_lower = {s.lower() for s in sources}
        articles = [a for a in articles if a.get("source", "").lower() in sources_lower]
        
    if limit:
        articles = articles[:limit]
        
    return articles
