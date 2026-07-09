import logging
import os
import json
import re
from collections import Counter

logger = logging.getLogger(__name__)

# Dedicated news/business stopwords (Objective 2)
STOPWORDS = {
    # Standard English stopwords
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

    # Reporting verbs and phrases
    "according", "announced", "appeared", "added", "amid", "across", "based", "better", "board", "ceo", "said", 
    "reported", "reports", "report", "reporting", "saying", "says", "told", "tells", "stated", "states", "announced", 
    "announces", "claiming", "claims", "claimed", "revealed", "reveals", "confirmed", "confirms", "declared", "declares", 
    "explained", "explains", "added", "adds", "noted", "notes", "pointed", "points", "suggested", "suggests", "showed", 
    "shows", "shown", "showing", "warned", "warns", "agreed", "agrees", "admitted", "admits", "commented", "comments",
    "highlighted", "highlights", "described", "describes", "detailed", "details", "discussed", "discusses",
    "will", "would", "could", "should", "can", "may", "might", "shall", "must",

    # Temporal words
    "today", "yesterday", "tomorrow", "week", "weeks", "month", "months", "year", "years", "day", "days", "daily", 
    "weekly", "monthly", "yearly", "now", "then", "currently", "recently", "soon", "late", "later", "latest", 
    "early", "earlier", "past", "future", "quarter", "annual", "annually", "quarterly", "fiscal", "monday", "tuesday", 
    "wednesday", "thursday", "friday", "saturday", "sunday", "january", "february", "march", "april", "may", "june", 
    "july", "august", "september", "october", "november", "december", "pm", "am", "est", "gmt", "utc",

    # Financial/business filler
    "million", "billion", "trillion", "percent", "pct", "share", "shares", "stock", "stocks", "market", "markets", 
    "company", "companies", "group", "groups", "global", "industry", "industries", "business", "businesses", "official", 
    "officials", "statement", "statements", "executive", "executives", "president", "founder", "analyst", "analysts", 
    "investor", "investors", "growth", "revenue", "profit", "profits", "loss", "losses", "deal", "deals", "funding", 
    "fund", "funds", "investment", "investments", "capital", "financial", "finance", "price", "prices", "cost", "costs", 
    "sales", "sale", "selling", "buy", "buying", "sell", "sold", "value", "valuation", "quarterly", "earning", "earnings",

    # Grammatical/boilerplate/filler/prepositions
    "including", "despite", "however", "therefore", "after", "before", "during", "while", "among", "around", "about", 
    "against", "along", "behind", "below", "beneath", "beside", "between", "beyond", "except", "inside", "outside", 
    "throughout", "toward", "towards", "underneath", "upon", "within", "without", "major", "latest", "breaking", "new", 
    "update", "updates", "released", "release", "press", "release", "statement", "via", "re", "vs", "versus", "etc", 
    "and/or", "e.g.", "i.e.", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "first", 
    "second", "third", "last", "next", "another", "other", "others", "some", "many", "few", "several", "much", "more", 
    "most", "all", "both", "either", "neither", "each", "every", "any", "somebody", "someone", "something", "anybody", 
    "anyone", "anything", "nobody", "noone", "nothing", "everything", "everyone", "everybody", "highly", "extremely", 
    "very", "quite", "rather", "somewhat", "really", "actually", "simply", "just", "only", "even", "also", "too", "well", 
    "very", "much", "far", "way", "close", "near", "next", "back", "front", "side", "top", "bottom", "end", "start", 
    "beginning", "middle", "part", "parts", "piece", "pieces", "whole", "total", "half", "double", "triple",
    "titled", "title", "headings", "heading"
}

# Obvious verbs to ignore (Objective 3)
VERBS = {
    "appeared", "added", "creating", "developing", "building", "expanding", "signed", "opened", "led", "driven", 
    "launched", "reported", "announced", "make", "makes", "making", "made", "take", "takes", "taking", "took", "taken", 
    "go", "goes", "going", "went", "gone", "come", "comes", "coming", "came", "get", "gets", "getting", "got", "gotten", 
    "include", "includes", "including", "included", "show", "shows", "showing", "showed", "see", "sees", "seeing", 
    "saw", "seen", "find", "finds", "finding", "found", "keep", "keeps", "keeping", "kept", "begin", "begins", 
    "beginning", "began", "begun", "start", "starts", "starting", "started", "run", "runs", "running", "ran", 
    "bring", "brings", "bringing", "brought", "carry", "carries", "carrying", "carried", "hold", "holds", "holding", 
    "held", "write", "writes", "writing", "wrote", "written", "read", "reads", "reading", "say", "says", "saying", 
    "said", "tell", "tells", "telling", "told", "ask", "asks", "asking", "asked", "answer", "answers", "answering", 
    "answered", "call", "calls", "calling", "called", "use", "uses", "using", "used", "work", "works", "working", 
    "worked", "play", "plays", "playing", "played", "move", "moves", "moving", "moved", "live", "lives", "living", 
    "lived", "believe", "believes", "believing", "believed", "think", "thinks", "thinking", "thought", "know", "knows", 
    "knowing", "knew", "known", "want", "wants", "wanting", "wanted", "need", "needs", "needing", "needed", "mean", 
    "means", "meaning", "meant", "feel", "feels", "feeling", "felt", "seem", "seems", "seeming", "seemed", "look", 
    "looks", "looking", "looked", "become", "becomes", "becoming", "became", "leave", "leaves", "leaving", "left", 
    "set", "sets", "setting", "put", "puts", "putting", "create", "creates", "created", "develop", "develops", 
    "developed", "build", "builds", "built", "expand", "expands", "expanded", "sign", "signs", "signing", "signed", 
    "open", "opens", "opening", "opened", "lead", "leads", "leading", "drive", "drives", "driving", "drove", "driven", 
    "launch", "launches", "launching", "launched", "report", "reports", "reporting", "reported", "announce", 
    "announces", "announcing", "announced", "win", "wins", "winning", "won", "lose", "loses", "losing", "lost", 
    "increase", "increases", "increasing", "increased", "decrease", "decreases", "decreasing", "decreased", 
    "grow", "grows", "growing", "grew", "grown", "rise", "rises", "rising", "rose", "risen", "fall", "falls", 
    "falling", "fell", "fallen", "drop", "drops", "dropping", "dropped", "raise", "raises", "raising", "raised", 
    "lower", "lowers", "lowering", "lowered", "seek", "seeks", "seeking", "sought", "find", "finds", "finding", 
    "found", "gain", "gains", "gaining", "gained", "offer", "offers", "offering", "offered", "provide", "provides", 
    "providing", "provided", "allow", "allows", "allowing", "allowed", "help", "helps", "helping", "helped", 
    "prevent", "prevents", "preventing", "prevented", "avoid", "avoids", "avoiding", "avoided", "ensure", "ensures", 
    "ensuring", "ensured", "protect", "protects", "protecting", "protected", "improve", "improves", "improving", 
    "improved", "enhance", "enhances", "enhancing", "enhanced", "reduce", "reduces", "reducing", "reduced", 
    "cut", "cuts", "cutting", "add", "adds", "adding", "added", "remove", "removes", "removing", "removed", 
    "delete", "deletes", "deleting", "deleted", "choose", "chooses", "choosing", "chose", "chosen", "select", 
    "selects", "selecting", "selected", "gather", "gathers", "gathering", "gathered", "collect", "collects", 
    "collecting", "collected", "receive", "receives", "receiving", "received", "send", "sends", "sending", "sent", 
    "deliver", "delivers", "delivering", "delivered", "publish", "publishes", "publishing", "published", 
    "share", "shares", "sharing", "shared", "post", "posts", "posting", "posted", "view", "views", "viewing", 
    "viewed", "watch", "watches", "watching", "watched", "listen", "listens", "listening", "listened", "hear", 
    "hears", "hearing", "heard", "speak", "speaks", "speaking", "spoke", "spoken", "talk", "talks", "talking", 
    "talked", "discuss", "discusses", "discussing", "discussed", "explain", "explains", "explaining", "explained", 
    "describe", "describes", "describing", "described", "introduce", "introduces", "introducing", "introduced", 
    "present", "presents", "presenting", "presented", "propose", "proposes", "proposing", "proposed", "suggest", 
    "suggests", "suggesting", "suggested", "recommend", "recommends", "recommending", "recommended", "decide", 
    "decides", "deciding", "decided", "determine", "determines", "determining", "determined", "identify", 
    "identifies", "identifying", "identified", "analyze", "analyzes", "analyzing", "analyzed", "evaluate", 
    "evaluates", "evaluating", "evaluated", "examine", "examines", "examining", "examined", "investigate", 
    "investigates", "investigating", "investigated", "study", "studies", "studying", "studied", "test", "tests", 
    "testing", "tested", "try", "tries", "trying", "tried", "attempt", "attempts", "attempting", "attempted",
    "discussing", "spending", "winning", "powering", "running", "underwriting", "investing", "bringing", "connecting",
    "rebounding", "ending", "hoping", "funding", "valuing", "pricing", "marketing", "heading", "starting", "accelerating",
    "transitioning", "entering", "joining", "extending", "testing", "matching", "suggesting"
}

# URL and Press-Wire artifacts to discard (Objective 6)
ARTIFACT_STOPWORDS = {
    "https", "http", "www", "com", "org", "net",
    "prnewswire", "globenewswire", "newswire", "networknewsaudio",
    "marketsandmarkets", "pypi", "githubusercontent", "rss", "xml", "feed"
}

# Core priority domains to boost (Objective 9)
DOMAIN_TOPICS = {
    "ai", "artificial intelligence", "ml", "machine learning",
    "automation", "industrial automation",
    "cement", "green cement", "dalmia bharat", "dalmia cement",
    "infrastructure", "construction",
    "industrial technology", "industrial innovation", "manufacturing", "manufacturing industry",
    "sustainability", "green energy", "carbon capture", "green hydrogen",
    "robotics", "robot", "robots",
    "supply chain", "semiconductor", "ev", "electric vehicle", "electric vehicles", "ev batteries", "battery", "batteries"
}

# Variant mappings (Objective 10)
VARIANT_MAPPING = {
    "ai": "Artificial Intelligence",
    "artificial intelligence": "Artificial Intelligence",
    "a.i.": "Artificial Intelligence",
    "ev": "Electric Vehicles",
    "electric vehicle": "Electric Vehicles",
    "electric vehicles": "Electric Vehicles",
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
}

_cached_keywords = []

def resolve_path(relative_path: str) -> str:
    """Resolve path relative to the backend base directory."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, relative_path)

def to_singular(word: str) -> str:
    """targeted singularizer to merge singular/plural forms without heavy NLP libraries (Objective 5)."""
    w = word.lower().strip()
    if not w:
        return ""
    # Exclude words that naturally end in s
    if w in {"business", "process", "news", "class", "glass", "robotics", "physics", "metrics", "analytics", "asbestos", "bias", "status", "focus", "gas", "series", "species", "chassis", "sports", "goods", "address"}:
        return w
    # ies -> y
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    # es -> check suffixes
    if w.endswith("es") and len(w) > 3:
        for suffix in ["shes", "ches", "sses", "xes", "zes"]:
            if w.endswith(suffix):
                return w[:-2]
        if w.endswith("s") and not w.endswith("ss"):
            return w[:-1]
        return w
    # s -> singular
    if w.endswith("s") and not w.endswith("ss") and len(w) > 2:
        return w[:-1]
    return w

def canonicalize(phrase: str) -> str:
    """Normalizes phrase internally to a canonical form (Objective 4, 5)."""
    words = []
    for w in phrase.split():
        w_cleaned = w.strip(".,;:!?()[]{}'\"-")
        if w_cleaned:
            words.append(w_cleaned.lower())
    
    if not words:
        return ""
        
    singular_words = [to_singular(w) for w in words]
    canonical_key = " ".join(singular_words)
    
    if canonical_key in VARIANT_MAPPING:
        return VARIANT_MAPPING[canonical_key].lower()
        
    return canonical_key

def get_casing_priority(s: str) -> float:
    """Determines casing priority for proper capitalization rendering (Objective 4)."""
    if not s:
        return 0.0
    words = s.split()
    score = 0.0
    for w in words:
        if w.isupper():
            score += 1.5
        elif w[0].isupper():
            score += 2.0
    return score

def is_domain_relevant(phrase: str) -> bool:
    """Checks if keyword belongs to target priority domains (Objective 9)."""
    phrase_lower = phrase.lower()
    if phrase_lower in DOMAIN_TOPICS:
        return True
    words = set(phrase_lower.split())
    domain_keywords = {
        "ai", "ml", "cement", "robot", "robotics", "automation", "manufacturing",
        "infrastructure", "construction", "sustainability", "energy", "hydrogen",
        "semiconductor", "battery", "batteries", "decarbonization", "carbon",
        "supply", "chain", "dalmia", "bharat", "adani", "amazon", "apple"
    }
    if words.intersection(domain_keywords):
        return True
    return False

def clean_phrase_boundaries(phrase: str) -> str:
    """Removes leading and trailing stopwords from extracted phrases."""
    words = phrase.split()
    while words and words[0].lower() in STOPWORDS:
        words.pop(0)
    while words and words[-1].lower() in STOPWORDS:
        words.pop()
    return " ".join(words)

def extract_capitalized_phrases(text: str) -> list[str]:
    """Extracts capitalized proper noun phrases, keeping length constrained (Objective 1)."""
    pattern = re.compile(
        r'\b[A-Z][a-zA-Z0-9\.\-]*(?:\s+(?:of|and|for|in|the|on|to|at|&)\s+[A-Z][a-zA-Z0-9\.\-]*|\s+[A-Z][a-zA-Z0-9\.\-]*)*\b'
    )
    phrases = []
    sentences = re.split(r'[.!?]+(?:\s+|\Z)', text)
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        for match in pattern.finditer(sent):
            phrase = match.group(0).strip()
            phrase = phrase.strip(".,;:!?()[]{}'\"-")
            
            # Restrict proper noun phrase length to max 3 words (or 4 if minor connector exists)
            words = phrase.split()
            if len(words) > 3:
                if len(words) == 4 and any(c in [w.lower() for w in words] for c in ["of", "and", "for", "in", "the", "on", "to", "at", "&"]):
                    pass
                else:
                    continue
                    
            # Filter proper noun phrases containing verbs or stopwords
            has_bad_word = False
            for w in words:
                w_lower = w.lower()
                if w_lower in ["of", "and", "for", "in", "the", "on", "to", "at", "&"]:
                    continue
                if w_lower in STOPWORDS or w_lower in VERBS or w_lower in ARTIFACT_STOPWORDS:
                    has_bad_word = True
                    break
            if has_bad_word:
                continue
                
            if len(phrase) >= 3:
                phrases.append(phrase)
    return phrases

def extract_noun_phrases(text: str) -> list[str]:
    """Extracts common noun phrases and single words from non-stopwords runs (Objective 1)."""
    sentences = re.split(r'[.!?]+(?:\s+|\Z)', text)
    phrases = []
    for sent in sentences:
        tokens = sent.split()
        runs = []
        current_run = []
        for t in tokens:
            t_clean = t.strip(".,;:!?()[]{}'\"-")
            t_lower = t_clean.lower()
            if len(t_clean) >= 3 and not t_clean.isdigit() and t_lower not in STOPWORDS and t_lower not in VERBS and t_lower not in ARTIFACT_STOPWORDS:
                current_run.append(t_clean)
            else:
                if current_run:
                    runs.append(current_run)
                    current_run = []
        if current_run:
            runs.append(current_run)
            
        for run in runs:
            n = len(run)
            # 1-grams
            for w in run:
                phrases.append(w)
            # 2-grams
            for i in range(n - 1):
                phrases.append(" ".join(run[i:i+2]))
            # 3-grams
            for i in range(n - 2):
                phrases.append(" ".join(run[i:i+3]))
    return phrases

def extract_keywords_from_pool(pool: list[dict]) -> list[str]:
    """
    Extracts, cleans, ranks, and deduplicates key phrases from the pool (Objective 11, 12).
    Returns approximately 100-200 high-quality topics.
    """
    phrase_counts = {}
    article_counts = {}
    display_casings = {}
    is_proper_noun = {}
    
    for i, art in enumerate(pool):
        title = art.get("title", "")
        # Strip smart quotes to clean artifacts
        title = re.sub(r'[“”‘’"]', ' ', title)
        desc = art.get("description", "") or ""
        desc = re.sub(r'[“”‘’"]', ' ', desc)
        
        url = art.get("url", f"idx-{i}")
        art_key = url if url else title
        
        text = f"{title}. {desc}"
        
        cap_phrases = extract_capitalized_phrases(text)
        noun_phrases = extract_noun_phrases(text)
        
        article_candidates = []
        for p in cap_phrases:
            article_candidates.append((p, True))
        for p in noun_phrases:
            article_candidates.append((p, False))
            
        for phrase, is_prop in article_candidates:
            phrase = clean_phrase_boundaries(phrase)
            if not phrase:
                continue
                
            canonical = canonicalize(phrase)
            if not canonical or len(canonical) < 3:
                continue
                
            words = canonical.split()
            if len(words) == 1 and (words[0] in STOPWORDS or words[0] in VERBS):
                continue
                
            if all(w in STOPWORDS or w in VERBS or w in ARTIFACT_STOPWORDS for w in words):
                continue
                
            if any(art_sw in canonical for art_sw in ARTIFACT_STOPWORDS):
                continue
                
            phrase_counts[canonical] = phrase_counts.get(canonical, 0) + 1
            
            if canonical not in article_counts:
                article_counts[canonical] = set()
            article_counts[canonical].add(art_key)
            
            if canonical not in display_casings:
                display_casings[canonical] = Counter()
            display_casings[canonical][phrase] += 1
            
            if is_prop:
                is_proper_noun[canonical] = True
                
    scored_keywords = []
    for canonical, art_keys in article_counts.items():
        art_count = len(art_keys)
        total_freq = phrase_counts[canonical]
        is_domain = is_domain_relevant(canonical)
        
        # Apply Minimum Quality Threshold (Objective 8)
        if art_count < 2 and not is_domain:
            continue
        if total_freq < 2 and not is_domain:
            continue
            
        # Determine best casing display version (Objective 4)
        casing_counter = display_casings[canonical]
        best_casing = ""
        matched_canonical = False
        
        for val in VARIANT_MAPPING.values():
            if val.lower() == canonical:
                best_casing = val
                matched_canonical = True
                break
                
        if not matched_canonical:
            best_casing = max(
                casing_counter.keys(),
                key=lambda c: casing_counter[c] * (1.0 + get_casing_priority(c))
            )
            
        # Ensure display name has proper capitalization for proper nouns and domain relevance
        if (is_proper_noun.get(canonical, False) or is_domain) and best_casing:
            if best_casing.islower() or best_casing[0].islower():
                best_casing = best_casing.title()
                
        # Calculate improved composite score (Objective 11)
        base_score = art_count * 3.0 + total_freq * 0.5
        multiplier = 1.0
        
        phrase_len = len(canonical.split())
        if phrase_len == 2:
            multiplier *= 2.0
        elif phrase_len >= 3:
            multiplier *= 2.5
            
        if is_proper_noun.get(canonical, False):
            multiplier *= 1.5
            
        if is_domain:
            multiplier *= 3.0
            
        final_score = base_score * multiplier
        scored_keywords.append((best_casing, final_score))
        
    scored_keywords.sort(key=lambda x: x[1], reverse=True)
    
    # Return top 150 high-quality topics (Objective 12)
    top_keywords = [kw for kw, score in scored_keywords[:150]]
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
