import os
import json
from typing import List

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

def load_monitored_keywords() -> List[str]:
    """Load monitored keywords from config/keywords.json."""
    if not os.path.exists(KEYWORDS_JSON_PATH):
        # Create directory and write default keywords
        os.makedirs(os.path.dirname(KEYWORDS_JSON_PATH), exist_ok=True)
        save_monitored_keywords(DEFAULT_MONITORED_KEYWORDS)
        return DEFAULT_MONITORED_KEYWORDS
    try:
        with open(KEYWORDS_JSON_PATH, "r", encoding="utf-8") as f:
            keywords = json.load(f)
            if isinstance(keywords, list):
                # Clean up empty values and duplicates
                seen = set()
                cleaned = []
                for k in keywords:
                    k_str = str(k).strip()
                    if k_str and k_str.lower() not in seen:
                        seen.add(k_str.lower())
                        cleaned.append(k_str)
                return cleaned
            return DEFAULT_MONITORED_KEYWORDS
    except Exception:
        return DEFAULT_MONITORED_KEYWORDS

def save_monitored_keywords(keywords: List[str]) -> None:
    """Save monitored keywords to config/keywords.json."""
    os.makedirs(os.path.dirname(KEYWORDS_JSON_PATH), exist_ok=True)
    # Deduplicate before saving
    seen = set()
    cleaned = []
    for k in keywords:
        k_str = str(k).strip()
        if k_str and k_str.lower() not in seen:
            seen.add(k_str.lower())
            cleaned.append(k_str)
            
    with open(KEYWORDS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=4)
