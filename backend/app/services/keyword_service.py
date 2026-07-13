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
    Generates exactly 3 semantic keywords for an article using Gemini 1.5 Flash.
    Uses cached keywords if already generated.
    """
    # 1. Check cache first
    cached_kws = get_cached_keywords_for_article(url)
    if cached_kws:
        logger.info(f"Using cached keywords for article: {url} -> {cached_kws}")
        return cached_kws

    # If mock article or empty content, return quick fallback keywords
    if "-mock.com" in url or not content:
        # Generate some simple mock keywords based on the title/keywords
        fallback = ["Manufacturing", "Automation", "Industry Insights"]
        save_cached_keywords_for_article(url, fallback)
        return fallback

    from app.services.gemini_client import GeminiClient
    gemini_client = GeminiClient()

    if not gemini_client.api_key:
        logger.warning("GEMINI_API_KEY not configured. Returning fallback keywords.")
        return ["Manufacturing", "Industrial Technology", "General"]

    system_prompt = (
        "You are an expert manufacturing and industrial technology news analyst.\n"
        "Analyze the provided article's title, description, and content to identify exactly three concise, high-quality semantic keywords representing the article's primary topics.\n"
        "These keywords should not simply be nouns extracted from the text; they should represent the core subject matter of the article.\n"
        "Do not generate generic words like 'news', 'article', 'technology', 'business', 'update'.\n"
        "Examples of high-quality semantic keywords:\n"
        "- Industrial AI\n"
        "- Predictive Maintenance\n"
        "- Decarbonization\n"
        "- Supply Chain\n"
        "- Digital Twin\n"
        "- Robotics\n"
        "- Industrial Automation\n"
        "- Carbon Capture\n"
        "- Smart Manufacturing\n"
        "- Green Cement\n"
        "You MUST return your output in strict JSON format with these exact keys:\n"
        "{\n"
        '  "keywords": ["<keyword1>", "<keyword2>", "<keyword3>"]\n'
        "}\n"
    )

    user_prompt = (
        f"Article Title: {title}\n"
        f"Article Description: {description}\n"
        f"Article Content: {content[:3000]}\n"
    )

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
        
        # Validate exact 3 keywords constraint and clean them
        cleaned_kws = [str(k).strip() for k in keywords if k]
        if len(cleaned_kws) != 3:
            # Adjust/truncate/pad to exactly 3 if needed
            if len(cleaned_kws) > 3:
                cleaned_kws = cleaned_kws[:3]
            elif len(cleaned_kws) < 3:
                while len(cleaned_kws) < 3:
                    cleaned_kws.append("Manufacturing")
        
        save_cached_keywords_for_article(url, cleaned_kws)
        return cleaned_kws
    except Exception as e:
        logger.error(f"Gemini keyword generation failed: {e}. Returning fallback keywords (not saved to cache).")
        return ["Manufacturing", "Industrial Technology", "General"]
