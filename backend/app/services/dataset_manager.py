import logging
import threading
import traceback
import datetime
import sqlite3
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger(__name__)

# Default empty dataset structure matching DashboardPayload schema
DEFAULT_DATASET: Dict[str, Any] = {
    "keyword": "Default Dashboard",
    "articles": [],
    "pinned_articles": [],
    "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    "next_update": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=settings.REFRESH_INTERVAL_HOURS)).isoformat().replace("+00:00", "Z"),
    "keyword_counts": {}
}

class DatasetManager:
    """
    Manages the global ACTIVE_DATASET in-memory snapshot.
    ACTIVE_DATASET is read-only during request serving and replaced atomically.
    SQLite remains the single authoritative persistent store.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._active_dataset: Dict[str, Any] = dict(DEFAULT_DATASET)

    def get_active_dataset(self) -> Dict[str, Any]:
        """Returns a copy/reference of the current read-only ACTIVE_DATASET snapshot."""
        with self._lock:
            return self._active_dataset

    def replace_active_dataset(self, new_dataset: Dict[str, Any]):
        """Atomically replaces the ACTIVE_DATASET reference in a thread-safe manner."""
        with self._lock:
            self._active_dataset = dict(new_dataset)
        logger.info("[ACTIVE_DATASET] Snapshot atomically replaced in memory.")

    def load_startup_snapshot(self):
        """
        Populates ACTIVE_DATASET from SQLite database on startup.
        No live scraping is required to restore previous backend state.
        """
        logger.info("[STARTUP] Loading ACTIVE_DATASET snapshot from SQLite authoritative store...")
        try:
            from app.services.cache import get_cached_results, search_cache_by_keyword, get_global_keyword_counts
            
            # Try to load cached pipeline result for default_dashboard
            cached = get_cached_results("default_dashboard")
            if cached and isinstance(cached, dict) and cached.get("articles"):
                cached["keyword_counts"] = get_global_keyword_counts()
                self.replace_active_dataset(cached)
                logger.info(f"[STARTUP] Successfully loaded snapshot from SQLite with {len(cached.get('articles', []))} articles.")
                return

            # Fallback to loading all articles from SQLite search cache
            matching = search_cache_by_keyword(None)
            global_kws = get_global_keyword_counts()
            now_str = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
            next_str = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=settings.REFRESH_INTERVAL_HOURS)).isoformat().replace("+00:00", "Z")
            
            payload = {
                "keyword": "Default Dashboard",
                "articles": matching,
                "pinned_articles": [],
                "last_updated": now_str,
                "next_update": next_str,
                "keyword_counts": global_kws
            }
            self.replace_active_dataset(payload)
            logger.info(f"[STARTUP] Loaded fallback snapshot from SQLite with {len(matching)} articles.")
        except Exception as e:
            logger.error(f"[STARTUP] Failed to load startup snapshot from SQLite: {e}\n{traceback.format_exc()}")
            # Maintain default empty dataset state
            self.replace_active_dataset(DEFAULT_DATASET)


class StagingDataset:
    """
    Isolated staging buffer for live refresh pipeline runs.
    Enforces strict commit sequence and atomic rollback.
    """
    def __init__(self, keyword: Optional[str] = None):
        self.keyword = keyword or "Default Dashboard"
        self.articles: List[Dict[str, Any]] = []
        self.pinned_articles: List[Dict[str, Any]] = []
        self.keyword_counts: Dict[str, int] = {}
        self.created_at = datetime.datetime.now(datetime.timezone.utc)
        logger.info(f"[STAGING] Created new StagingDataset buffer for keyword '{self.keyword}'.")

    def set_content(self, articles: List[Dict[str, Any]], pinned_articles: Optional[List[Dict[str, Any]]] = None, keyword_counts: Optional[Dict[str, int]] = None):
        self.articles = articles
        self.pinned_articles = pinned_articles or []
        self.keyword_counts = keyword_counts or {}

    def commit(self) -> Dict[str, Any]:
        """
        Executes strict commit order:
        1. Validate staging dataset non-emptiness/schema
        2. Begin SQLite transaction
        3. Write dataset to SQLite
        4. Commit transaction
        5. Verify commit success
        6. Replace ACTIVE_DATASET atomically
        """
        t0 = datetime.datetime.now(datetime.timezone.utc)
        logger.info(f"[STAGING COMMIT] Beginning strict commit order for {len(self.articles)} articles...")

        # 1. Validation check
        if not isinstance(self.articles, list):
            raise ValueError("Staging dataset articles must be a list.")

        from app.services.cache import save_cached_results, get_db_connection
        
        now_str = t0.isoformat().replace("+00:00", "Z")
        next_str = (t0 + datetime.timedelta(hours=settings.REFRESH_INTERVAL_HOURS)).isoformat().replace("+00:00", "Z")

        payload = {
            "keyword": self.keyword,
            "articles": self.articles,
            "pinned_articles": self.pinned_articles,
            "last_updated": now_str,
            "next_update": next_str,
            "keyword_counts": self.keyword_counts
        }

        # 2-5. SQLite Transaction & Persistence
        logger.info("[STAGING COMMIT] Step 3: Beginning SQLite transaction...")
        conn = get_db_connection()
        try:
            conn.execute("BEGIN TRANSACTION;")
            # Save payload to SQLite cached_pipeline_results
            cache_key = self.keyword if self.keyword and self.keyword != "Default Dashboard" else "default_dashboard"
            save_cached_results(cache_key, payload, conn=conn)
            if cache_key != "default_dashboard":
                save_cached_results("default_dashboard", payload, conn=conn)

            conn.commit()
            logger.info("[STAGING COMMIT] Step 5: SQLite transaction committed successfully.")
        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"[STAGING COMMIT FAILED] SQLite transaction failed: {e}")
            raise e
        finally:
            conn.close()

        # 6. Verify success & 7. Replace ACTIVE_DATASET
        dataset_manager.replace_active_dataset(payload)
        duration = (datetime.datetime.now(datetime.timezone.utc) - t0).total_seconds()
        logger.info(f"[STAGING COMMIT] ACTIVE_DATASET replaced successfully. Refresh duration: {duration:.3f}s.")
        return payload

    def rollback(self, error: Exception):
        """
        Handles failure during pipeline refresh:
        - Discards staging dataset
        - Preserves previous ACTIVE_DATASET
        - Logs complete traceback
        """
        logger.error(f"[STAGING ROLLBACK] Refresh pipeline failed: {error}")
        logger.error(f"[STAGING ROLLBACK] Traceback:\n{traceback.format_exc()}")
        logger.warning("[STAGING ROLLBACK] Staging dataset discarded. ACTIVE_DATASET retained without modification.")


# Global singleton dataset manager
dataset_manager = DatasetManager()
