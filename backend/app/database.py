from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func
from app.config import settings
import logging

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.sqlalchemy_database_uri,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class CachedPipelineResult(Base):
    __tablename__ = "cached_pipeline_results"
    
    keyword = Column(String(255), primary_key=True)
    payload = Column(Text(4294967295), nullable=False) # LONGTEXT equivalent in MySQL
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class LLMCache(Base):
    __tablename__ = "llm_cache"
    
    cache_key = Column(String(255), primary_key=True)
    payload = Column(Text(4294967295), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class ArticleKeyword(Base):
    __tablename__ = "article_keywords"
    
    url = Column(String(768), primary_key=True)
    keywords = Column(Text(4294967295), nullable=False)
    title = Column(String(1024))
    summary = Column(Text(4294967295))
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class NewsdataUsage(Base):
    __tablename__ = "newsdata_usage"
    
    date = Column(String(255), primary_key=True)
    request_count = Column(Integer, default=0)

class SeenArticleHash(Base):
    __tablename__ = "seen_article_hashes"
    
    hash_value = Column(String(255), primary_key=True)
    hash_type = Column(String(50), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

def init_db():
    logger.info("Initializing MySQL database schema with SQLAlchemy...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
