import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

def getNormalizedDomain(url: str) -> str:
    """
    Extracts and normalizes the registrable domain from a URL.
    Treats www.example.com and example.com as the same;
    strips subdomains like news.example.com down to the registrable domain (example.com).
    Also handles common double-suffixes (e.g., .co.uk, .org.uk, .com.au).
    """
    if not url:
        return ""
    
    # Extract host part
    host = url.lower()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0]
    host = host.split(":", 1)[0]
    host = host.strip()
    
    # Remove leading www.
    if host.startswith("www."):
        host = host[4:]
        
    # Split by dot
    parts = host.split(".")
    if len(parts) <= 2:
        return host
        
    # Check for multi-part TLDs (double-suffixes)
    double_suffix_mid = {"co", "com", "org", "net", "gov", "edu", "ac", "res", "mil"}
    if len(parts) >= 3:
        # If the second-to-last part is a helper suffix, and the TLD is a short ccTLD (usually 2 chars)
        if parts[-2] in double_suffix_mid and len(parts[-1]) == 2:
            return ".".join(parts[-3:])
            
    return ".".join(parts[-2:])

# =====================================================================
# Source Diversity Selection Rule
# =====================================================================
# 1. The 5 dynamic-slot articles must each come from a distinct source domain.
#    No two dynamic articles may share the same publisher/registrable domain.
# 2. Prefer domains not already used by the 5 hardcoded/pinned articles.
#    If enough distinct-domain candidates exist, avoid reuse of any domain
#    occupied by pinned articles.
# 3. If there aren't enough distinct domains among candidates, reuse domains
#    from the pinned/hardcoded set rather than leaving slots empty.
# 4. Never allow two dynamic slots to share a domain with each other. If the
#    number of unique-domain candidates is completely exhausted and still
#    fewer than 5 slots are filled, backfill with repeating domains but
#    log a warning indicating that source diversity could not be fully satisfied.
# =====================================================================

def selectDiverseArticles(
    candidates: List[Dict[str, Any]], 
    count: int = 5, 
    excludeDomains: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Selects a set of articles enforcing source domain diversity.
    
    :param candidates: List of candidate article dictionaries.
    :param count: Target number of articles to select.
    :param excludeDomains: Optional list/set of domains to deprioritize (e.g. pinned domains).
    :return: A list of selected article dictionaries (length <= count).
    """
    if not candidates:
        return []
        
    if excludeDomains is None:
        excludeDomains = []
        
    exclude_set = {d.lower().strip() for d in excludeDomains if d}
    
    # 1. Group articles by normalized domain
    domain_to_articles = {}
    domain_first_index = {}
    
    for idx, art in enumerate(candidates):
        url = art.get("url", "")
        if not url:
            continue
        domain = getNormalizedDomain(url)
        if not domain:
            continue
        if domain not in domain_to_articles:
            domain_to_articles[domain] = []
            domain_first_index[domain] = idx
        domain_to_articles[domain].append(art)
        
    # Unique domains sorted by the appearance of their first article to preserve relative ranking/order
    sorted_domains = sorted(domain_to_articles.keys(), key=lambda d: domain_first_index[d])
    
    preferred_domains = [d for d in sorted_domains if d not in exclude_set]
    avoid_domains = [d for d in sorted_domains if d in exclude_set]
    
    selected_articles = []
    used_domains = set()
    used_urls = set()
    
    # Helper to check if article already selected (by URL)
    def add_selected(art, domain):
        selected_articles.append(art)
        used_domains.add(domain)
        used_urls.add(art["url"])
        
    # Phase 1: Pick 1 article from each preferred domain
    for domain in preferred_domains:
        if len(selected_articles) >= count:
            break
        # Grab first available article for this domain (best candidate)
        for art in domain_to_articles[domain]:
            if art["url"] not in used_urls:
                add_selected(art, domain)
                break
                
    # Phase 2: If we still need more, pick 1 article from each avoid domain (pinned domains)
    for domain in avoid_domains:
        if len(selected_articles) >= count:
            break
        for art in domain_to_articles[domain]:
            if art["url"] not in used_urls:
                add_selected(art, domain)
                break
                
    # Phase 3: Fallback/Exhausted unique domains.
    # If we still have fewer than count articles, we must reuse domains to avoid leaving slots empty.
    # We select remaining unused articles in their original order.
    if len(selected_articles) < count:
        logger.warning(
            f"Source diversity could not be fully satisfied. "
            f"Only {len(used_domains)} unique domains found for {count} slots. "
            f"Filling remaining slots with repeating domains."
        )
        for art in candidates:
            if len(selected_articles) >= count:
                break
            if art.get("url") and art["url"] not in used_urls:
                # We can't avoid domain reuse here
                domain = getNormalizedDomain(art["url"])
                add_selected(art, domain)
                
    return selected_articles
