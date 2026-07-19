import os
import json
from typing import List, Dict, Any

# Resolve path relative to backend folder
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KEYWORDS_JSON_PATH = os.path.join(BASE_DIR, "config", "keywords.json")

DEFAULT_MONITORED_KEYWORDS = [
    "Artificial Intelligence",
    "Cybersecurity",
    "Robotics",
    "Cloud Computing",
    "Quantum Computing",
    "Dalmia Cement",
    "Manufacturing",
    "Cement Industry"
]

def load_monitored_keywords_detailed() -> List[Dict[str, Any]]:
    """
    Load monitored keywords with detailed properties (e.g. is_processed).
    If the file exists as a flat list, migrates it automatically.
    """
    if not os.path.exists(KEYWORDS_JSON_PATH):
        # Create directory and write default keywords
        os.makedirs(os.path.dirname(KEYWORDS_JSON_PATH), exist_ok=True)
        save_monitored_keywords(DEFAULT_MONITORED_KEYWORDS)
        return [{"keyword": kw, "is_processed": False} for kw in DEFAULT_MONITORED_KEYWORDS]
    try:
        with open(KEYWORDS_JSON_PATH, "r", encoding="utf-8") as f:
            keywords = json.load(f)
            if not isinstance(keywords, list):
                keywords = DEFAULT_MONITORED_KEYWORDS
            
            detailed = []
            seen = set()
            for k in keywords:
                if isinstance(k, dict):
                    k_str = str(k.get("keyword", "")).strip()
                    is_proc = bool(k.get("is_processed", False))
                else:
                    k_str = str(k).strip()
                    is_proc = False
                
                if k_str and k_str.lower() not in seen:
                    seen.add(k_str.lower())
                    detailed.append({"keyword": k_str, "is_processed": is_proc})
            return detailed
    except Exception:
        return [{"keyword": kw, "is_processed": False} for kw in DEFAULT_MONITORED_KEYWORDS]

def save_monitored_keywords_detailed(detailed_keywords: List[Dict[str, Any]]) -> None:
    """Save detailed monitored keywords to config/keywords.json."""
    os.makedirs(os.path.dirname(KEYWORDS_JSON_PATH), exist_ok=True)
    # Deduplicate before saving
    seen = set()
    cleaned = []
    for k in detailed_keywords:
        k_str = str(k.get("keyword", "")).strip()
        is_proc = bool(k.get("is_processed", False))
        if k_str and k_str.lower() not in seen:
            seen.add(k_str.lower())
            cleaned.append({"keyword": k_str, "is_processed": is_proc})
            
    with open(KEYWORDS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=4)

def load_monitored_keywords() -> List[str]:
    """Load monitored keywords from config/keywords.json as flat list of strings for compatibility."""
    detailed = load_monitored_keywords_detailed()
    return [d["keyword"] for d in detailed]

def save_monitored_keywords(keywords: List[str]) -> None:
    """Save flat list of keywords, preserving processed state for existing ones."""
    existing_detailed = load_monitored_keywords_detailed()
    state_map = {d["keyword"].lower(): d["is_processed"] for d in existing_detailed}
    
    new_detailed = []
    for kw in keywords:
        kw_clean = kw.strip()
        if kw_clean:
            is_proc = state_map.get(kw_clean.lower(), False)
            new_detailed.append({"keyword": kw_clean, "is_processed": is_proc})
            
    save_monitored_keywords_detailed(new_detailed)

def mark_keyword_processed(keyword: str, is_processed: bool = True) -> None:
    """Mark a keyword as processed (or unprocessed) in the canonical keywords storage."""
    detailed = load_monitored_keywords_detailed()
    updated = False
    for d in detailed:
        if d["keyword"].lower() == keyword.lower().strip():
            d["is_processed"] = is_processed
            updated = True
    if updated:
        save_monitored_keywords_detailed(detailed)
