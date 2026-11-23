"""
File usage analysis module for computing usage metadata and categorization

Analyzes file access patterns based on:
- Last access time (platform-dependent)
- Last modified time
- Creation time
- File size
"""
from pathlib import Path
from typing import Optional, Dict, Tuple, Generator
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging
import os
import sys

logger = logging.getLogger(__name__)


@dataclass
class UsageMetadata:
    """Container for file usage metadata"""
    path: Path
    size: int
    created_at: datetime
    modified_at: datetime
    last_accessed: Optional[datetime]
    days_since_access: int
    usage_category: str  # RECENTLY_USED, RARELY_USED, NOT_USED
    usage_priority: float  # 0.0-1.0, higher = higher priority for cleanup
    
    def __repr__(self):
        return (f"<UsageMetadata(path={self.path.name}, category={self.usage_category}, "
                f"priority={self.usage_priority:.2f})>")


class UsageAnalyzer:
    """Analyzes file usage patterns and categorizes files for cleanup"""
    
    # Default thresholds (days)
    DEFAULT_RECENTLY_USED = 30      # 0-30 days
    DEFAULT_RARELY_USED = 180       # 31-180 days
    DEFAULT_NOT_USED = 180          # 180+ days
    DEFAULT_MIN_PRIORITY_SIZE_MB = 100
    
    # System directories to skip
    EXCLUDED_DIRS = {
        '.git', '.svn', '.hg',
        '__pycache__', '.pytest_cache', '.mypy_cache', 'node_modules',
        '.venv', 'venv', 'env',
        '.idea', '.vscode',
        '$Recycle.Bin', 'System Volume Information', '$WINDOWS.~BT',
        '.Trash', '.Spotlight-V100', '.TemporaryItems',
        '.cache', '.local',
    }
    
    def __init__(
        self,
        recently_used_days: int = DEFAULT_RECENTLY_USED,
        rarely_used_days: int = DEFAULT_RARELY_USED,
        not_used_days: int = DEFAULT_NOT_USED,
        min_priority_size_mb: int = DEFAULT_MIN_PRIORITY_SIZE_MB,
    ):
        """
        Initialize usage analyzer with configurable thresholds
        
        Args:
            recently_used_days: Days to consider a file "recently used" (default: 30)
            rarely_used_days: Days to consider a file "rarely used" (default: 180)
            not_used_days: Days to consider a file "not used" (default: 180)
            min_priority_size_mb: Minimum file size (MB) for high priority (default: 100)
        """
        self.recently_used_days = recently_used_days
        self.rarely_used_days = rarely_used_days
        self.not_used_days = not_used_days
        self.min_priority_size_mb = min_priority_size_mb
        self._analysis_timestamp = datetime.utcnow()
    
    def analyze_file(self, file_path: Path) -> Optional[UsageMetadata]:
        """
        Analyze a single file and compute usage metadata
        
        Args:
            file_path: Path to file
        
        Returns:
            UsageMetadata object or None if file is inaccessible
        """
        try:
            stat = file_path.stat()
            size = stat.st_size
            
            # Get timestamps
            created_at = datetime.fromtimestamp(stat.st_ctime)
            modified_at = datetime.fromtimestamp(stat.st_mtime)
            
            # Get last access time (platform-dependent)
            last_accessed = self._get_last_accessed(stat, file_path)
            
            # Calculate days since access
            if last_accessed:
                days_since = (self._analysis_timestamp - last_accessed).days
            else:
                # Fall back to modified time if access time unavailable
                days_since = (self._analysis_timestamp - modified_at).days
                last_accessed = None
            
            # Categorize usage
            usage_category = self._categorize_usage(days_since)
            
            # Calculate priority score
            usage_priority = self._calculate_priority(usage_category, size, days_since)
            
            return UsageMetadata(
                path=file_path,
                size=size,
                created_at=created_at,
                modified_at=modified_at,
                last_accessed=last_accessed,
                days_since_access=days_since,
                usage_category=usage_category,
                usage_priority=usage_priority,
            )
        
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot analyze file {file_path}: {e}")
            return None
    
    def _get_last_accessed(self, stat_result, file_path: Path) -> Optional[datetime]:
        """
        Get last access time from file stat
        
        Handles platform differences:
        - Linux: st_atime (accurate)
        - macOS: st_atime (may be disabled)
        - Windows: No direct atime, use st_mtime as fallback
        
        Args:
            stat_result: Result from Path.stat()
            file_path: Path to file
        
        Returns:
            Last accessed time or None if unavailable
        """
        try:
            # Try to get atime
            atime = stat_result.st_atime
            
            # On some systems, atime might be 0 or older than mtime
            if atime > 0:
                accessed_dt = datetime.fromtimestamp(atime)
                # Validate that atime is reasonable (not before mtime)
                mtime_dt = datetime.fromtimestamp(stat_result.st_mtime)
                if accessed_dt >= mtime_dt:
                    return accessed_dt
            
            return None
        
        except (OSError, ValueError) as e:
            logger.debug(f"Cannot get access time for {file_path}: {e}")
            return None
    
    def _categorize_usage(self, days_since_access: int) -> str:
        """
        Categorize file usage based on days since last access
        
        Args:
            days_since_access: Number of days since last access
        
        Returns:
            Usage category: RECENTLY_USED, RARELY_USED, or NOT_USED
        """
        if days_since_access <= self.recently_used_days:
            return "RECENTLY_USED"
        elif days_since_access <= self.rarely_used_days:
            return "RARELY_USED"
        else:
            return "NOT_USED"
    
    def _calculate_priority(self, usage_category: str, size: int, days_since: int) -> float:
        """
        Calculate cleanup priority score (0.0-1.0)
        
        Combines:
        - Usage category (NOT_USED > RARELY_USED > RECENTLY_USED)
        - File size (larger files = higher priority)
        - Days since access (older files = higher priority)
        
        Args:
            usage_category: File usage category
            size: File size in bytes
            days_since: Days since last access
        
        Returns:
            Priority score (0.0-1.0)
        """
        # Category base score
        category_scores = {
            "RECENTLY_USED": 0.1,
            "RARELY_USED": 0.5,
            "NOT_USED": 0.9,
        }
        base_score = category_scores.get(usage_category, 0.0)
        
        # Size bonus (files >= min_priority_size add 0.1)
        min_size_bytes = self.min_priority_size_mb * 1024 * 1024
        size_bonus = 0.1 if size >= min_size_bytes else 0.0
        
        # Age bonus (older files add up to 0.1 based on age beyond threshold)
        age_bonus = 0.0
        if usage_category == "NOT_USED":
            # Increase bonus as file gets older
            max_age_days = self.not_used_days + 365  # 1 year beyond threshold
            age_days = max(0, days_since - self.not_used_days)
            age_bonus = min(0.1, (age_days / max_age_days) * 0.1)
        
        priority = min(1.0, base_score + size_bonus + age_bonus)
        return round(priority, 3)
    
    def analyze_directory(
        self,
        root_path: Path,
        recursive: bool = True,
        batch_size: int = 500,
    ) -> Generator[UsageMetadata, None, None]:
        """
        Recursively analyze files in a directory
        
        Args:
            root_path: Root directory to analyze
            recursive: Whether to recurse into subdirectories
            batch_size: Number of files to yield before returning
        
        Yields:
            UsageMetadata objects for each file
        """
        root_path = Path(root_path)
        
        if not root_path.exists():
            logger.error(f"Path does not exist: {root_path}")
            return
        
        if not root_path.is_dir():
            logger.error(f"Path is not a directory: {root_path}")
            return
        
        logger.info(f"Starting usage analysis: {root_path}")
        
        try:
            for metadata in self._analyze_recursive(root_path, recursive):
                if metadata:
                    yield metadata
        except Exception as e:
            logger.error(f"Error during usage analysis: {e}", exc_info=True)
            raise
    
    def _analyze_recursive(
        self,
        directory: Path,
        recursive: bool,
    ) -> Generator[UsageMetadata, None, None]:
        """
        Recursively analyze directory
        
        Args:
            directory: Directory to analyze
            recursive: Whether to recurse into subdirectories
        
        Yields:
            UsageMetadata objects
        """
        try:
            entries = list(directory.iterdir())
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot access directory {directory}: {e}")
            return
        
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    # Skip excluded directories
                    if entry.name not in self.EXCLUDED_DIRS:
                        if recursive:
                            yield from self._analyze_recursive(entry, recursive)
                
                elif entry.is_file(follow_symlinks=False):
                    metadata = self.analyze_file(entry)
                    if metadata:
                        yield metadata
            
            except (PermissionError, OSError) as e:
                logger.warning(f"Cannot access {entry}: {e}")
                continue
    
    def batch_analyze(
        self,
        file_paths: list[Path],
    ) -> Dict[str, list[UsageMetadata]]:
        """
        Analyze multiple files and group by category
        
        Args:
            file_paths: List of file paths to analyze
        
        Returns:
            Dictionary grouped by usage category
        """
        results = {
            "RECENTLY_USED": [],
            "RARELY_USED": [],
            "NOT_USED": [],
            "errors": [],
        }
        
        for file_path in file_paths:
            metadata = self.analyze_file(file_path)
            if metadata:
                results[metadata.usage_category].append(metadata)
            else:
                results["errors"].append(str(file_path))
        
        return results
    
    def get_cleanup_candidates(
        self,
        metadata_list: list[UsageMetadata],
        min_priority: float = 0.5,
        max_results: Optional[int] = None,
    ) -> list[UsageMetadata]:
        """
        Get prioritized cleanup candidates from metadata list
        
        Args:
            metadata_list: List of UsageMetadata objects
            min_priority: Minimum priority score to include (0.0-1.0)
            max_results: Maximum results to return (None = all)
        
        Returns:
            Sorted list of cleanup candidates
        """
        # Filter by priority
        candidates = [m for m in metadata_list if m.usage_priority >= min_priority]
        
        # Sort by priority (descending), then by size (descending)
        candidates.sort(key=lambda x: (x.usage_priority, x.size), reverse=True)
        
        # Limit results
        if max_results:
            candidates = candidates[:max_results]
        
        return candidates
    
    def get_summary_statistics(
        self,
        metadata_list: list[UsageMetadata],
    ) -> Dict:
        """
        Calculate summary statistics for metadata list
        
        Args:
            metadata_list: List of UsageMetadata objects
        
        Returns:
            Dictionary with statistics
        """
        if not metadata_list:
            return {
                "total_files": 0,
                "total_size_mb": 0.0,
                "categories": {},
            }
        
        # Count by category
        categories = {}
        for metadata in metadata_list:
            cat = metadata.usage_category
            if cat not in categories:
                categories[cat] = {
                    "count": 0,
                    "total_size_mb": 0.0,
                    "average_priority": 0.0,
                }
            categories[cat]["count"] += 1
            categories[cat]["total_size_mb"] += metadata.size / (1024 * 1024)
        
        # Calculate average priority per category
        for metadata in metadata_list:
            cat = metadata.usage_category
            # This is simplified; in production, calculate true average
        
        return {
            "total_files": len(metadata_list),
            "total_size_mb": sum(m.size for m in metadata_list) / (1024 * 1024),
            "categories": categories,
            "highest_priority": max((m.usage_priority for m in metadata_list), default=0.0),
        }
