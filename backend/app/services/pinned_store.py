import os
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Resolve path relative to backend folder
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PINNED_JSON_PATH = os.path.join(BASE_DIR, "data", "pinned-articles.json")

def load_pinned_articles() -> List[Dict[str, Any]]:
    """Loads pinned articles from JSON store."""
    if not os.path.exists(PINNED_JSON_PATH):
        logger.info(f"Pinned articles JSON not found at {PINNED_JSON_PATH}. Returning empty list.")
        return []
    try:
        with open(PINNED_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Support both array directly, or object with 'articles' key
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "articles" in data:
                return data["articles"]
            return []
    except Exception as e:
        logger.error(f"Error loading pinned articles from {PINNED_JSON_PATH}: {e}")
        return []

def save_pinned_articles(articles: List[Dict[str, Any]]) -> None:
    """Saves pinned articles to JSON store."""
    os.makedirs(os.path.dirname(PINNED_JSON_PATH), exist_ok=True)
    try:
        # Atomic write
        tmp_path = PINNED_JSON_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(articles, f, indent=4)
        if os.path.exists(PINNED_JSON_PATH):
            os.remove(PINNED_JSON_PATH)
        os.rename(tmp_path, PINNED_JSON_PATH)
        logger.info(f"Saved {len(articles)} pinned articles to {PINNED_JSON_PATH}")
    except Exception as e:
        logger.error(f"Error saving pinned articles to {PINNED_JSON_PATH}: {e}")

def pin_article(article: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pins an article if it is not already pinned."""
    pinned = load_pinned_articles()
    url = article.get("url")
    if not url:
        return pinned
        
    # Check if already pinned
    for a in pinned:
        if a.get("url") == url:
            return pinned
            
    # Copy article and mark is_pinned = True
    new_art = dict(article)
    new_art["is_pinned"] = True
    pinned.append(new_art)
    save_pinned_articles(pinned)
    return pinned

def unpin_article(url: str) -> List[Dict[str, Any]]:
    """Unpins an article by its URL."""
    pinned = load_pinned_articles()
    updated = [a for a in pinned if a.get("url") != url]
    save_pinned_articles(updated)
    return updated
