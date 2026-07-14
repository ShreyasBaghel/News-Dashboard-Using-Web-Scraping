import logging
import asyncio
from typing import List, Dict, Any
from app.config import settings
from app.services.news_fetcher import fetch_from_newsapi, fetch_from_gnews
from app.services.language_detector import is_english

logger = logging.getLogger(__name__)

async def fetch_pinned_articles() -> List[Dict[str, Any]]:
    """
    Fetch all available technology articles representing NVIDIA, Microsoft, and OpenAI.
    Returns all candidates so that the pipeline can validate and filter them.
    Falls back to mock tech articles if APIs are not configured.
    """
    has_keys = any([settings.news_api_key_resolved, settings.gnews_key_resolved, settings.newsdata_key_resolved])
    
    if not has_keys:
        logger.info("No news API keys configured. Loading mock pinned articles.")
        return _generate_mock_pinned()
        
    companies = settings.PINNED_COMPANIES  # NVIDIA, Microsoft, OpenAI
    all_pinned = []
    
    # We will fetch articles for each company
    for company in companies:
        phrase = f"{company} AI technology"
        logger.info(f"Fetching pinned articles for company: '{company}'")
        
        # Query active providers
        tasks = []
        if settings.news_api_key_resolved:
            tasks.append(fetch_from_newsapi(phrase))
        if settings.gnews_key_resolved:
            tasks.append(fetch_from_gnews(phrase))
        if settings.newsdata_key_resolved:
            from app.services.news_fetcher import fetch_from_newsdata
            tasks.append(fetch_from_newsdata(phrase))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        company_articles = []
        for result in results:
            if isinstance(result, Exception) or not result:
                continue
            for art in result:
                # Check language of pinned article candidates
                if not is_english(art.get("title", ""), art.get("description", "") or ""):
                    logger.info(f"Skipping pinned article '{art.get('title')}' because it is detected as non-English.")
                    continue
                art["company"] = company
                art["is_pinned"] = True
                company_articles.append(art)
                
        # Take all articles for this company to validate later
        all_pinned.extend(company_articles)
        
    # If API requests returned nothing, load mock pinned
    if not all_pinned:
        return _generate_mock_pinned()
        
    return all_pinned

def _generate_mock_pinned() -> List[Dict[str, Any]]:
    """Return high-quality mock technology articles for NVIDIA, Microsoft, and OpenAI."""
    return [
        {
            "title": "NVIDIA Blackwell B200 GPUs Enter Full Production for Enterprise AI Cloud Scale",
            "url": "https://www.nvidiapinned-mock.com/blackwell-b200-production",
            "source": "Hardware Horizon",
            "published_at": "2026-06-29T08:00:00Z",
            "description": "NVIDIA Blackwell B200 GPUs are now in full production, offering cloud scale performance for generative AI workflows.",
            "company": "NVIDIA",
            "is_pinned": True
        },
        {
            "title": "Microsoft Announces Copilot Studio V2 with Advanced Multi-Agent Orchestration",
            "url": "https://www.microsoftpinned-mock.com/copilot-studio-v2-agents",
            "source": "Redmond Inside",
            "published_at": "2026-06-29T09:15:00Z",
            "description": "Microsoft introduces Copilot Studio V2, featuring complex multi-agent orchestration for enterprise automation tasks.",
            "company": "Microsoft",
            "is_pinned": True
        },
        {
            "title": "OpenAI GPT-5 Achieves Unprecedented Multi-Modal Logic and Reasoning Benchmarks",
            "url": "https://www.openaipinned-mock.com/gpt-5-reasoning-launch",
            "source": "AI Vanguard",
            "published_at": "2026-06-29T10:30:00Z",
            "description": "OpenAI's upcoming GPT-5 model hits landmark scores in multi-modal reasoning and complex programming evaluations.",
            "company": "OpenAI",
            "is_pinned": True
        },
        {
            "title": "NVIDIA Isaac Robotics Platform Receives Generative AI Physical Foundation Models",
            "url": "https://www.nvidiapinned-mock.com/isaac-robotics-generative-ai",
            "source": "RoboTech Monthly",
            "published_at": "2026-06-28T11:45:00Z",
            "description": "NVIDIA integrates generative AI physical foundation models into its Isaac robotics stack to accelerate automated task handling.",
            "company": "NVIDIA",
            "is_pinned": True
        },
        {
            "title": "Microsoft and OpenAI Partner on $100B Stargate Supercomputer Project",
            "url": "https://www.microsoftpinned-mock.com/stargate-supercomputer-project",
            "source": "Tech Infrastructure",
            "published_at": "2026-06-28T15:00:00Z",
            "description": "Microsoft and OpenAI collaborate on a massive $100 billion supercomputing cluster named Stargate to power future AI models.",
            "company": "Microsoft",
            "is_pinned": True
        }
    ]
