"""
File utilities
"""
from pathlib import Path
from typing import Optional, Tuple
import mimetypes
import shutil
import logging

logger = logging.getLogger(__name__)


def get_file_size(size_bytes: int) -> str:
    """
    Format file size to human-readable string
    
    Args:
        size_bytes: Size in bytes
    
    Returns:
        Formatted size string
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def get_mime_type(file_path: Path) -> Optional[str]:
    """
    Get MIME type for file
    
    Args:
        file_path: Path to file
    
    Returns:
        MIME type string or None
    """
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type


def get_disk_usage(path: Path) -> Tuple[int, int]:
    """
    Get disk usage for path
    
    Args:
        path: Path to check
    
    Returns:
        Tuple of (used, available) in bytes
    """
    try:
        usage = shutil.disk_usage(path)
        return (usage.used, usage.free)
    except Exception as e:
        logger.warning(f"Failed to get disk usage for {path}: {e}")
        return (0, 0)


def is_system_path(path: Path) -> bool:
    """
    Check if path is a system directory
    
    Args:
        path: Path to check
    
    Returns:
        True if system path, False otherwise
    """
    system_paths = {
        'Windows': {
            'C:\\Windows',
            'C:\\Program Files',
            'C:\\Program Files (x86)',
            'C:\\ProgramData',
        },
        'Darwin': {
            '/System',
            '/Library',
            '/Applications',
        },
        'Linux': {
            '/usr',
            '/bin',
            '/sbin',
            '/etc',
            '/var',
        },
    }
    
    import platform
    system = platform.system()
    
    if system not in system_paths:
        return False
    
    for system_path in system_paths[system]:
        try:
            if path.resolve().is_relative_to(Path(system_path).resolve()):
                return True
        except ValueError:
            continue
    
    return False
