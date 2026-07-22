import sys
content = open('app/pipeline.py', 'r', encoding='utf-8').read()

# Phase 4 Imports
content = content.replace(
    'save_seen_articles_to_disk, get_seen_url_cache_stats, deduplicate_articles',
    'save_seen_articles_to_disk, get_seen_url_cache_stats, deduplicate_articles,\n    normalize_url, normalize_title, get_hash, is_hash_seen, mark_hash_seen'
)

# Phase 4 Deduplication logic
dedup_logic = '''        if not relevance_ok:
            logger.info(f"Skipping candidate '{title}' because of relevance check ({relevance_kw}): {reason}")
            stats["failed_relevance_validation"] += 1
            return None
            
        # Deduplication (Phase 4)
        norm_url_hash = get_hash(normalize_url(url))
        norm_title_hash = get_hash(normalize_title(title))
        
        if is_hash_seen(norm_url_hash, "url"):
            logger.info(f"Duplicate skipped\\nReason: URL hash\\nSource: {art.get('source', 'Unknown')}")
            stats["duplicate_urls"] += 1
            return None
            
        if is_hash_seen(norm_title_hash, "title"):
            logger.info(f"Duplicate skipped\\nReason: Title hash\\nSource: {art.get('source', 'Unknown')}")
            stats["duplicate_urls"] += 1
            return None
            
        mark_hash_seen(norm_url_hash, "url")
        mark_hash_seen(norm_title_hash, "title")
'''
content = content.replace(
    '        if not relevance_ok:\n            logger.info(f"Skipping candidate \'{title}\' because of relevance check ({relevance_kw}): {reason}")\n            stats["failed_relevance_validation"] += 1\n            return None',
    dedup_logic
)

# Phase 4 Remove late dedup
content = content.replace(
    '    summarized_articles = deduplicate_articles(summarized_articles)\n    summarized_pinned = deduplicate_articles(summarized_pinned)',
    '    # Removed in Phase 4'
)

# Phase 1 & 2 integration at the end
end_logic_old = '''    payload = {
        "keyword": keyword or "Default Dashboard",
        "articles": summarized_articles,
        "pinned_articles": summarized_pinned,
        "last_updated": last_updated_dt.isoformat().replace("+00:00", "Z"),
        "next_update": next_update_dt.isoformat().replace("+00:00", "Z"),
        "keyword_counts": keyword_counts
    }
    
    # 8. Save in database cache
    save_cached_results(db_keyword, payload)'''

end_logic_new = '''    from app.services.dataset_manager import StagingDataset
    staging = StagingDataset(keyword=keyword or "Default Dashboard")
    staging.set_content(summarized_articles, summarized_pinned, keyword_counts)
    payload = staging.commit()
    '''
content = content.replace(end_logic_old, end_logic_new)

# Tag Validation Phase 2 logic replacement
tag_old = '''        keywords = await generate_article_keywords(
            title=title,
            description=art.get("description", "") or summary,
            content=content,
            url=url
        )
        art["keywords"] = keywords'''

tag_new = '''        from app.services.validator import validate_and_clean_tags
        raw_keywords = await generate_article_keywords(
            title=title,
            description=art.get("description", "") or summary,
            content=content,
            url=url
        )
        art["keywords"] = validate_and_clean_tags(
            raw_tags=raw_keywords,
            title=title,
            summary=summary,
            content=content,
            entity_list=art.get("entities", []),
            taxonomy=art.get("taxonomy", [])
        )'''
content = content.replace(tag_old, tag_new)

with open('app/pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Applied Phase 1, 2, and 4 to pipeline.py')
