import logging
import json
import re
from typing import Tuple, Dict, Any, List
from urllib.parse import urlparse
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

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
    title: str, description: str, url: str, content: str, keyword: str
) -> Tuple[bool, float, str]:
    """
    Calculates industry relevance score. Rejects non-relevant articles.
    Tries Gemini Flash first, falls back to Ollama, then rule-based heuristics.
    """
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
            return False, 0.0, f"Contains blacklisted topic keyword: {blacklist_kw}"

    # 1. Primary: Gemini 1.5 Flash
    if settings.GEMINI_API_KEY:
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={settings.GEMINI_API_KEY}"
        
        system_prompt = (
            "You are an expert industry and manufacturing news analyst. "
            "Evaluate if the provided article is genuinely relevant to the selected topic.\n"
            "You MUST return your output in JSON format with these exact keys:\n"
            "{\n"
            '  "is_relevant": <bool>,\n'
            '  "relevance_score": <int, 0 to 100>,\n'
            '  "primary_topic": "<string describing primary topic>",\n'
            '  "reason": "<brief justification>"\n'
            "}\n"
        )
        
        user_prompt = (
            f"Topic/Industry: {topic}\n"
            f"Article Title: {title}\n"
            f"Article Description: {description}\n"
            f"Article URL: {url}\n"
            f"Scraped Paragraphs: {content[:1500]}\n\n"
            "Strict Evaluation Guidelines:\n"
            "1. Reject (is_relevant=false, score < 60) if the primary subject of the article is NOT the selected Topic/Industry.\n"
            "2. Reject if the Topic/Industry is only mentioned in passing (e.g. a general tech article that mentions manufacturing in one sentence). The selected industry must be the core subject.\n"
            "3. Reject blacklisted domains/categories: entertainment, video games (e.g. Spider-Man PS5), movies, celebrity news, sports, music, software package/library releases, generic programming tools/libraries (e.g., PyPI/NPM updates), and general AI news (e.g. new GPT model release, ChatGPT tips, LLM prompts) UNLESS that AI news is directly and specifically about industrial automation, smart factories, robotics, manufacturing lines, cement kilns, production, or supply chain logistics.\n"
            "4. Reject generic macro-finance, general jobs reports, or stock market updates unless they are heavily focused on manufacturing/production statistics.\n"
            "5. If relevant, set is_relevant=true and score >= 60. Give higher scores (80-100) to articles where the selected industry is the direct focal point."
        )

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"System Prompt:\n{system_prompt}\n\nUser Input:\n{user_prompt}"}]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(gemini_url, json=payload)
                if response.status_code == 200:
                    res_data = response.json()
                    res_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    parsed = json.loads(res_text)
                    is_relevant = bool(parsed.get("is_relevant", False))
                    score = float(parsed.get("relevance_score", 0))
                    reason = str(parsed.get("reason", "No reason provided"))
                    
                    logger.info(f"Gemini Relevance for '{title}': Relevant={is_relevant}, Score={score}, Reason={reason}")
                    return is_relevant, score, reason
                else:
                    logger.warning(f"Gemini API returned status {response.status_code} during relevance validation. Trying Ollama fallback.")
        except Exception as e:
            logger.warning(f"Gemini Relevance API call failed: {str(e)}. Trying Ollama fallback.")

    # 2. Secondary: Ollama Fallback
    try:
        ollama_payload = {
            "model": settings.OLLAMA_MODEL,
            "prompt": (
                f"Identify if the following article is relevant to the industry '{topic}'. "
                f"Title: {title}. Description: {description}. URL: {url}. Content: {content[:1000]}.\n"
                f"Do not include explanation. Return ONLY a JSON object: "
                f"{{\"is_relevant\": true/false, \"relevance_score\": 0-100, \"reason\": \"string\"}} "
                f"Make sure to reject entertainment, sports, software libraries, and general AI announcements."
            ),
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1}
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(f"{settings.OLLAMA_URL}/api/generate", json=ollama_payload)
            if response.status_code == 200:
                data = response.json()
                raw_response = data.get("response", "").strip()
                parsed = json.loads(raw_response)
                is_relevant = bool(parsed.get("is_relevant", False))
                score = float(parsed.get("relevance_score", 0))
                reason = str(parsed.get("reason", "Ollama fallback"))
                
                logger.info(f"Ollama Relevance for '{title}': Relevant={is_relevant}, Score={score}, Reason={reason}")
                return is_relevant, score, reason
    except Exception as e:
        logger.warning(f"Ollama Relevance check failed: {str(e)}. Using rule-based fallback.")

    # 3. Last Resort: Rule-Based Fallback (Keyword Matching)
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
    return is_relevant, score, reason


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
