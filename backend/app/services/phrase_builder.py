import httpx
import json
import logging
import asyncio
from typing import List
from app.config import settings
from app.services.cache import TTLLRUCache
from app.services.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

# Bounded in-memory cache for phrase expansions (TTL: 24 hours, max size: 500)
_phrase_cache = TTLLRUCache(maxsize=500, ttl_seconds=86400)

async def expand_keyword(keyword: str) -> List[str]:
    """
    Use Gemini Flash to expand a raw keyword into 3-4 professional search phrases.
    Falls back to using the raw keyword if API key is not configured or errors occur.
    Uses an in-memory TTL LRU cache to avoid duplicate remote API calls.
    """
    keyword_clean = keyword.strip()
    
    # 1. Check cache first
    cached_phrases = _phrase_cache.get(keyword_clean)
    if cached_phrases is not None:
        logger.info(f"Using cached phrase expansion for '{keyword_clean}': {cached_phrases}")
        return cached_phrases
        
    gemini_client = GeminiClient()
    if not gemini_client.api_key:
        logger.warning("GEMINI_API_KEY is not set. Using raw keyword fallback.")
        return _get_fallback_phrases(keyword_clean)
        
    system_prompt = (
        "You are a professional search optimizer. Expand the input keyword or topic into exactly "
        "3 to 4 distinct, professional search queries optimized for news search engines (like NewsAPI or Google News). "
        "The queries should be concise (2-4 words) and target different facets (e.g. technology, market, sustainability). "
        "Return ONLY a JSON array of strings. Do not include markdown codeblocks or extra text."
    )
    
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"Keyword: {keyword_clean}"}]
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "ARRAY",
                "items": {
                    "type": "STRING"
                }
            },
            "temperature": 0.2
        }
    }
    
    try:
        response = await gemini_client.post_request_with_retry(payload)
        data = response.json()
        
        # Extract candidate text
        text_response = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        
        # Parse the JSON response
        phrases = json.loads(text_response)
        if isinstance(phrases, list) and all(isinstance(p, str) for p in phrases):
            logger.info(f"Expanded '{keyword_clean}' into: {phrases}")
            # Cache the successful result
            _phrase_cache.set(keyword_clean, phrases)
            return phrases
        else:
            logger.warning(f"Unexpected response format from Gemini: {text_response}")
            return _get_fallback_phrases(keyword_clean)
    except Exception as e:
        logger.error(f"Gemini phrase expansion failed for '{keyword_clean}': {e}. Using fallback.")
        return _get_fallback_phrases(keyword_clean)

def _get_fallback_phrases(keyword: str) -> List[str]:
    """Fallback generator in case Gemini API is not accessible."""
    return [keyword]
