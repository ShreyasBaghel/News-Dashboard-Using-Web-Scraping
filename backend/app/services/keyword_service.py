import logging
import json
from typing import List, Optional
import httpx
from app.config import settings
from app.services.cache import get_cached_keywords_for_article, save_cached_keywords_for_article

logger = logging.getLogger(__name__)

async def generate_article_keywords(
    title: str,
    description: str,
    content: str,
    url: str,
    client: Optional[httpx.AsyncClient] = None
) -> List[str]:
    """
    Generates exactly 3 semantic search keywords for an article using Gemini Flash.
    Uses cached keywords if already generated.
    """
    # 1. Check cache first
    cached_kws = get_cached_keywords_for_article(url)
    if cached_kws:
        logger.info(f"Using cached keywords for article: {url} -> {cached_kws}")
        return cached_kws

    # Forbidden generic terms that should not be used as keywords
    forbidden = {"news", "article", "update", "latest", "report", "today", "technology", "business", "company", "information"}

    # If mock article or empty content, return quick fallback keywords based on title/domain
    if "-mock.com" in url or not content:
        # Simple extraction from title to look a bit realistic
        words = [w.strip(".,;:!?()[]{}'\"-") for w in title.split()]
        candidates = []
        seen_cand = set()
        for w in words:
            if len(w) > 3 and w.lower() not in forbidden and w.lower() not in {"how", "what", "with", "from", "that", "this", "your", "their"}:
                if w.lower() not in seen_cand:
                    seen_cand.add(w.lower())
                    candidates.append(w)
        # Pad if needed
        while len(candidates) < 3:
            candidates.append("Manufacturing")
        fallback = candidates[:3]
        save_cached_keywords_for_article(url, fallback)
        return fallback

    from app.services.gemini_client import GeminiClient
    gemini_client = GeminiClient()

    if not gemini_client.api_key:
        logger.warning("GEMINI_API_KEY not configured. Returning fallback keywords.")
        return ["Manufacturing", "Industrial Technology", "General"]

    system_prompt = (
        "You are an expert news analyst. Analyze the provided article's title, summary, and content to identify exactly 3 concise, high-quality, meaningful search keywords or tags representing the article's primary topics.\n"
        "Requirements:\n"
        "1. You MUST return exactly 3 keywords.\n"
        "2. The keywords must be unique (no duplicates).\n"
        "3. Do NOT use generic words like: 'news', 'article', 'update', 'latest', 'report', 'today', 'technology', 'business', 'company', 'information'.\n"
        "4. Prefer specific: company names, technologies, products, organizations, countries, people, events, AI topics, cybersecurity topics, finance topics, scientific topics.\n"
        "Format your output in strict JSON with a single key 'keywords' containing the array of 3 strings. Example:\n"
        "{\n"
        '  "keywords": ["NVIDIA", "Blackwell", "AI GPU"]\n'
        "}"
    )

    user_prompt = f"Article Title: {title}\n"
    if description:
        user_prompt += f"Article Summary/Description: {description}\n"
    if content:
        user_prompt += f"Article Content: {content[:4000]}\n"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_prompt}]
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "keywords": {
                        "type": "ARRAY",
                        "items": {
                            "type": "STRING"
                        }
                    }
                },
                "required": ["keywords"]
            },
            "temperature": 0.1
        }
    }

    try:
        response = await gemini_client.post_request_with_retry(payload, client)
        res_data = response.json()
        res_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        parsed = json.loads(res_text)
        keywords = parsed.get("keywords", [])
        
        # Clean and deduplicate case-insensitively
        cleaned_kws = []
        seen = set()
        for k in keywords:
            k_clean = str(k).strip()
            if not k_clean:
                continue
            k_lower = k_clean.lower()
            if k_lower in forbidden:
                continue
            if k_lower not in seen:
                seen.add(k_lower)
                cleaned_kws.append(k_clean)
        
        # Adjust/truncate/pad to exactly 3
        if len(cleaned_kws) != 3:
            if len(cleaned_kws) > 3:
                cleaned_kws = cleaned_kws[:3]
            else:
                fallbacks = ["Manufacturing", "Industrial Technology", "Automation", "AI", "Cement Industry"]
                for fb in fallbacks:
                    if len(cleaned_kws) >= 3:
                        break
                    if fb.lower() not in seen and fb.lower() not in forbidden:
                        seen.add(fb.lower())
                        cleaned_kws.append(fb)
        
        save_cached_keywords_for_article(url, cleaned_kws)
        return cleaned_kws
    except Exception as e:
        logger.error(f"Gemini keyword generation failed: {e}. Returning fallback keywords (not saved to cache).")
        # Find 3 words from title as fallback
        words = [w.strip(".,;:!?()[]{}'\"-") for w in title.split()]
        candidates = []
        seen_cand = set()
        for w in words:
            if len(w) > 3 and w.lower() not in forbidden:
                if w.lower() not in seen_cand:
                    seen_cand.add(w.lower())
                    candidates.append(w)
        while len(candidates) < 3:
            candidates.append("Manufacturing")
        return candidates[:3]
