"""
Safe cleanup module for file deletion and restoration
"""
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import shutil
import logging

logger = logging.getLogger(__name__)


class CleanupManager:
    """Manages safe file deletion with backup functionality"""
    
    def __init__(self, backup_root: Path = None):
        """
        Initialize cleanup manager
        
        Args:
            backup_root: Root directory for backups (default: ./backups)
        """
        self.backup_root = Path(backup_root or "./backups")
        self.backup_root.mkdir(parents=True, exist_ok=True)
        logger.info(f"Cleanup manager initialized with backup root: {self.backup_root}")
    
    def backup_file(self, source_path: Path) -> Path:
        """
        Create backup of file before deletion
        
        Args:
            source_path: Path to file to backup
        
        Returns:
            Path to backup file
        
        Raises:
            FileNotFoundError: If source file doesn't exist
            IOError: If backup fails
        """
        source_path = Path(source_path)
        
        if not source_path.exists():
            raise FileNotFoundError(f"File not found: {source_path}")
        
        # Create backup path with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_subdir = self.backup_root / timestamp
        backup_subdir.mkdir(parents=True, exist_ok=True)
        
        backup_path = backup_subdir / source_path.name
        
        try:
            shutil.copy2(source_path, backup_path)
            logger.info(f"Backed up file: {source_path} -> {backup_path}")
            return backup_path
        
        except IOError as e:
            logger.error(f"Failed to backup file {source_path}: {e}")
            raise
    
    def backup_and_delete(self, file_path: Path) -> Path:
        """
        Backup file and delete original
        
        Args:
            file_path: Path to file to delete
        
        Returns:
            Path to backup file
        """
        backup_path = self.backup_file(file_path)
        
        try:
            file_path.unlink()
            logger.info(f"Deleted original file: {file_path}")
            return backup_path
        
        except Exception as e:
            logger.error(f"Failed to delete {file_path}: {e}")
            # Backup was successful, but couldn't delete original
            raise
    
    def restore_file(self, backup_path: Path, restore_to: Optional[Path] = None) -> Path:
        """
        Restore file from backup
        
        Args:
            backup_path: Path to backup file
            restore_to: Where to restore file (default: original location if detectable)
        
        Returns:
            Path to restored file
        
        Raises:
            FileNotFoundError: If backup doesn't exist
            IOError: If restore fails
        """
        backup_path = Path(backup_path)
        
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")
        
        if restore_to is None:
            # Try to infer original location from database in real implementation
            restore_to = Path.home() / "restored_files"
        
        restore_to = Path(restore_to)
        restore_to.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            shutil.copy2(backup_path, restore_to)
            logger.info(f"Restored file: {backup_path} -> {restore_to}")
            return restore_to
        
        except IOError as e:
            logger.error(f"Failed to restore file {backup_path}: {e}")
            raise
    
    def permanently_delete(self, file_path: Path) -> None:
        """
        Permanently delete file
        
        Args:
            file_path: Path to file
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            logger.warning(f"File not found for deletion: {file_path}")
            return
        
        try:
            file_path.unlink()
            logger.info(f"Permanently deleted: {file_path}")
        
        except Exception as e:
            logger.error(f"Failed to permanently delete {file_path}: {e}")
            raise
    
    def cleanup_old_backups(self, max_age_days: int = 30) -> int:
        """
        Delete backup files older than specified days
        
        Args:
            max_age_days: Maximum age in days
        
        Returns:
            Number of backups deleted
        """
        from datetime import timedelta
        
        cutoff_time = datetime.now() - timedelta(days=max_age_days)
        deleted_count = 0
        
        for backup_dir in self.backup_root.iterdir():
            if backup_dir.is_dir():
                try:
                    dir_time = datetime.fromtimestamp(backup_dir.stat().st_mtime)
                    if dir_time < cutoff_time:
                        shutil.rmtree(backup_dir)
                        deleted_count += 1
                        logger.info(f"Deleted old backup: {backup_dir}")
                except Exception as e:
                    logger.warning(f"Failed to delete backup {backup_dir}: {e}")
        
        return deleted_count
    
    def get_backup_size(self) -> int:
        """
        Get total size of all backups
        
        Returns:
            Total size in bytes
        """
        total_size = 0
        
        for file_path in self.backup_root.rglob('*'):
            if file_path.is_file():
                try:
                    total_size += file_path.stat().st_size
                except OSError:
                    continue
        
        return total_size
