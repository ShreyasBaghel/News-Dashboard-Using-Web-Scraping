import sys
import os
import asyncio
import logging

# Ensure project root is in the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.validator import (
    is_valid_url,
    is_valid_source_type,
    validate_content_quality,
    validate_relevance,
    validate_summary_quality
)
from app.services.scraper import scrape_article

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_validation")

async def test_url_validation():
    logger.info("--- Testing URL Validation ---")
    
    bad_urls = [
        "https://github.com/django/django/releases",
        "https://pypi.org/project/fastapi/",
        "https://npmjs.com/package/react",
        "https://docs.microsoft.com/en-us/api/",
        "https://example.com/login",
        "https://example.com/feed.rss",
        "https://example.com/docs/api-reference",
        "https://example.com/changelog"
    ]
    
    good_urls = [
        "https://www.reuters.com/business/cop-cement-decarbonization-2026-06-29/",
        "https://www.bloomberg.com/news/articles/2026-06-28/manufacturers-embrace-robotics",
        "https://github.blog/2026-06-25-ai-coding-trends/"
    ]
    
    for url in bad_urls:
        ok, reason = is_valid_url(url)
        logger.info(f"Bad URL: {url} -> Pass: {ok} (Reason: {reason})")
        assert not ok, f"Expected {url} to fail validation"
        
    for url in good_urls:
        ok, reason = is_valid_url(url)
        logger.info(f"Good URL: {url} -> Pass: {ok} (Reason: {reason})")
        assert ok, f"Expected {url} to pass validation but got: {reason}"
        
    logger.info("URL validation tests passed!\n")


async def test_source_type_validation():
    logger.info("--- Testing Source Type Validation ---")
    
    doc_content = "To install the package, run pip install example-package. Use import example; example.run() to initialize it. Public class Example { public static void main(String[] args) {} }"
    news_content = "Global manufacturing plants are adopting new robotics and edge intelligence. Factory operations managers reported that sensor integration reduced kiln energy use by fifteen percent this quarter."
    
    url = "https://example.com/article"
    
    # Test title checks
    bad_title_ok, reason = is_valid_source_type(url, "API Reference & Documentation", news_content)
    logger.info(f"API Title Check -> Pass: {bad_title_ok} (Reason: {reason})")
    assert not bad_title_ok
    
    # Test code signatures check
    code_ok, reason = is_valid_source_type(url, "New Software Release", doc_content)
    logger.info(f"Code signature check -> Pass: {code_ok} (Reason: {reason})")
    assert not code_ok
    
    # Test valid news article page
    good_ok, reason = is_valid_source_type(url, "Manufacturers Boost Efficiency with Robotics", news_content)
    logger.info(f"Valid news check -> Pass: {good_ok} (Reason: {reason})")
    assert good_ok
    
    logger.info("Source type validation tests passed!\n")


async def test_content_quality_validation():
    logger.info("--- Testing Content Quality Validation ---")
    
    short_content = "This content is way too short. It only has a few words."
    boilerplate_content = "Please enable cookies in your browser. Access Denied. Cloudflare ray ID. This page is forbidden."
    valid_content = (
        "Dalmia Cement has officially inaugurated its next-generation cement production plant "
        "designed with advanced hydrogen-powered kilns. The new facility will leverage renewable "
        "energy sources to offset manufacturing emissions and aims for carbon-neutral operations.\n\n"
        "Industry experts believe that hydrogen-based cement manufacturing represents a massive leap forward "
        "for sustainable construction. The pilot facility plans to scale its capacity over the next two years "
        "to serve major infrastructure projects in the region."
    )
    
    short_ok, reason = validate_content_quality(short_content)
    logger.info(f"Short content -> Pass: {short_ok} (Reason: {reason})")
    assert not short_ok
    
    boiler_ok, reason = validate_content_quality(boilerplate_content)
    logger.info(f"Boilerplate content -> Pass: {boiler_ok} (Reason: {reason})")
    assert not boiler_ok
    
    valid_ok, reason = validate_content_quality(valid_content)
    logger.info(f"Valid content -> Pass: {valid_ok} (Reason: {reason})")
    assert valid_ok
    
    logger.info("Content quality validation tests passed!\n")


async def test_summary_quality_validation():
    logger.info("--- Testing Summary Quality Validation ---")
    
    bad_summaries = [
        "No sufficient content available.",
        "This report covers the latest developments regarding Sustainable Cement, discussing industry impacts, strategic decisions.",
        "Short",
        "Manufacturers Boost Efficiency with Robotics"  # exact copy of title
    ]
    
    good_summary = "Dalmia Cement has launched a sustainable kiln pilot plant utilizing green hydrogen. The facility expects to dramatically lower manufacturing emissions and serve regional demand."
    
    for summary in bad_summaries:
        ok = validate_summary_quality(summary, "Manufacturers Boost Efficiency with Robotics")
        logger.info(f"Summary: '{summary}' -> Pass: {ok}")
        assert not ok
        
    ok = validate_summary_quality(good_summary, "Manufacturers Boost Efficiency with Robotics")
    logger.info(f"Summary: '{good_summary}' -> Pass: {ok}")
    assert ok
    
    logger.info("Summary quality validation tests passed!\n")


async def test_relevance_validation():
    logger.info("--- Testing Relevance Validation ---")
    
    # Note: If API key is present, this will make a call. If not, it falls back.
    title = "Dalmia Cement commissions green kiln pilot plant"
    desc = "New kiln pilot uses carbon capture to decarbonize cement manufacturing processes."
    url = "https://example.com/cement-kiln-pilot"
    content = (
        "Dalmia Cement has commissioned a carbon capture pilot facility at its manufacturing plant. "
        "The project is designed to capture up to 90% of kiln emissions. This marks a critical step "
        "in sustainable cement manufacturing."
    )
    
    ok, score, reason = await validate_relevance(title, desc, url, content, "Cement Industry")
    logger.info(f"Relevant Article -> Pass: {ok}, Score: {score}, Reason: {reason}")
    assert ok, f"Expected cement article to be relevant to Cement Industry topic"
    
    # Test blacklisted categories
    irrelevant_title = "Marvel Spider-Man PS5 Disc News"
    irrelevant_desc = "New updates on Spider-Man PS5 disc release dates and features."
    irrelevant_url = "https://gaming-mock.com/spiderman-ps5-release"
    irrelevant_content = "Insomniac Games has released new info on the Spider-Man PS5 game. Fans can preorder the disc version now."
    
    irr_ok, irr_score, irr_reason = await validate_relevance(irrelevant_title, irrelevant_desc, irrelevant_url, irrelevant_content, "Manufacturing")
    logger.info(f"Irrelevant Game Article -> Pass: {irr_ok}, Score: {irr_score}, Reason: {irr_reason}")
    assert not irr_ok, f"Expected gaming article to be rejected"
    
    logger.info("Relevance validation tests passed!\n")


async def test_scraper_mock():
    logger.info("--- Testing Scraper Mock URLs ---")
    url = "https://www.cementnews-mock.com/dalmia-carbon-capture-2026"
    title = "Dalmia Carbon Capture Pilot"
    
    content = await scrape_article(url, title)
    logger.info(f"Mock scrape returned content: '{content[:120]}...'")
    
    quality_ok, quality_reason = validate_content_quality(content)
    logger.info(f"Mock content quality check -> Pass: {quality_ok} (Reason: {quality_reason})")
    assert quality_ok
    
    logger.info("Scraper mock tests passed!\n")


async def main():
    try:
        await test_url_validation()
        await test_source_type_validation()
        await test_content_quality_validation()
        await test_summary_quality_validation()
        await test_relevance_validation()
        await test_scraper_mock()
        print("\nALL VALIDATION TESTS PASSED SUCCESSFULLY!")
    except AssertionError as e:
        logger.error(f"Assertion failed during tests: {str(e)}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error during tests: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
