import sys
import os
import asyncio
import logging

# Ensure project root is in the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.cache import (
    init_db,
    get_cached_keywords_for_article,
    save_cached_keywords_for_article,
    get_all_aggregated_keywords
)
from app.services.keyword_service import generate_article_keywords
from app.services.validator import validate_relevance
from app.pipeline import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_keywords")

async def test_keyword_caching():
    logger.info("--- Testing Keyword Caching ---")
    url = "https://example.com/test-keywords-url"
    keywords = ["cement", "decarbonization", "sustainability"]
    
    # Save keywords
    save_cached_keywords_for_article(url, keywords)
    
    # Retrieve and check
    retrieved = get_cached_keywords_for_article(url)
    logger.info(f"Retrieved keywords: {retrieved}")
    assert retrieved == keywords, f"Expected {keywords}, got {retrieved}"
    
    # Check all aggregated
    all_kws = get_all_aggregated_keywords()
    logger.info(f"All aggregated keywords: {all_kws}")
    for kw in keywords:
        assert kw in all_kws, f"Expected {kw} to be in aggregated keywords"
        
    logger.info("Keyword caching tests passed!\n")

async def test_keyword_generation_service():
    logger.info("--- Testing Keyword Generation Service ---")
    mock_url = "https://www.industrynews-mock.com/fallback-123-1"
    
    # Check mock fallback keywords
    mock_kws = await generate_article_keywords(
        title="Test Mock Headline",
        description="Test Mock Description",
        content="Test Mock Content",
        url=mock_url
    )
    logger.info(f"Mock URL keywords: {mock_kws}")
    assert len(mock_kws) == 3, f"Expected exactly 3 keywords, got {len(mock_kws)}"
    assert "Manufacturing" in mock_kws, "Expected 'Manufacturing' in fallback keywords"
    
    # Check cache behavior
    url = "https://example.com/test-service-caching"
    test_kws = ["AI", "Robotics", "Predictive Maintenance"]
    save_cached_keywords_for_article(url, test_kws)
    
    service_kws = await generate_article_keywords(
        title="Ignore this title",
        description="Ignore this description",
        content="Ignore this content",
        url=url
    )
    logger.info(f"Service returned cached keywords: {service_kws}")
    assert service_kws == test_kws, "Expected keywords to be fetched from cache without calling LLM"
    
    logger.info("Keyword generation service tests passed!\n")

async def test_relevance_validation_phi3():
    logger.info("--- Testing Relevance Validation ---")
    # We want to check that validate_relevance still works and uses Ollama.
    # Note: If Ollama is not running locally, it should fall back to rule-based or return correctly.
    title = "Dalmia Cement introduces new green concrete formulation"
    desc = "Dalmia Cement has developed a green concrete to support infrastructure decarbonization."
    content = "Dalmia Cement is leading the construction sector in sustainability by introducing green concrete formulations..."
    
    ok, score, reason = await validate_relevance(title, desc, "https://example.com/green-cement", content, "Cement Industry")
    logger.info(f"Validation result: Relevant={ok}, Score={score}, Reason={reason}")
    # It should pass relevance because it is highly relevant to Cement Industry.
    # (Whether it's Ollama or rule-based fallback, it should return a valid Tuple)
    assert isinstance(ok, bool)
    assert isinstance(score, float)
    assert isinstance(reason, str)
    
    logger.info("Relevance validation tests passed!\n")

async def test_pipeline_integration():
    logger.info("--- Testing End-to-End Pipeline Integration ---")
    
    # Run the pipeline for a default query
    payload = await run_pipeline(keyword="AI", force_refresh=True)
    
    # Check that returned payload matches model and contains keywords field
    assert "keyword_counts" in payload, "Expected keyword_counts in payload"
    assert "articles" in payload, "Expected articles in payload"
    
    articles = payload["articles"]
    if articles:
        first_art = articles[0]
        logger.info(f"First article in feed: {first_art['title']}")
        logger.info(f"First article keywords: {first_art.get('keywords')}")
        assert "keywords" in first_art, "Expected article object to have 'keywords' field"
        assert isinstance(first_art["keywords"], list), "Expected keywords to be a list"
        
    logger.info(f"Aggregated keyword counts: {payload['keyword_counts']}")
    
    logger.info("Pipeline integration tests passed!\n")

async def main():
    logger.info("Initializing database...")
    init_db()
    
    await test_keyword_caching()
    await test_keyword_generation_service()
    await test_relevance_validation_phi3()
    await test_pipeline_integration()
    
    logger.info("All tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
