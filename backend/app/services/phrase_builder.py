import httpx
import json
import logging
import asyncio
from typing import List
from app.config import settings

logger = logging.getLogger(__name__)

async def expand_keyword(keyword: str) -> List[str]:
    """
    Use Gemini Flash to expand a raw keyword into 3-4 professional search phrases.
    Falls back to using the raw keyword if API key is not configured or errors occur.
    """
    keyword_clean = keyword.strip()
    
    # Check if Gemini API key is provided
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is not set. Using raw keyword fallback.")
        return _get_fallback_phrases(keyword_clean)
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={settings.GEMINI_API_KEY}"
    
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
                "parts": [{"text": f"System prompt: {system_prompt}\nKeyword: {keyword_clean}"}]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2
        }
    }
    
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                
                data = response.json()
                # Extract candidate text
                text_response = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                
                # Parse the JSON response
                phrases = json.loads(text_response)
                if isinstance(phrases, list) and all(isinstance(p, str) for p in phrases):
                    logger.info(f"Expanded '{keyword_clean}' into: {phrases}")
                    return phrases
                else:
                    logger.warning(f"Unexpected response format from Gemini (attempt {attempt}): {text_response}")
                    if attempt == max_retries:
                        return _get_fallback_phrases(keyword_clean)
        except Exception as e:
            logger.warning(f"Gemini API request failed on attempt {attempt}: {str(e)}")
            if attempt == max_retries:
                logger.error(f"All {max_retries} attempts for Gemini phrase expansion failed. Using fallback.")
                return _get_fallback_phrases(keyword_clean)
            await asyncio.sleep(1.0 * attempt)
            
    return _get_fallback_phrases(keyword_clean)

def _get_fallback_phrases(keyword: str) -> List[str]:
    """Fallback generator in case Gemini API is not accessible."""
    return [keyword]
