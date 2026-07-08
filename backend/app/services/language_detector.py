import logging
from langdetect import detect, LangDetectException

logger = logging.getLogger(__name__)

def is_english(title: str, description: str = "", content: str = "") -> bool:
    """
    Detect if the article content is in English.
    Combines title, description, and scraped content (if available) for detection.
    """
    parts = []
    if title:
        parts.append(title)
    if description:
        parts.append(description)
    if content:
        parts.append(content)
        
    sample_text = " ".join(parts).strip()
    if not sample_text:
        logger.warning("Empty text provided for language detection.")
        return False
        
    try:
        lang = detect(sample_text)
        is_eng = (lang == 'en')
        if not is_eng:
            logger.info(f"Language detection: Skipping non-English article '{title}' (detected: '{lang}')")
        return is_eng
    except LangDetectException as e:
        logger.warning(f"Language detection failed for article '{title}': {str(e)}")
        # If it's pure numbers/punctuation, it's not a valid article.
        return False
