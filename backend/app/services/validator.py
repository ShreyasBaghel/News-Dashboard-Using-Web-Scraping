import logging
import json
import re
from typing import Tuple, Dict, Any, List, Optional
from urllib.parse import urlparse
import httpx
from app.config import settings
from app.services.cache import TTLLRUCache

logger = logging.getLogger(__name__)

# Bounded relevance cache with (url, title, keyword) key
_relevance_cache = TTLLRUCache(maxsize=500, ttl_seconds=1800)

# URL Blacklist configurations
BLACKLIST_DOMAINS = {
    "github.com", "pypi.org", "pypi.python.org", "npmjs.com", "npmjs.org",
    "crates.io", "packagist.org", "maven.org", "docker.com", "hub.docker.com",
    "stackoverflow.com", "stackexchange.com", "reddit.com", "quora.com",
    "medium.com", "docs.google.com", "wikipedia.org", "w3schools.com"
}

BLACKLIST_SUBDOMAINS = {
    "docs", "api", "wiki", "help", "support", "developer", "developers",
    "learn", "gitbook", "readthedocs", "changelog", "status", "download"
}

BLACKLIST_PATH_KEYWORDS = [
    "/releases/", "/releases", "/tags/", "/commit/", "/tree/", "/blob/",
    "/pull/", "/issue/", "/issues/", "/pulls/", "/doc/", "/docs/", "/api/",
    "api-docs", "/changelog", "/wiki/", "/download/", "/login", "/signin",
    "/signup", "/logout", "/archive", "/search", "/feed", "/rss", "/xml",
    "/packages/", "/project/", "/projects/", "/documentation/", "/tutorial/",
    "/tutorials/", "/spec/", "/specs/", "/specification/", "/specifications/"
]

BLACKLIST_TOPICS = [
    "entertainment", "gaming", "sports", "celebrity", "movies", "music",
    "pop culture", "playstation", "xbox", "nintendo", "ps5", "fortnite",
    "nfl", "nba", "mlb", "cricket", "olympics", "movie", "album", "song",
    "concert", "theater", "hollywood", "actor", "actress", "pypi", "npm",
    "release notes", "changelog", "stock market", "nasdaq", "dow jones",
    "s&p 500", "trading", "crypto", "bitcoin", "ethereum", "dogecoin",
    "jobs report", "unemployment rate", "dependency injection", "pypi package",
    "pypi release", "npm package", "programming library", "software release"
]

def is_valid_url(url: str) -> Tuple[bool, str]:
    """
    Checks if a URL is likely to be a news/article page.
    Rejects documentation, code repositories, package indexes, logins, etc.
    """
    if not url:
        return False, "Empty URL"

    try:
        parsed = urlparse(url.lower())
        host = parsed.netloc
        path = parsed.path
        
        # Check domain blacklist
        if host in BLACKLIST_DOMAINS or any(host.endswith("." + d) for d in BLACKLIST_DOMAINS):
            # Exception for GitHub Blog
            if host != "github.blog" and "github.blog" not in host:
                return False, f"Blacklisted domain: {host}"
                
        # Check subdomain blacklist
        parts = host.split(".")
        if len(parts) > 2:
            subdomain = parts[0]
            if subdomain in BLACKLIST_SUBDOMAINS:
                return False, f"Blacklisted subdomain: {subdomain}"
                
        # Check path keyword blacklist
        for kw in BLACKLIST_PATH_KEYWORDS:
            if kw in path:
                return False, f"Blacklisted path pattern: {kw}"
                
        # Check file extensions
        if path.endswith((".xml", ".rss", ".json", ".zip", ".tar.gz", ".pdf", ".txt", ".exe", ".msi")):
            return False, f"Blacklisted file extension in path"
            
        return True, "URL passes filters"
    except Exception as e:
        return False, f"URL parse error: {str(e)}"


def is_valid_source_type(url: str, title: str, content: str) -> Tuple[bool, str]:
    """
    Determines if the page is a real news/article page versus documentation, changelog,
    landing page, code repository, etc.
    """
    url_ok, reason = is_valid_url(url)
    if not url_ok:
        return False, reason
        
    title_lower = title.lower()
    
    # Title checklist
    doc_title_keywords = [
        "api reference", "documentation", "changelog", "release notes",
        "tutorial", "how to", "getting started", "installation", "404",
        "not found", "login", "sign in", "sign up", "forgot password",
        "terms of service", "privacy policy", "pricing", "features"
    ]
    for kw in doc_title_keywords:
        if kw in title_lower:
            return False, f"Title suggests non-article content type ({kw})"
            
    # Content body checks
    content_lower = content.lower()
    
    # Code repositories or programming documentation signatures
    code_signatures = [
        "pip install", "npm install", "yarn add", "composer require", "git clone",
        "docker pull", "import ", "const ", "require(", "from ... import",
        "public class ", "def ", "function()", "npm i ", "gem install"
    ]
    code_count = sum(1 for sig in code_signatures if sig in content_lower)
    if code_count >= 3:
        return False, "High density of programming code snippets detected"
        
    # Generic landing page signatures
    landing_signatures = [
        "pricing plan", "monthly plan", "yearly plan", "free trial",
        "add to cart", "buy now", "check out", "product specs",
        "all rights reserved", "terms and conditions", "contact support"
    ]
    landing_count = sum(1 for sig in landing_signatures if sig in content_lower)
    if landing_count >= 4:
        return False, "Page signature resembles product landing page"
        
    return True, "Valid source type"


def validate_content_quality(content: str) -> Tuple[bool, str]:
    """
    Verifies that the article body contains enough meaningful content
    and is not boilerplate text or error pages.
    """
    if not content:
        return False, "Empty content body"
        
    words = content.strip().split()
    if len(words) < 60:
        return False, f"Content too short ({len(words)} words, min 60 required)"
        
    # Check paragraphs (split by double newlines or single newlines with spaces)
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n|\n{2,}', content) if len(p.strip()) > 30]
    if len(paragraphs) < 2:
        # Fallback split check by single newlines
        paragraphs = [p.strip() for p in content.split("\n") if len(p.strip()) > 30]
        if len(paragraphs) < 2:
            # If word count is large and there are multiple sentences, accept it as valid
            sentences = [s.strip() for s in re.split(r'[.!?]+', content) if len(s.strip()) > 10]
            if len(words) >= 80 and len(sentences) >= 3:
                # Satisfies paragraph constraint virtually
                pass
            else:
                return False, f"Too few paragraphs ({len(paragraphs)}, min 2 required) and too short/few sentences"
            
    # Boilerplate detection
    content_lower = content.lower()
    boilerplate_phrases = [
        "enable cookies", "please verify you are a human", "access denied",
        "cloudflare", "javascript is required", "enable javascript",
        "browser is not supported", "404 not found", "page not found",
        "login to your account", "invalid request", "forbidden error",
        "unauthorized access", "checking your browser"
    ]
    for phrase in boilerplate_phrases:
        if phrase in content_lower:
            return False, f"Boilerplate/Error signature detected: {phrase}"
            
    return True, "Valid content quality"


async def validate_relevance(
    title: str, description: str, url: str, content: str, keyword: str, client: Optional[httpx.AsyncClient] = None
) -> Tuple[bool, float, str]:
    """
    Calculates industry relevance score. Rejects non-relevant articles.
    Uses Phi-3 Mini (Ollama) as the primary and only semantic validator,
    falling back to rule-based heuristics on error.
    """
    cache_key = (url, title, keyword)
    cached_res = _relevance_cache.get(cache_key)
    if cached_res is not None:
        return cached_res

    # Clean input keyword/topic
    topic = keyword.strip() if keyword else "General Manufacturing & Industry"
    
    # Pre-filter: Check title and description against obvious blacklisted categories before API calls
    text_to_check = f"{title} {description} {url}".lower()
    for blacklist_kw in BLACKLIST_TOPICS:
        # Avoid false positives like "unemployment rate" vs "factory jobs"
        if re.search(r'\b' + re.escape(blacklist_kw) + r'\b', text_to_check):
            # Special exceptions (e.g. if the blacklist word is "ai" or "finance" which have conditional rules)
            # But the BLACKLIST_TOPICS list has specific bad terms
            logger.info(f"Pre-filter relevance: Rejected '{title}' due to blacklisted topic: '{blacklist_kw}'")
            res = (False, 0.0, f"Contains blacklisted topic keyword: {blacklist_kw}")
            _relevance_cache.set(cache_key, res)
            return res

    # 1. Primary: Ollama Semantic Validation
    try:
        ollama_payload = {
            "model": settings.OLLAMA_MODEL,
            "prompt": (
                f"You are an expert industry and manufacturing news analyst. "
                f"Evaluate if the provided article is genuinely relevant to the selected topic.\n"
                f"Topic/Industry: {topic}\n"
                f"Article Title: {title}\n"
                f"Article Description: {description}\n"
                f"Article URL: {url}\n"
                f"Scraped Paragraphs: {content[:1000]}\n\n"
                f"Strict Evaluation Guidelines:\n"
                f"1. Reject (is_relevant=false, score < 60) if the primary subject of the article is NOT the selected Topic/Industry.\n"
                f"2. Reject if the Topic/Industry is only mentioned in passing (e.g. a general tech article that mentions manufacturing in one sentence). The selected industry must be the core subject.\n"
                f"3. Reject blacklisted domains/categories: entertainment, video games (e.g. Spider-Man PS5), movies, celebrity news, sports, music, software package/library releases, generic programming tools/libraries (e.g., PyPI/NPM updates), and general AI news (e.g. new GPT model release, ChatGPT tips, LLM prompts) UNLESS that AI news is directly and specifically about industrial automation, smart factories, robotics, manufacturing lines, cement kilns, production, or supply chain logistics.\n"
                f"4. Reject generic macro-finance, general jobs reports, or stock market updates unless they are heavily focused on manufacturing/production statistics.\n"
                f"5. If relevant, set is_relevant=true and score >= 60. Give higher scores (80-100) to articles where the selected industry is the direct focal point.\n"
                f"Return ONLY a JSON object: "
                f"{{\"is_relevant\": true/false, \"relevance_score\": 0-100, \"reason\": \"string\"}}"
            ),
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1}
        }
        timeout_cfg = httpx.Timeout(connect=3.0, read=15.0, write=3.0, pool=5.0)
        if client is not None:
            response = await client.post(f"{settings.OLLAMA_URL}/api/generate", json=ollama_payload, timeout=timeout_cfg)
        else:
            async with httpx.AsyncClient(timeout=timeout_cfg) as local_client:
                response = await local_client.post(f"{settings.OLLAMA_URL}/api/generate", json=ollama_payload)
        if response.status_code == 200:
            data = response.json()
            raw_response = data.get("response", "").strip()
            parsed = json.loads(raw_response)
            is_relevant = bool(parsed.get("is_relevant", False))
            score = float(parsed.get("relevance_score", 0))
            reason = str(parsed.get("reason", "Ollama validation"))
            
            logger.info(f"Ollama Relevance for '{title}': Relevant={is_relevant}, Score={score}, Reason={reason}")
            res = (is_relevant, score, reason)
            _relevance_cache.set(cache_key, res)
            return res
        else:
            logger.warning(f"Ollama API returned status {response.status_code} during relevance validation. Trying rule-based fallback.")
    except Exception as e:
        logger.warning(f"Ollama Relevance check failed: {str(e)}. Using rule-based fallback.")

    # 2. Secondary: Rule-Based Fallback (Keyword Matching)
    # Check if the title or description contains high-priority industry keywords
    priority_keywords = [
        "manufacturing", "cement", "factory", "automation", "robotics", "kiln",
        "industrial", "supply chain", "production", "mortar", "concrete", "decarboniz"
    ]
    
    topic_words = [w.lower() for w in topic.split() if len(w) > 3]
    all_positive_keywords = list(set(priority_keywords + topic_words))
    
    text_to_evaluate = f"{title} {description} {content[:1000]}".lower()
    
    # Calculate score based on matches
    matches = [kw for kw in all_positive_keywords if kw in text_to_evaluate]
    score = min(len(matches) * 20.0, 100.0)
    is_relevant = score >= 40.0
    
    reason = f"Rule-based match (matched keywords: {matches})"
    logger.info(f"Rule-based Relevance for '{title}': Relevant={is_relevant}, Score={score}, Reason={reason}")
    res = (is_relevant, score, reason)
    _relevance_cache.set(cache_key, res)
    return res



def validate_summary_quality(summary: str, title: str) -> bool:
    """
    Checks that the generated summary is meaningful and not empty, a placeholder,
    or a replication of failure text.
    """
    if not summary:
        return False
        
    summary_clean = summary.strip()
    if len(summary_clean) < 25:
        return False
        
    summary_lower = summary_clean.lower()
    
    # Error message checking
    if "no sufficient content" in summary_lower:
        return False
    if "unable to fetch" in summary_lower:
        return False
    if "error occurred" in summary_lower:
        return False
        
    # Placeholder boilerplate checking
    placeholders = [
        "this report covers the latest developments",
        "this article discusses",
        "in this article",
        "summarize the following",
        "here is a summary",
        "discussing industry impacts, strategic decisions"
    ]
    for p in placeholders:
        if p in summary_lower:
            return False
            
    # Simple check: summary shouldn't be identical to title
    if summary_clean.lower() == title.strip().lower():
        return False
        
    return True


# --- PHASE 2: TAG VALIDATION ENGINE ---

GENERIC_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "up", "about", "into", "over", "after", "is", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did", "can", "could",
    "should", "would", "will", "this", "that", "these", "those", "news", "report",
    "article", "update", "latest", "today", "using", "uses", "making", "new", "industry",
    "general", "stuff", "thing", "things", "various", "overview", "analysis"
}

def normalize_text_for_matching(text: str) -> str:
    """Strips non-alphanumeric characters, hyphens, spaces, and lowers casing for collision matching."""
    if not text:
        return ""
    return re.sub(r'[^a-zA-Z0-9]', '', text.lower())

def singularize_word(word: str) -> str:
    """Rule-based singularization for English plurals (e.g., Tariffs -> Tariff, Technologies -> Technology)."""
    w_lower = word.lower()
    if w_lower.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    elif w_lower.endswith("es") and len(word) > 4 and w_lower[-3:] in ("ses", "xes", "zes", "ches", "shes"):
        return word[:-2]
    elif w_lower.endswith("s") and not w_lower.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word

def normalize_tag(tag: str) -> str:
    """Normalizes whitespace and singularizes words in the tag while preserving mixed-case acronyms (e.g., OpenAI)."""
    words = [w.strip() for w in tag.strip().split() if w.strip()]
    singular_words = [singularize_word(w) for w in words]
    result_words = []
    for orig, sing in zip(words, singular_words):
        if orig.isupper() and len(orig) <= 4:
            result_words.append(orig)
        elif any(c.isupper() for c in orig[1:]):
            # Preserve mixed-case terms like OpenAI or ChatGPT
            if len(orig) > len(sing) and orig.lower().startswith(sing.lower()):
                result_words.append(orig[:len(sing)])
            else:
                result_words.append(orig)
        elif orig.islower():
            result_words.append(sing.title())
        else:
            result_words.append(sing)
    return " ".join(result_words)


def validate_and_clean_tags(
    tags: List[str],
    title: str = "",
    summary: str = "",
    content: str = "",
    entity_list: Optional[List[str]] = None,
    taxonomy: Optional[List[str]] = None
) -> List[str]:
    """
    Validation engine for article tags:
    - Maximum 2 words per tag.
    - Rejects generic words, stop words, numbers-only, punctuation, duplicates.
    - Normalizes casing, whitespace, and plurals (e.g., Tariffs -> Tariff).
    - Performs normalized presence check against title, summary, content, entity_list, or taxonomy.
    """
    if not tags:
        return []

    full_text_norm = normalize_text_for_matching(f"{title} {summary} {content[:2000]}")
    entities_norm = [normalize_text_for_matching(e) for e in (entity_list or [])]
    taxonomy_norm = [normalize_text_for_matching(t) for t in (taxonomy or [])]

    cleaned_tags: List[str] = []
    seen_normalized: set = set()

    for tag in tags:
        if not tag or not isinstance(tag, str):
            continue
        
        raw_tag = tag.strip()
        # 1. Clean punctuation except hyphens and spaces
        raw_tag = re.sub(r'[^\w\s\-]', '', raw_tag).strip()

        if not raw_tag:
            continue

        words = raw_tag.split()
        # 2. Maximum 2 words per tag
        if len(words) > 2:
            continue

        # 3. Reject numbers-only or pure generic/stopwords
        if all(w.isdigit() for w in words):
            continue
        if all(w.lower() in GENERIC_STOPWORDS for w in words):
            continue

        # 4. Normalize casing, whitespace, and plurals
        norm_tag_str = normalize_tag(raw_tag)
        tag_norm_key = normalize_text_for_matching(norm_tag_str)

        if not tag_norm_key or len(tag_norm_key) < 2:
            continue

        # 5. Deduplicate
        if tag_norm_key in seen_normalized:
            continue

        # 6. Normalized Presence Check
        is_present = False
        if not title and not summary and not content and entity_list is None and taxonomy is None:
            is_present = True
        else:
            is_present = (
                tag_norm_key in full_text_norm or
                any(tag_norm_key in ent for ent in entities_norm if ent) or
                any(tag_norm_key in tax for tax in taxonomy_norm if tax) or
                any(ent in tag_norm_key for ent in entities_norm if len(ent) > 2) or
                any(tax in tag_norm_key for tax in taxonomy_norm if len(tax) > 2)
            )

        if not is_present:
            continue

        seen_normalized.add(tag_norm_key)
        cleaned_tags.append(norm_tag_str)
        if len(cleaned_tags) >= 4:
            break

    return cleaned_tags

def score_tag_quality(tag: str, title: str = "", content: str = "") -> bool:
    """Deprecated quality scoring. Wraps validate_and_clean_tags for backward compatibility."""
    cleaned = validate_and_clean_tags([tag], title=title, content=content)
    return len(cleaned) > 0

