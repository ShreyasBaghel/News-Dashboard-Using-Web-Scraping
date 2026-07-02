import logging
import os
import json
import re
from collections import Counter

logger = logging.getLogger(__name__)

# Standard English stopwords + custom news/industry stopwords
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't", "as", "at",
    "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during", "each", "few", "for",
    "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's",
    "her", "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm",
    "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's", "me", "more", "most", "mustn't",
    "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours",
    "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't",
    "so", "some", "such", "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there",
    "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "weren't",
    "what", "what's", "when", "when's", "where", "where's", "which", "while", "who", "who's", "whom", "why",
    "why's", "with", "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves",
    # Custom industry stopwords
    "says", "report", "news", "today", "also", "new", "us", "one", "two", "three", "first", "last", "year", "years",
    "company", "industry", "market", "global", "shares", "stock", "percent", "million", "billion", "more", "many",
    "would", "could", "should", "may", "might", "can", "will", "get", "make", "take", "like", "well", "much", "time",
    "some", "any", "other", "than", "then", "into", "only", "just", "how", "what", "who", "why", "where", "when"
}

_cached_keywords = []

def resolve_path(relative_path: str) -> str:
    """Resolve path relative to the backend base directory."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, relative_path)

def extract_keywords_from_pool(pool: list[dict]) -> list[str]:
    """
    Extracts and ranks single-word keywords from titles and descriptions in the pool.
    Strips punctuation, lowercases, filters stopwords, digits, and words < 3 characters.
    """
    words = []
    for art in pool:
        # Combine title and description
        text = f"{art.get('title', '')} {art.get('description', '')}"
        # Lowercase
        text = text.lower()
        # Replace non-word characters with spaces (preserves words and splits on hyphens/slashes)
        text = re.sub(r'[^\w\s]', ' ', text)
        # Tokenize by whitespace
        tokens = text.split()
        for token in tokens:
            # Filters: length >= 3, not pure numbers, not in stopwords
            if len(token) >= 3 and not token.isdigit() and token not in STOPWORDS:
                words.append(token)
                
    # Rank by frequency
    counts = Counter(words)
    # Deduplicate and return top 300
    top_keywords = [word for word, count in counts.most_common(300)]
    return top_keywords

def save_keywords_to_disk(keywords: list[str], path: str = "data/keywords_index.json") -> None:
    """Saves the keywords list to disk as a JSON array."""
    full_path = resolve_path(path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    try:
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(keywords, f, indent=4)
        logger.info(f"Successfully saved {len(keywords)} keywords to {full_path}")
    except Exception as e:
        logger.error(f"Error saving keywords to {full_path}: {e}")

def load_keywords_cache(path: str = "data/keywords_index.json") -> None:
    """Loads the keywords from disk into the in-memory cache."""
    global _cached_keywords
    full_path = resolve_path(path)
    if not os.path.exists(full_path):
        logger.warning(f"Keywords index file not found at {full_path}. Memory cache remains empty.")
        _cached_keywords = []
        return
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            _cached_keywords = json.load(f)
        logger.info(f"Loaded {len(_cached_keywords)} keywords into memory cache.")
    except Exception as e:
        logger.error(f"Error loading keywords cache from {full_path}: {e}")
        _cached_keywords = []

def get_cached_keywords() -> list[str]:
    """Returns the current in-memory cached keywords list."""
    global _cached_keywords
    return _cached_keywords
