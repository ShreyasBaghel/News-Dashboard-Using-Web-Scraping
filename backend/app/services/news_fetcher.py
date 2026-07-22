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

async def fetch_from_rss(phrases: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch and parse RSS feeds configured in config/rss_sources.json.
    Normalizes metadata and filters articles matching query phrases.
    """
    import os
    import json
    from bs4 import BeautifulSoup
    
    config_path = settings.RSS_SOURCES_PATH
    if not os.path.exists(config_path):
        logger.warning(f"RSS configuration file not found at {config_path}. Skipping RSS fetching.")
        return []
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            sources_config = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read RSS sources config: {e}")
        return []
        
    feeds = []
    for category, feed_list in sources_config.items():
        for feed in feed_list:
            if feed.get("url") and feed.get("name"):
                feeds.append(feed)
                
    if not feeds:
        logger.warning("No feeds defined in RSS sources configuration.")
        return []
        
    logger.info(f"Processing {len(feeds)} RSS feeds for phrases: {phrases}")
    
    async def fetch_feed(feed: Dict[str, str], client: httpx.AsyncClient) -> Optional[str]:
        try:
            logger.info(f"Fetching RSS feed: {feed['name']} ({feed['url']})")
            response = await client.get(feed["url"], timeout=10.0)
            if response.status_code == 200:
                return response.text
        except Exception as e:
            logger.warning(f"Failed to fetch RSS feed {feed['name']}: {e}")
        return None

    timeout_cfg = httpx.Timeout(connect=3.0, read=10.0, write=3.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout_cfg, follow_redirects=True) as client:
        tasks = [fetch_feed(feed, client) for feed in feeds]
        xml_contents = await asyncio.gather(*tasks)
        
    rss_articles = []
    seen_urls = set()
    cleaned_phrases = [p.strip().lower() for p in phrases if p.strip()]
    
    for feed, xml_content in zip(feeds, xml_contents):
        if not xml_content:
            continue
            
        try:
            soup = BeautifulSoup(xml_content, "xml")
            items = soup.find_all("item")
            is_atom = False
            if not items:
                items = soup.find_all("entry")
                is_atom = True
                
            feed_articles_count = 0
            for item in items:
                title = ""
                url = ""
                description = ""
                pub_date = ""
                
                if is_atom:
                    title_el = item.find("title")
                    title = title_el.text if title_el else ""
                    
                    link_el = item.find("link")
                    if link_el:
                        url = link_el.get("href") or link_el.text
                        
                    summary_el = item.find("summary") or item.find("content")
                    description = summary_el.text if summary_el else ""
                    
                    pub_el = item.find("published") or item.find("updated")
                    pub_date = pub_el.text if pub_el else ""
                else:
                    title_el = item.find("title")
                    title = title_el.text if title_el else ""
                    
                    link_el = item.find("link")
                    url = link_el.text if link_el else ""
                    
                    desc_el = item.find("description")
                    description = desc_el.text if desc_el else ""
                    
                    pub_el = item.find("pubDate")
                    pub_date = pub_el.text if pub_el else ""
                    
                title = title.strip()
                url = url.strip()
                description = description.strip()
                pub_date = pub_date.strip()
                
                if not title or not url:
                    continue
                    
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                
                text_to_check = f"{title} {description}".lower()
                matches_any_phrase = False
                for phrase in cleaned_phrases:
                    if phrase in text_to_check:
                        matches_any_phrase = True
                        break
                        
                if not matches_any_phrase:
                    continue
                    
                rss_articles.append({
                    "title": title,
                    "url": url,
                    "source": feed["name"],
                    "published_at": pub_date,
                    "description": description[:300]
                })
                feed_articles_count += 1
                
            logger.info(f"RSS feed '{feed['name']}' found {feed_articles_count} matching articles.")
        except Exception as e:
            logger.warning(f"Error parsing XML content for RSS feed '{feed['name']}': {e}")
            
    deduped = []
    seen_dedup = set()
    for art in rss_articles:
        if art["url"] not in seen_dedup:
            seen_dedup.add(art["url"])
            deduped.append(art)
            
    from app.services.diversity import getNormalizedDomain
    domain_counts = {}
    diversity_filtered = []
    for art in deduped:
        dom = getNormalizedDomain(art["url"])
        count = domain_counts.get(dom, 0)
        if count < 3:
            domain_counts[dom] = count + 1
            diversity_filtered.append(art)
            
    selected = diversity_filtered[:15]
    logger.info(f"RSS fetching completed: feeds_processed={len(feeds)}, articles_found={len(deduped)}, articles_selected={len(selected)}")
    return selected

async def fetch_from_hackernews(phrase: str) -> List[Dict[str, Any]]:
    """
    Fetch news from Hacker News Algolia Search API.
    Skip Ask HN, Show HN, dead/deleted, and stories without external URLs.
    """
    url = "https://hn.algolia.com/api/v1/search"
    params = {
        "query": phrase,
        "tags": "story",
        "hitsPerPage": 20
    }
    
    try:
        timeout_cfg = httpx.Timeout(connect=3.0, read=10.0, write=3.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout_cfg, follow_redirects=True) as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                articles = []
                stories_fetched = 0
                stories_accepted = 0
                
                for item in data.get("hits", []):
                    stories_fetched += 1
                    title = item.get("title", "")
                    ext_url = item.get("url", "")
                    
                    title_lower = title.lower().strip()
                    if title_lower.startswith("ask hn:") or title_lower.startswith("show hn:"):
                        continue
                    if "[dead]" in title_lower or "[deleted]" in title_lower:
                        continue
                    if not ext_url or "news.ycombinator.com/item" in ext_url:
                        continue
                        
                    created_at = item.get("created_at", "")
                    
                    articles.append({
                        "title": title,
                        "url": ext_url,
                        "source": "Hacker News",
                        "published_at": created_at,
                        "description": f"Hacker News story by {item.get('author', 'unknown')}. Points: {item.get('points', 0)}."
                    })
                    stories_accepted += 1
                    
                logger.info(f"Hacker News fetched: {stories_fetched} stories, accepted: {stories_accepted} for phrase '{phrase}'")
                return articles
            else:
                logger.warning(f"Hacker News API returned status {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Failed to query Hacker News: {str(e)}")
    return []

async def fetch_from_newsdata(phrase: str, page: int = 1) -> List[Dict[str, Any]]:
    """
    Fetch news from NewsData.io.
    Implements persistent credit protection using database.
    """
    key = settings.newsdata_key_resolved
    if not key:
        logger.warning("NewsData.io key is not configured.")
        return []
        
    from datetime import datetime, timezone
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    from app.services.cache import get_newsdata_usage, increment_newsdata_usage
    current_usage = get_newsdata_usage(today_str)
    
    if current_usage >= settings.NEWSDATA_DAILY_LIMIT:
        logger.warning(f"NewsData.io daily quota reached ({current_usage}/{settings.NEWSDATA_DAILY_LIMIT} requests). Skipping NewsData.io requests.")
        return []
        
    url = "https://newsdata.io/api/1/latest"
    params = {
        "apikey": key,
        "q": phrase,
        "language": "en"
    }
    if page > 1:
        return []
        
    try:
        timeout_cfg = httpx.Timeout(connect=3.0, read=10.0, write=3.0, pool=5.0)
        logger.info(f"NewsData.io request: phrase='{phrase}', today_usage={current_usage}")
        
        async with httpx.AsyncClient(timeout=timeout_cfg, follow_redirects=True) as client:
            response = await client.get(url, params=params)
            
            # Increment request counter (save to persistent database storage)
            increment_newsdata_usage(today_str)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "error":
                    err = data.get("results", {})
                    logger.error(f"NewsData.io returned error: {err.get('message')}")
                    if "limit" in err.get("message", "").lower() or err.get("code") == "UsageLimitExceeded":
                        _failed_providers.add("newsdata")
                    return []
                    
                articles = []
                for item in data.get("results", []):
                    title = item.get("title")
                    link = item.get("link")
                    if title and link:
                        articles.append({
                            "title": title,
                            "url": link,
                            "source": item.get("source_id", "NewsData"),
                            "published_at": item.get("pubDate", ""),
                            "description": item.get("description", "") or ""
                        })
                return articles
            else:
                if response.status_code in (429, 403):
                    logger.error(f"NewsData.io quota limit reached (Status {response.status_code}). Triggering rotation/fallback.")
                    _failed_providers.add("newsdata")
                else:
                    logger.warning(f"NewsData.io returned status {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Failed to query NewsData.io: {str(e)}")
    return []

async def fetch_news_for_phrases(
    phrases: List[str],
    page: int = 1,
    is_pool_generation: bool = False
) -> List[Dict[str, Any]]:
    """
    Fetch news for all expanded phrases using configured APIs.
    Filters out already seen URLs. Falls back to mock news if no APIs are configured
    or if all configured APIs hit quota limits.
    """
    has_keys = any([settings.news_api_key_resolved, settings.gnews_key_resolved, settings.newsdata_key_resolved])
    
    all_articles = []
    seen_urls = set()
    
    # 1. RSS Support (pool-generation only)
    if is_pool_generation and page == 1:
        try:
            rss_results = await fetch_from_rss(phrases)
            for art in rss_results:
                url = art.get("url")
                if url and url not in seen_urls and not is_url_seen(url):
                    seen_urls.add(url)
                    all_articles.append(art)
        except Exception as e:
            logger.error(f"Error fetching RSS: {e}")
            
    # 2. Hacker News Support (pool-generation only)
    if is_pool_generation and page == 1:
        for phrase in phrases:
            try:
                hn_results = await fetch_from_hackernews(phrase)
                for art in hn_results:
                    url = art.get("url")
                    if url and url not in seen_urls and not is_url_seen(url):
                        seen_urls.add(url)
                        all_articles.append(art)
            except Exception as e:
                logger.error(f"Error fetching Hacker News for phrase '{phrase}': {e}")
                
    # Reset failed providers for a new pipeline fetch session (only on page 1)
    if page == 1:
        reset_failed_providers()
        
    for phrase in phrases:
        logger.info(f"Fetching news articles for query phrase: '{phrase}' (page {page})")
        
        phrase_articles = []
        
        # Priority 1: NewsAPI
        if settings.news_api_key_resolved and "newsapi" not in _failed_providers:
            try:
                res = await fetch_from_newsapi(phrase, page=page)
                if res:
                    phrase_articles.extend(res)
            except Exception as e:
                logger.error(f"NewsAPI error: {e}")
                _failed_providers.add("newsapi")
                
        # Priority 2: GNews
        if not phrase_articles and settings.gnews_key_resolved and "gnews" not in _failed_providers:
            try:
                res = await fetch_from_gnews(phrase, page=page)
                if res:
                    phrase_articles.extend(res)
            except Exception as e:
                logger.error(f"GNews error: {e}")
                _failed_providers.add("gnews")
                
        # Priority 3: NewsData.io
        if not phrase_articles and settings.newsdata_key_resolved and "newsdata" not in _failed_providers:
            try:
                res = await fetch_from_newsdata(phrase, page=page)
                if res:
                    phrase_articles.extend(res)
            except Exception as e:
                logger.error(f"NewsData error: {e}")
                _failed_providers.add("newsdata")
                
        # Merge results for this phrase
        for art in phrase_articles:
            url = art.get("url")
            if url and url not in seen_urls and not is_url_seen(url):
                seen_urls.add(url)
                all_articles.append(art)
                
    # If API requests and RSS/HN returned nothing, fall back to mock news so the PoC works (only on page 1)
    if not all_articles:
        if page == 1:
            logger.warning("All active fetches returned 0 articles. Falling back to mock articles.")
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
    
    selected = []
    seen = set()
    
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
    sources: Optional[List[str]] = None,
    is_pool_generation: bool = False
) -> List[Dict[str, Any]]:
    """
    Stable, provider-agnostic public interface to retrieve news articles.
    All provider fallback, quota errors, rotation and API selection logic are encapsulated here.
    Returns a normalized list of raw article dictionary structures.
    """
    articles = await fetch_news_for_phrases(phrases, page=page, is_pool_generation=is_pool_generation)
    
    if sources:
        sources_lower = {s.lower() for s in sources}
        articles = [a for a in articles if a.get("source", "").lower() in sources_lower]
        
    if limit:
        articles = articles[:limit]
        
    return articles
