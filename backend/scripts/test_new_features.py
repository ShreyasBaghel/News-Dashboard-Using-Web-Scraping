import sys
import os
import asyncio
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.pinned_store import load_pinned_articles, pin_article, unpin_article, PINNED_JSON_PATH
from app.pipeline import calculate_article_score, TARGET_ARTICLE_COUNT
from pool.keyword_extractor import get_cached_keywords, load_keywords_cache

def test_pinned_store():
    print("Testing pinned store...")
    # Clean up any existing test pinned articles file
    if os.path.exists(PINNED_JSON_PATH):
        os.remove(PINNED_JSON_PATH)

    # Load empty pinned articles
    pinned = load_pinned_articles()
    assert len(pinned) == 0, f"Expected 0 pinned articles, got {len(pinned)}"

    # Pin an article
    art = {
        "title": "Test NVIDIA Blackwell",
        "url": "https://test.nvidia.com/123",
        "source": "Nvidia Press",
        "published_at": "2026-06-29T10:30:00Z",
        "summary": "Blackwell production is going well.",
        "company": "NVIDIA"
    }
    pinned = pin_article(art)
    assert len(pinned) == 1, f"Expected 1 pinned article, got {len(pinned)}"
    assert pinned[0]["is_pinned"] == True
    assert pinned[0]["title"] == "Test NVIDIA Blackwell"

    # Pin duplicate article
    pinned = pin_article(art)
    assert len(pinned) == 1, "Expected duplicate check to prevent double pinning"

    # Unpin article
    pinned = unpin_article("https://test.nvidia.com/123")
    assert len(pinned) == 0, f"Expected 0 pinned articles after unpinning, got {len(pinned)}"
    print("Pinned store tests passed!")

def test_article_scoring():
    print("Testing article scoring...")
    article = {
        "title": "Green Cement and decarbonization in Manufacturing",
        "url": "https://industry-cement.com/decarb",
        "published_at": "2026-07-08T10:00:00Z",
        "description": "An article about green cement.",
        "summary": "Decarbonizing manufacturing.",
        "scraped_content": "Green cement and concrete are key."
    }
    
    # 1. Base score (recency near now + keyword match)
    seen_domains = set()
    score = calculate_article_score(article, "cement,manufacturing", seen_domains)
    # Title has "Cement" and "Manufacturing" (adds 2.0 * 2 = 4.0)
    # Description/content has "cement" (adds 0.5)
    # Recency should be ~1.0 because date is today (2026-07-08)
    # Domain is new, so diversity bonus adds 0.3
    # Total score should be around 5.8
    print(f"Calculated Score: {score}")
    assert score > 5.0, f"Expected high score for matches and recency, got {score}"

    # 2. Score with duplicate domain (no diversity bonus)
    score_dup = calculate_article_score(article, "cement,manufacturing", seen_domains)
    print(f"Calculated Score (duplicate domain): {score_dup}")
    assert score_dup < score, f"Expected score with duplicate domain to be lower due to no diversity bonus"
    print("Article scoring tests passed!")

def test_target_count_constant():
    print("Testing article count constants...")
    assert TARGET_ARTICLE_COUNT == 50, f"Expected TARGET_ARTICLE_COUNT to be 50, got {TARGET_ARTICLE_COUNT}"
    print("Article count constants tests passed!")

if __name__ == "__main__":
    test_pinned_store()
    test_article_scoring()
    test_target_count_constant()
    print("All tests completed successfully!")
