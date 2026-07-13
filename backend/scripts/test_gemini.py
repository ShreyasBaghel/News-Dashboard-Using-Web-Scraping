import sys
import os
import asyncio
import logging
import time

# Ensure project root is in the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.services.gemini_client import GeminiClient, validate_gemini_config
from app.services.keyword_service import generate_article_keywords
from app.services.phrase_builder import expand_keyword

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_gemini")

async def main():
    logger.info("=========================================")
    logger.info("   GEMINI API DIAGNOSTICS UTILITY")
    logger.info("=========================================")
    
    # 1. Check API key and configuration
    logger.info(f"Loaded config GEMINI_API_KEY: {'[SET]' if settings.GEMINI_API_KEY else '[NOT SET]'}")
    logger.info(f"Loaded config GEMINI_MODEL: {settings.GEMINI_MODEL}")
    
    if not settings.GEMINI_API_KEY:
        logger.error("Error: GEMINI_API_KEY is missing from environment. Diagnostics cannot proceed.")
        sys.exit(1)
        
    # 2. Test Model Validation Endpoint
    logger.info("\n--- Step 1: Validating Model Config via startup method ---")
    start_time = time.time()
    valid = await validate_gemini_config()
    latency = time.time() - start_time
    logger.info(f"Model validation result: {valid} (Latency: {latency:.2f}s)")
    if not valid:
        logger.error("Error: Configured model validation failed. Check settings or API key details.")
        sys.exit(1)
        
    # 3. Test generateContent Keyword Generation
    logger.info("\n--- Step 2: Testing Article Keyword Generation ---")
    title = "Dalmia Cement launches next-generation low-carbon green cement"
    desc = "Dalmia Cement announced the release of its new eco-friendly cement brand to target construction decarbonization."
    content = (
        "Dalmia Cement has officially introduced its new green cement line today, which offers a 40% reduction in carbon dioxide "
        "emissions compared to standard OPC cement. The product utilizes advanced alternative binders and clinker-substitute "
        "materials, backed by state-of-the-art carbon capture pilot installations at its primary production kiln."
    )
    url = "https://example.com/dalmia-green-cement-release"
    
    # We want to clear cache entry first so we definitely trigger Gemini
    try:
        from app.services.cache import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM article_keywords WHERE url = ?", (url,))
        conn.commit()
        conn.close()
        logger.info("Cleaned previous test cache entries.")
    except Exception as cache_err:
        logger.warning(f"Could not clean test cache: {cache_err}")

    start_time = time.time()
    keywords = await generate_article_keywords(title, desc, content, url)
    latency = time.time() - start_time
    
    logger.info(f"Generated Keywords: {keywords}")
    logger.info(f"Keyword generation latency: {latency:.2f}s")
    
    assert len(keywords) == 3, f"Expected exactly 3 keywords, got {len(keywords)}"
    assert keywords != ["Manufacturing", "Industrial Technology", "General"], "Error: Service returned fallback keywords instead of generating semantic ones."
    
    # 4. Check cache storage
    from app.services.cache import get_cached_keywords_for_article
    cached = get_cached_keywords_for_article(url)
    logger.info(f"Keywords successfully cached: {cached}")
    assert cached == keywords, f"Expected cached keywords to match generated, got {cached}"
    
    # 5. Test phrase expansion
    logger.info("\n--- Step 3: Testing Phrase Expansion ---")
    keyword_to_expand = "Green Cement"
    
    start_time = time.time()
    phrases = await expand_keyword(keyword_to_expand)
    latency = time.time() - start_time
    
    logger.info(f"Expanded Phrases for '{keyword_to_expand}': {phrases}")
    logger.info(f"Phrase expansion latency: {latency:.2f}s")
    
    assert len(phrases) >= 3, f"Expected 3 to 4 expanded phrases, got {len(phrases)}"
    assert phrases != [keyword_to_expand], "Error: Phrase builder returned fallback (un-expanded) keyword list."
    
    # 6. Test phrase expansion caching
    logger.info("\n--- Step 4: Testing Phrase Expansion Caching (should be instant) ---")
    start_time = time.time()
    phrases_cached = await expand_keyword(keyword_to_expand)
    cached_latency = time.time() - start_time
    logger.info(f"Cached Expanded Phrases: {phrases_cached}")
    logger.info(f"Cached call latency: {cached_latency:.4f}s")
    
    assert phrases_cached == phrases, "Expected cached phrases to match original phrases."
    assert cached_latency < 0.05, f"Expected cached latency to be sub-50ms, got {cached_latency:.4f}s"
    
    logger.info("\n=========================================")
    logger.info("   ALL GEMINI DIAGNOSTIC TESTS PASSED!")
    logger.info("=========================================")

if __name__ == "__main__":
    asyncio.run(main())
