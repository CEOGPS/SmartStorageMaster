"""
Database configuration and session management
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DatabaseConfig:
    """Database configuration"""
    
    def __init__(self, db_url: str = None, echo: bool = False):
        """
        Initialize database configuration
        
        Args:
            db_url: Database URL (default: sqlite:///storage.db)
            echo: Enable SQL logging (default: False)
        """
        self.db_url = db_url or "sqlite:///storage.db"
        self.echo = echo
    
    def get_engine(self):
        """Create and return database engine"""
        if "sqlite" in self.db_url:
            # SQLite specific settings. Background scan threads open their own
            # sessions, so file databases need a real connection pool; StaticPool
            # (one shared connection) is only safe for in-memory databases.
            kwargs = {"connect_args": {"check_same_thread": False}}
            if ":memory:" in self.db_url:
                kwargs["poolclass"] = StaticPool
            return create_engine(self.db_url, echo=self.echo, **kwargs)
        else:
            return create_engine(
                self.db_url,
                echo=self.echo,
                pool_pre_ping=True,
            )


# Global engine and session factory
_engine = None
_SessionLocal = None


def init_db(db_url: str = None, echo: bool = False):
    """
    Initialize database engine and session factory
    
    Args:
        db_url: Database URL
        echo: Enable SQL logging
    """
    global _engine, _SessionLocal
    
    config = DatabaseConfig(db_url, echo)
    _engine = config.get_engine()
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    
    # Enable foreign keys for SQLite
    if "sqlite" in (db_url or "sqlite:///storage.db"):
        @event.listens_for(_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    
    logger.info(f"Database initialized: {config.db_url}")


def get_session() -> Session:
    """
    Get a new database session
    
    Returns:
        SQLAlchemy Session
    """
    if _SessionLocal is None:
        init_db()
    return _SessionLocal()


def get_db():
    """
    FastAPI dependency that yields a session and always closes it afterwards
    """
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def get_engine():
    """Get database engine"""
    global _engine
    if _engine is None:
        init_db()
    return _engine


def create_all_tables():
    """Create all database tables"""
    from .models import Base
    
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")


def drop_all_tables():
    """Drop all database tables (use with caution!)"""
    from .models import Base
    
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    logger.warning("All database tables dropped!")


class DatabaseSession:
    """Context manager for database sessions"""
    
    def __enter__(self) -> Session:
        """Enter context and return session"""
        self.session = get_session()
        return self.session
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and close session"""
        self.session.close()
