"""
File usage service for managing usage analysis, database persistence, and cleanup prioritization

Handles:
- Persisting usage metadata to database
- Categorizing files by usage
- Generating cleanup recommendations
- Managing configurable thresholds
"""
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session

from app.core.usage_analyzer import UsageAnalyzer, UsageMetadata
from app.db.models import File, UsageThreshold
from app.db.connection import get_session

logger = logging.getLogger(__name__)


class UsageService:
    """Manages file usage analysis and cleanup prioritization"""
    
    def __init__(self, db_session: Optional[Session] = None):
        """
        Initialize usage service
        
        Args:
            db_session: SQLAlchemy session (uses default if None)
        """
        self.db = db_session or get_session()
        self.analyzer = None
        self._init_analyzer()
    
    def _init_analyzer(self):
        """Initialize analyzer with thresholds from database"""
        thresholds = self.get_thresholds()
        
        self.analyzer = UsageAnalyzer(
            recently_used_days=thresholds["recently_used_days"],
            rarely_used_days=thresholds["rarely_used_days"],
            not_used_days=thresholds["not_used_days"],
            min_priority_size_mb=thresholds["min_priority_size_mb"],
        )
    
    def get_thresholds(self) -> Dict:
        """
        Get current usage thresholds from database
        
        Returns:
            Dictionary with threshold configuration
        """
        try:
            threshold = self.db.query(UsageThreshold).first()
            if threshold:
                return {
                    "recently_used_days": threshold.recently_used_days,
                    "rarely_used_days": threshold.rarely_used_days,
                    "not_used_days": threshold.not_used_days,
                    "min_priority_size_mb": threshold.min_priority_size_mb,
                }
        except Exception as e:
            logger.warning(f"Error fetching thresholds: {e}")
        
        # Return defaults
        return {
            "recently_used_days": UsageAnalyzer.DEFAULT_RECENTLY_USED,
            "rarely_used_days": UsageAnalyzer.DEFAULT_RARELY_USED,
            "not_used_days": UsageAnalyzer.DEFAULT_NOT_USED,
            "min_priority_size_mb": UsageAnalyzer.DEFAULT_MIN_PRIORITY_SIZE_MB,
        }
    
    def update_thresholds(
        self,
        recently_used_days: Optional[int] = None,
        rarely_used_days: Optional[int] = None,
        not_used_days: Optional[int] = None,
        min_priority_size_mb: Optional[int] = None,
    ) -> Dict:
        """
        Update usage thresholds
        
        Args:
            recently_used_days: Days for "recently used" category
            rarely_used_days: Days for "rarely used" category
            not_used_days: Days for "not used" category
            min_priority_size_mb: Minimum size (MB) for high priority
        
        Returns:
            Updated threshold configuration
        """
        try:
            threshold = self.db.query(UsageThreshold).first()
            if not threshold:
                threshold = UsageThreshold()
                self.db.add(threshold)
            
            if recently_used_days is not None:
                threshold.recently_used_days = recently_used_days
            if rarely_used_days is not None:
                threshold.rarely_used_days = rarely_used_days
            if not_used_days is not None:
                threshold.not_used_days = not_used_days
            if min_priority_size_mb is not None:
                threshold.min_priority_size_mb = min_priority_size_mb
            
            threshold.updated_at = datetime.utcnow()
            self.db.commit()
            
            # Reinitialize analyzer with new thresholds
            self._init_analyzer()
            
            logger.info("Usage thresholds updated successfully")
            return self.get_thresholds()
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating thresholds: {e}")
            raise
    
    def update_file_usage(self, file_id: str, metadata: UsageMetadata) -> bool:
        """
        Update file usage metadata in database
        
        Args:
            file_id: ID of file to update
            metadata: UsageMetadata object with computed values
        
        Returns:
            True if successful, False otherwise
        """
        try:
            file = self.db.query(File).filter(File.id == file_id).first()
            if not file:
                logger.warning(f"File not found: {file_id}")
                return False
            
            file.last_accessed = metadata.last_accessed
            file.usage_category = metadata.usage_category
            file.days_since_access = metadata.days_since_access
            file.usage_priority = metadata.usage_priority
            
            self.db.commit()
            return True
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating file usage: {e}")
            return False
    
    def analyze_and_store_usage(self, file_path: Path) -> Optional[str]:
        """
        Analyze a file and store usage metadata
        
        Args:
            file_path: Path to file to analyze
        
        Returns:
            File ID if successful, None otherwise
        """
        try:
            # Find file in database
            file = self.db.query(File).filter(File.path == str(file_path)).first()
            if not file:
                logger.debug(f"File not found in database: {file_path}")
                return None
            
            # Analyze usage
            metadata = self.analyzer.analyze_file(file_path)
            if metadata:
                self.update_file_usage(file.id, metadata)
                return file.id
        
        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {e}")
        
        return None
    
    def batch_update_usage(self, file_paths: List[Path]) -> Dict:
        """
        Batch analyze and store usage for multiple files

        Looks files up 500 at a time and commits once per batch. (It used to do two
        lookups and a separate commit per file, and every commit is a disk sync, so
        this step took most of the time of a whole scan.)

        Args:
            file_paths: List of file paths to analyze

        Returns:
            Dictionary with results {updated: int, failed: int, errors: List}
        """
        results = {"updated": 0, "failed": 0, "errors": []}
        chunk_size = 500

        for start in range(0, len(file_paths), chunk_size):
            paths = [Path(p) for p in file_paths[start:start + chunk_size]]
            try:
                rows = {
                    f.path: f
                    for f in self.db.query(File).filter(File.path.in_([str(p) for p in paths])).all()
                }
            except Exception as e:
                self.db.rollback()
                results["failed"] += len(paths)
                results["errors"].append(str(e))
                continue

            pending = 0
            for path in paths:
                row = rows.get(str(path))
                if row is None:
                    logger.debug(f"File not found in database: {path}")
                    results["failed"] += 1
                    continue
                try:
                    metadata = self.analyzer.analyze_file(path)
                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append(str(e))
                    continue
                if not metadata:
                    results["failed"] += 1
                    continue
                row.last_accessed = metadata.last_accessed
                row.usage_category = metadata.usage_category
                row.days_since_access = metadata.days_since_access
                row.usage_priority = metadata.usage_priority
                pending += 1

            try:
                self.db.commit()
                results["updated"] += pending
            except Exception as e:
                self.db.rollback()
                results["failed"] += pending
                results["errors"].append(str(e))

        return results

    def get_files_by_category(
        self,
        category: str,
        limit: Optional[int] = None,
        min_priority: float = 0.0,
    ) -> List[Dict]:
        """
        Get files by usage category, sorted by priority
        
        Args:
            category: Usage category (RECENTLY_USED, RARELY_USED, NOT_USED)
            limit: Maximum results to return
            min_priority: Minimum priority score filter
        
        Returns:
            List of file metadata dictionaries
        """
        try:
            query = self.db.query(File).filter(
                File.usage_category == category,
                File.usage_priority >= min_priority,
            ).order_by(File.usage_priority.desc())
            
            if limit:
                query = query.limit(limit)
            
            files = query.all()
            
            return [
                {
                    "id": f.id,
                    "path": f.path,
                    "name": f.name,
                    "size_mb": round(f.size / (1024 * 1024), 2),
                    "usage_category": f.usage_category,
                    "usage_priority": f.usage_priority,
                    "days_since_access": f.days_since_access,
                    "last_accessed": f.last_accessed.isoformat() if f.last_accessed else None,
                    "modified_at": f.modified_at.isoformat() if f.modified_at else None,
                }
                for f in files
            ]
        
        except Exception as e:
            logger.error(f"Error fetching files by category: {e}")
            return []
    
    def get_usage_summary(self) -> Dict:
        """
        Get summary of file usage across all categories
        
        Returns:
            Dictionary with usage statistics
        """
        try:
            summary = {
                "RECENTLY_USED": {"count": 0, "total_size_mb": 0.0},
                "RARELY_USED": {"count": 0, "total_size_mb": 0.0},
                "NOT_USED": {"count": 0, "total_size_mb": 0.0},
            }
            
            for category in summary.keys():
                files = self.db.query(File).filter(File.usage_category == category).all()
                summary[category]["count"] = len(files)
                summary[category]["total_size_mb"] = round(
                    sum(f.size for f in files) / (1024 * 1024),
                    2
                )
            
            # Calculate total and potential savings
            total_size_mb = sum(cat["total_size_mb"] for cat in summary.values())
            not_used_size = summary["NOT_USED"]["total_size_mb"]
            rarely_used_size = summary["RARELY_USED"]["total_size_mb"]
            
            return {
                "summary": summary,
                "total_files": sum(cat["count"] for cat in summary.values()),
                "total_size_mb": round(total_size_mb, 2),
                "potential_cleanup_mb": round(not_used_size + rarely_used_size * 0.5, 2),
                "thresholds": self.get_thresholds(),
            }
        
        except Exception as e:
            logger.error(f"Error calculating usage summary: {e}")
            return {"error": str(e)}
    
    def get_cleanup_recommendations(
        self,
        limit: int = 100,
        min_priority: float = 0.7,
    ) -> List[Dict]:
        """
        Get prioritized cleanup recommendations
        
        Args:
            limit: Maximum files to return
            min_priority: Minimum priority score (0.0-1.0)
        
        Returns:
            List of files recommended for cleanup, sorted by priority
        """
        try:
            files = self.db.query(File).filter(
                File.usage_priority >= min_priority,
                File.usage_category.in_(["RARELY_USED", "NOT_USED"]),
            ).order_by(
                File.usage_priority.desc(),
                File.size.desc(),
            ).limit(limit).all()
            
            recommendations = []
            for f in files:
                reason = []
                
                if f.usage_category == "NOT_USED":
                    reason.append(f"Not accessed for {f.days_since_access} days")
                elif f.usage_category == "RARELY_USED":
                    reason.append(f"Rarely used ({f.days_since_access} days since access)")
                
                if f.size > 1024 * 1024 * 100:  # > 100 MB
                    reason.append("Large file")
                
                recommendations.append({
                    "id": f.id,
                    "path": f.path,
                    "name": f.name,
                    "size_mb": round(f.size / (1024 * 1024), 2),
                    "usage_category": f.usage_category,
                    "priority": f.usage_priority,
                    "reason": ", ".join(reason),
                    "last_accessed": f.last_accessed.isoformat() if f.last_accessed else None,
                })
            
            return recommendations
        
        except Exception as e:
            logger.error(f"Error getting cleanup recommendations: {e}")
            return []
    
    def get_file_usage_details(self, file_id: str) -> Optional[Dict]:
        """
        Get detailed usage information for a specific file
        
        Args:
            file_id: ID of file
        
        Returns:
            Dictionary with usage details or None
        """
        try:
            file = self.db.query(File).filter(File.id == file_id).first()
            if not file:
                return None
            
            return {
                "id": file.id,
                "path": file.path,
                "name": file.name,
                "size_mb": round(file.size / (1024 * 1024), 2),
                "created_at": file.created_at.isoformat() if file.created_at else None,
                "modified_at": file.modified_at.isoformat() if file.modified_at else None,
                "last_accessed": file.last_accessed.isoformat() if file.last_accessed else None,
                "days_since_access": file.days_since_access,
                "usage_category": file.usage_category,
                "usage_priority": file.usage_priority,
            }
        
        except Exception as e:
            logger.error(f"Error fetching file usage details: {e}")
            return None
