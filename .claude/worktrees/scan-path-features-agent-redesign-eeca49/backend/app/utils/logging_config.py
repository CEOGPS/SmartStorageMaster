"""
Logging configuration
"""
import logging
import logging.handlers
from pathlib import Path


def setup_logging(log_dir: Path = None, level: int = logging.INFO) -> None:
    """
    Setup application logging
    
    Args:
        log_dir: Directory for log files
        level: Logging level
    """
    log_dir = Path(log_dir or './logs')
    log_dir.mkdir(exist_ok=True)
    
    # Create formatters
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # create_app() runs once on import of app.main and again from run.py;
    # without this guard every log line was written twice.
    if getattr(root_logger, "_ssm_configured", False):
        return
    root_logger._ssm_configured = True
    
    # File handler
    fh = logging.handlers.RotatingFileHandler(
        log_dir / 'storage_manager.log',
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
    )
    fh.setLevel(level)
    fh.setFormatter(formatter)
    root_logger.addHandler(fh)
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(formatter)
    root_logger.addHandler(ch)
    
    # Suppress verbose logs
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)
