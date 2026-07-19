import sys
import os
import json
import asyncio
import logging

# Ensure backend directory is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.dataset_manager import dataset_manager, StagingDataset
from app.services.validator import validate_and_clean_tags, normalize_text_for_matching
from app.services.cache import init_db, save_smart_cached_tags, get_smart_cached_tags

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_phase1_phase2")

def test_phase1_architecture():
    logger.info("=========================================")
    logger.info("TESTING PHASE 1: BACKEND ARCHITECTURE & PERSISTENCE")
    logger.info("=========================================")

    init_db()

    # 1. Test Startup Recovery
    logger.info("[Test 1.1] Startup Recovery...")
    dataset_manager.load_startup_snapshot()
    active = dataset_manager.get_active_dataset()
    assert isinstance(active, dict), "ACTIVE_DATASET snapshot must be a dictionary."
    assert "articles" in active, "ACTIVE_DATASET payload must contain 'articles' key."
    logger.info(f"Startup snapshot loaded successfully with {len(active.get('articles', []))} articles.")

    # 2. Test Staging Dataset & Atomic Commit
    logger.info("[Test 1.2] Staging Dataset & Atomic Commit...")
    initial_snapshot = dict(dataset_manager.get_active_dataset())

    staging = StagingDataset(keyword="Test Topic")
    sample_articles = [
        {
            "url": "https://example.com/test-article-1",
            "title": "GPT-5 Released for Industrial Robotics",
            "summary": "OpenAI introduced GPT-5 with specialized features for factory automation and smart manufacturing.",
            "source": "Tech News",
            "published_at": "2026-07-17T10:00:00Z",
            "keywords": ["GPT-5", "Robotics", "OpenAI"]
        }
    ]
    staging.set_content(sample_articles, pinned_articles=[], keyword_counts={"GPT-5": 1, "Robotics": 1})

    committed_payload = staging.commit()
    assert committed_payload["keyword"] == "Test Topic"
    assert len(committed_payload["articles"]) == 1

    new_active = dataset_manager.get_active_dataset()
    assert new_active["keyword"] == "Test Topic"
    assert len(new_active["articles"]) == 1
    assert new_active["articles"][0]["url"] == "https://example.com/test-article-1"
    logger.info("Atomic commit successfully replaced ACTIVE_DATASET reference in memory.")

    # 3. Test Rollback Handling on Failure
    logger.info("[Test 1.3] Rollback Handling...")
    failing_staging = StagingDataset(keyword="Failed Topic")

    try:
        # Simulate exception during refresh/commit
        failing_staging.set_content(None) # Invalid content type
        failing_staging.commit()
        assert False, "Commit should have raised an exception."
    except Exception as e:
        failing_staging.rollback(e)

    retained_active = dataset_manager.get_active_dataset()
    # Should retain previous valid dataset snapshot
    assert retained_active["keyword"] == "Test Topic"
    assert len(retained_active["articles"]) == 1
    logger.info("Rollback handling verified: previous ACTIVE_DATASET was preserved without partial updates.")
    logger.info("Phase 1 Architecture Tests Passed!\n")


def test_phase2_tag_validation():
    logger.info("=========================================")
    logger.info("TESTING PHASE 2: TAG GENERATION & VALIDATION ENGINE")
    logger.info("=========================================")

    title = "OpenAI Unveils GPT-5 for Industrial Automation and Robot Tariff Controls"
    summary = "The new GPT 5 reasoning model accelerates factory automation, supply chain logistics, and tariff analysis."
    content = "OpenAI announced GPT-5 featuring zero-shot industrial reasoning and automated tariff calculations for factories."

    # 1. Max 2 words & stop word filtering
    logger.info("[Test 2.1] Tag Length & Stopword Filtering...")
    raw_tags = ["OpenAI", "GPT-5", "Industrial Automation", "Very Long Generic Tag Name That Exceeds Two Words Limit", "the", "12345"]
    cleaned = validate_and_clean_tags(raw_tags, title=title, summary=summary, content=content)
    assert "OpenAI" in cleaned
    assert "Gpt-5" in cleaned or "GPT-5" in cleaned
    assert "Industrial Automation" in cleaned
    assert not any(len(t.split()) > 2 for t in cleaned), "No tag should exceed 2 words."
    assert "12345" not in cleaned, "Numbers-only tags must be rejected."
    assert "the" not in cleaned, "Stopwords must be rejected."
    logger.info(f"Cleaned tags: {cleaned}")

    # 2. Plural Normalization ("Tariffs" -> "Tariff")
    logger.info("[Test 2.2] Plural Normalization...")
    raw_plural_tags = ["Tariffs", "Robots"]
    cleaned_plurals = validate_and_clean_tags(raw_plural_tags, title=title, summary=summary, content=content)
    assert "Tariff" in cleaned_plurals, f"Expected 'Tariff' in {cleaned_plurals}"
    assert "Robot" in cleaned_plurals, f"Expected 'Robot' in {cleaned_plurals}"
    logger.info(f"Plural normalized tags: {cleaned_plurals}")

    # 3. Normalized Presence Check
    logger.info("[Test 2.3] Normalized Presence Check...")
    # "GPT 5" should match "GPT-5" in title
    tags_variant = ["GPT 5", "Open AI"]
    cleaned_variant = validate_and_clean_tags(tags_variant, title=title, summary=summary, content=content)
    assert len(cleaned_variant) >= 1
    assert any(normalize_text_for_matching(t) in ("gpt5", "openai") for t in cleaned_variant)
    logger.info(f"Normalized presence check tags: {cleaned_variant}")

    # 4. Duplicate Tag Removal
    logger.info("[Test 2.4] Duplicate Tag Removal...")
    duplicate_tags = ["GPT-5", "gpt-5", "Gpt 5", "GPT5"]
    cleaned_dups = validate_and_clean_tags(duplicate_tags, title=title, summary=summary, content=content)
    assert len(cleaned_dups) == 1, f"Expected 1 unique tag but got: {cleaned_dups}"
    logger.info(f"Deduplicated tags: {cleaned_dups}")
    logger.info("Phase 2 Tag Validation Tests Passed!\n")


def test_phase2_smart_cache():
    logger.info("=========================================")
    logger.info("TESTING PHASE 2: SMART TAG CACHE")
    logger.info("=========================================")

    url = "https://example.com/smart-cache-test"
    orig_title = "Dalmia Cement Next-Gen Kiln Efficiency"
    orig_summary = "Dalmia Cement deploys automated kiln monitoring."
    orig_tags = ["Cement", "Kiln"]

    # Save initial smart cache
    save_smart_cached_tags(url, orig_tags, title=orig_title, summary=orig_summary)

    # 1. Cache hit for unchanged article
    hit_tags = get_smart_cached_tags(url, orig_title, orig_summary)
    assert hit_tags is not None, "Cache hit expected for unchanged article."
    assert "Cement" in hit_tags
    logger.info(f"[Smart Cache Hit] Successfully retrieved cached tags: {hit_tags}")

    # 2. Cache miss for title change
    changed_title_tags = get_smart_cached_tags(url, "Changed Title For Cement", orig_summary)
    assert changed_title_tags is None, "Cache miss expected when title changes."
    logger.info("[Smart Cache Miss] Correctly invalidated cache on title change.")

    # 3. Cache miss for summary change
    changed_summary_tags = get_smart_cached_tags(url, orig_title, "Completely new summary content.")
    assert changed_summary_tags is None, "Cache miss expected when summary changes."
    logger.info("[Smart Cache Miss] Correctly invalidated cache on summary change.")

    logger.info("Phase 2 Smart Cache Tests Passed!\n")


if __name__ == "__main__":
    logger.info("STARTING PHASE 1 & PHASE 2 VERIFICATION SUITE")
    test_phase1_architecture()
    test_phase2_tag_validation()
    test_phase2_smart_cache()
    logger.info("ALL PHASE 1 & PHASE 2 TESTS PASSED SUCCESSFULLY!")
