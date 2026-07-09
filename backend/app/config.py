import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PORT: int = 8000
    DATABASE_PATH: str = "backend.db"
    
    # API Keys from the plan
    GEMINI_API_KEY: str = ""
    NEWSAPI_KEY: str = ""
    GNEWS_KEY: str = ""
    MEDIASTACK_KEY: str = ""
    
    # Backwards compatibility key support (optional, but good to have)
    NEWS_API_KEY: str = ""
    GNEWS_API_KEY: str = ""
    MEDIASTACK_API_KEY: str = ""
    
    # Local LLM settings from the plan
    OLLAMA_MODEL: str = "phi3:mini"
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_URL: str = "http://localhost:11434" # Compatibility
    
    # LLM Intelligence Settings
    ENABLE_LLM_REASONING: bool = True
    OLLAMA_TIMEOUT: float = 30.0
    LLM_BATCH_SIZE: int = 3
    LLM_CACHE_ENABLED: bool = True
    LLM_CACHE_TTL: int = 604800 # 7 days in seconds
    
    # Cache settings from the plan
    CACHE_FILE_PATH: str = "./cache.json"
    REFRESH_INTERVAL_HOURS: int = 12
    CACHE_TTL_DAYS: int = 7
    DE_DUP_DAYS: int = 7 # Compatibility
    SEEN_ARTICLES_JSON_PATH: str = "seen_articles.json" # Compatibility
    
    # Default keywords to merge for the initial/empty search dashboard
    DEFAULT_KEYWORDS: List[str] = [
        "Manufacturing",
        "Cement Industry",
        "AI",
        "Machine Learning",
        "Automation"
    ]
    
    # Target tech firms for pinned section
    PINNED_COMPANIES: List[str] = [
        "NVIDIA",
        "Microsoft",
        "OpenAI"
    ]

    @property
    def news_api_key_resolved(self) -> str:
        return self.NEWSAPI_KEY or self.NEWS_API_KEY

    @property
    def gnews_key_resolved(self) -> str:
        return self.GNEWS_KEY or self.GNEWS_API_KEY

    @property
    def mediastack_key_resolved(self) -> str:
        return self.MEDIASTACK_KEY or self.MEDIASTACK_API_KEY

    @property
    def ollama_url_resolved(self) -> str:
        return self.OLLAMA_HOST or self.OLLAMA_URL

    @property
    def cache_path_resolved(self) -> str:
        return self.CACHE_FILE_PATH or self.SEEN_ARTICLES_JSON_PATH

    @property
    def ttl_days_resolved(self) -> int:
        return self.CACHE_TTL_DAYS or self.DE_DUP_DAYS

    # Pydantic settings config to load from .env
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
