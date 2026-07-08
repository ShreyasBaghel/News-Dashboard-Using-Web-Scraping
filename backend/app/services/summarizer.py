import httpx
import json
import logging
from typing import Optional
from app.config import settings
from app.services.cache import TTLLRUCache

logger = logging.getLogger(__name__)

# Bounded in-memory cache for summaries (max size 500, TTL 30 minutes)
_summary_cache = TTLLRUCache(maxsize=500, ttl_seconds=1800)

async def summarize_content(
    title: str, 
    content: str, 
    client: Optional[httpx.AsyncClient] = None, 
    url: Optional[str] = None
) -> str:
    """
    Summarize article content using Ollama (Phi-3 Mini by default).
    Falls back to a heuristic text-shortener if Ollama is offline or fails.
    Uses the in-memory summary cache and accepts an optional shared AsyncClient.
    """
    if not content or len(content.strip()) < 50:
        return f"No sufficient content available. Title: {title}"
        
    cache_key = url if url else content
    cached_summary = _summary_cache.get(cache_key)
    if cached_summary is not None:
        return cached_summary

    prompt = (
        f"You are a professional business analyst summarizing industry news. "
        f"Summarize the following article text in exactly two concise sentences. "
        f"Do not include personal opinions, markdown styling, or intros like 'Here is a summary'. "
        f"Article Title: {title}\n"
        f"Article Content: {content}\n\n"
        f"You MUST return the output as a valid JSON object with the format:\n"
        f"{{\"summary\": \"your two-sentence summary here\"}}"
    )
    
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.3
        }
    }
    
    ollama_endpoint = f"{settings.OLLAMA_URL}/api/generate"
    timeout_cfg = httpx.Timeout(connect=3.0, read=15.0, write=3.0, pool=5.0)
    
    summary = None
    try:
        if client is not None:
            response = await client.post(ollama_endpoint, json=payload, timeout=timeout_cfg)
        else:
            async with httpx.AsyncClient(timeout=timeout_cfg) as local_client:
                response = await local_client.post(ollama_endpoint, json=payload)
                
        if response.status_code == 200:
            data = response.json()
            raw_response = data.get("response", "").strip()
            # Parse JSON summary
            parsed = json.loads(raw_response)
            if isinstance(parsed, dict):
                summary = parsed.get("summary", "")
                if isinstance(summary, dict):
                    # Merge keys and values if LLM formatted sentences as key-value pairs
                    summary = " ".join([f"{k.strip()} {v.strip()}".strip() for k, v in summary.items() if k and v])
            else:
                summary = str(parsed)
            
            if summary:
                summary = str(summary).strip()
        else:
            logger.warning(f"Ollama returned status {response.status_code}. Using local fallback.")
    except Exception as e:
        logger.warning(f"Ollama communication failed: {str(e)}. Using local fallback summarization.")
        
    if not summary:
        summary = _get_fallback_summary(title, content)
        
    # Cache summary
    _summary_cache.set(cache_key, summary)
    return summary

def _get_fallback_summary(title: str, content: str) -> str:
    """
    Generates a fallback summary by taking the first two sentences 
    or a structured description if sentences are too short.
    """
    # Simple sentence tokenizer
    sentences = []
    current = []
    for char in content:
        current.append(char)
        if char in ['.', '!', '?'] and len(current) > 10:
            sentences.append("".join(current).strip())
            current = []
            if len(sentences) >= 2:
                break
    if current:
        sentences.append("".join(current).strip())
        
    fallback = " ".join(sentences[:2])
    if len(fallback) < 50:
        return f"This report covers the latest developments regarding '{title}', discussing industry impacts, strategic decisions, and future outlook."
    return fallback
