import logging
import asyncio
from typing import List, Dict, Any
from app.config import settings
from app.services.news_fetcher import fetch_from_newsapi, fetch_from_gnews, fetch_from_mediastack

logger = logging.getLogger(__name__)

async def fetch_pinned_articles() -> List[Dict[str, Any]]:
    """
    Fetch up to 5 technology articles representing NVIDIA, Microsoft, and OpenAI.
    Ensures representation of all three companies.
    Falls back to mock tech articles if APIs are not configured.
    """
    has_keys = any([settings.news_api_key_resolved, settings.gnews_key_resolved, settings.mediastack_key_resolved])
    
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
        if settings.mediastack_key_resolved:
            tasks.append(fetch_from_mediastack(phrase))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        company_articles = []
        for result in results:
            if isinstance(result, Exception) or not result:
                continue
            for art in result:
                art["company"] = company
                art["is_pinned"] = True
                company_articles.append(art)
                
        # Take the top 2 articles for this company to merge later
        all_pinned.extend(company_articles[:2])
        
    # If API requests returned nothing, load mock pinned
    if not all_pinned:
        return _generate_mock_pinned()
        
    # Deduplicate and limit to exactly 5 articles, ensuring round-robin representation
    final_pinned = []
    seen_urls = set()
    
    # Round robin selection to ensure representation of each company if possible
    for idx in range(3):  # up to 3 articles per company
        for company in companies:
            matching = [a for a in all_pinned if a.get("company") == company and a["url"] not in seen_urls]
            if matching and len(final_pinned) < 5:
                art = matching[0]
                seen_urls.add(art["url"])
                final_pinned.append(art)
                
    return final_pinned

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
