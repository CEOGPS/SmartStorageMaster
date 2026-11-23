"""
Application configuration
"""
from pathlib import Path
from enum import Enum


class Environment(str, Enum):
    """Application environment"""
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


class Config:
    """Base configuration"""
    
    # Application
    APP_NAME = "Storage Manager Pro"
    APP_VERSION = "1.0.0"
    APP_DESCRIPTION = "AI-powered desktop storage management"
    
    # Database
    DATABASE_URL = "sqlite:///storage.db"
    ECHO_SQL = False
    
    # Logging
    LOG_LEVEL = "INFO"
    LOG_DIR = Path("./logs")
    
    # File handling
    BATCH_SIZE = 500
    MAX_WORKERS = 4
    
    # Duplicate detection
    IMAGE_SIMILARITY_THRESHOLD = 0.85
    HASH_ALGORITHMS = ["phash", "dhash", "ahash"]
    
    # Cleanup
    BACKUP_ROOT = Path("./backups")
    DEFAULT_MAX_AGE_DAYS = 30
    
    # Security
    ALLOWED_PATHS: list = []  # Empty = allow all
    EXCLUDED_DIRS = {
        '.git', '.svn', '.hg',
        '__pycache__', '.pytest_cache', '.mypy_cache', 'node_modules',
        '.venv', 'venv', 'env',
        '.idea', '.vscode',
        '$Recycle.Bin', 'System Volume Information',
        '.Trash', '.Spotlight-V100', '.TemporaryItems',
        '.cache', '.local',
    }


class DevelopmentConfig(Config):
    """Development configuration"""
    ENVIRONMENT = Environment.DEVELOPMENT
    DEBUG = True
    ECHO_SQL = False  # Set to True to see SQL queries
    DATABASE_URL = "sqlite:///storage_dev.db"


class ProductionConfig(Config):
    """Production configuration"""
    ENVIRONMENT = Environment.PRODUCTION
    DEBUG = False
    ECHO_SQL = False
    DATABASE_URL = "sqlite:///storage.db"
    
    # Use stronger defaults
    IMAGE_SIMILARITY_THRESHOLD = 0.90


class TestingConfig(Config):
    """Testing configuration"""
    ENVIRONMENT = Environment.TESTING
    DEBUG = True
    ECHO_SQL = False
    DATABASE_URL = "sqlite:///:memory:"
    BACKUP_ROOT = Path("/tmp/test_backups")


def get_config(environment: str = "development") -> Config:
    """
    Get configuration for environment
    
    Args:
        environment: Environment name
    
    Returns:
        Configuration object
    """
    configs = {
        "development": DevelopmentConfig,
        "production": ProductionConfig,
        "testing": TestingConfig,
    }
    
    config_class = configs.get(environment.lower(), DevelopmentConfig)
    return config_class()
