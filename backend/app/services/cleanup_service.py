"""
Cleanup service for backup and restore operations
"""
from pathlib import Path
from typing import List, Dict
import logging
import shutil
from datetime import datetime
from sqlalchemy.orm import Session

from ..core.cleanup import CleanupManager
from ..db.models import File, BackupFile

logger = logging.getLogger(__name__)


class CleanupService:
    """Service for managing file cleanup and backups"""
    
    def __init__(self, db_session: Session, backup_root: Path = None):
        """
        Initialize cleanup service
        
        Args:
            db_session: SQLAlchemy session
            backup_root: Root directory for backups
        """
        self.db = db_session
        self.cleanup_manager = CleanupManager(backup_root)
    
    def backup_files(self, file_ids: List[str]) -> Dict:
        """
        Backup files and prepare for deletion
        
        Args:
            file_ids: List of file IDs to backup
        
        Returns:
            Result dictionary with backed up file count
        """
        logger.info(f"Backing up {len(file_ids)} files")
        
        backed_up = 0
        failed = 0
        
        for file_id in file_ids:
            file = self.db.query(File).filter_by(id=file_id).first()
            if not file:
                continue
            
            try:
                file_path = Path(file.path)
                if not file_path.exists():
                    logger.warning(f"File not found: {file_path}")
                    failed += 1
                    continue
                
                backup_path = self.cleanup_manager.backup_file(file_path)

                # One backup row per original file (original_file_id is unique),
                # so re-backing up a file updates its existing row
                backup = self.db.query(BackupFile).filter_by(original_file_id=file.id).first()
                if backup is None:
                    backup = BackupFile(original_file_id=file.id)
                    self.db.add(backup)
                backup.original_path = str(file_path)
                backup.backup_path = str(backup_path)
                backup.file_size = file.size
                backup.deleted_at = datetime.utcnow()
                backup.restored_at = None
                backup.permanently_deleted_at = None
                backed_up += 1
            
            except Exception as e:
                logger.error(f"Failed to backup file {file_id}: {e}")
                failed += 1
        
        self.db.commit()
        
        return {
            'backed_up': backed_up,
            'failed': failed,
            'total': len(file_ids),
        }
    
    def delete_files(self, file_ids: List[str]) -> Dict:
        """
        Delete files after backup
        
        Args:
            file_ids: List of file IDs to delete
        
        Returns:
            Result dictionary
        """
        logger.info(f"Deleting {len(file_ids)} files")
        
        deleted = 0
        failed = 0
        
        for file_id in file_ids:
            file = self.db.query(File).filter_by(id=file_id).first()
            if not file:
                continue
            
            try:
                file_path = Path(file.path)
                if file_path.exists():
                    file_path.unlink()
                    deleted += 1
                    logger.info(f"Deleted file: {file_path}")
            
            except Exception as e:
                logger.error(f"Failed to delete file {file_id}: {e}")
                failed += 1
        
        return {
            'deleted': deleted,
            'failed': failed,
            'total': len(file_ids),
        }
    
    def get_backups(self) -> List[Dict]:
        """
        Get list of backup files
        
        Returns:
            List of backup dictionaries
        """
        backups = self.db.query(BackupFile).filter(
            BackupFile.restored_at.is_(None),
            BackupFile.permanently_deleted_at.is_(None),
        ).all()
        
        return [
            {
                'id': b.id,
                'original_path': b.original_path,
                'backup_path': b.backup_path,
                'file_size': b.file_size,
                'deleted_at': b.deleted_at.isoformat(),
                'is_restored': b.is_restored,
            }
            for b in backups
        ]
    
    def restore_file(self, backup_id: str, restore_to: str = None) -> Dict:
        """
        Restore file from backup
        
        Args:
            backup_id: ID of backup to restore
            restore_to: Optional custom restore path
        
        Returns:
            Result dictionary
        """
        backup = self.db.query(BackupFile).filter_by(id=backup_id).first()
        
        if not backup:
            return {'success': False, 'error': 'Backup not found'}
        
        try:
            backup_path = Path(backup.backup_path)
            restore_path = Path(restore_to or backup.original_path)
            
            restored = self.cleanup_manager.restore_file(backup_path, restore_path)
            
            backup.restored_at = datetime.utcnow()
            self.db.commit()
            
            logger.info(f"Restored file: {backup_path} -> {restored}")
            
            return {
                'success': True,
                'restored_path': str(restored),
            }
        
        except Exception as e:
            logger.error(f"Failed to restore backup {backup_id}: {e}")
            return {
                'success': False,
                'error': str(e),
            }
    
    def permanently_delete_backup(self, backup_id: str) -> Dict:
        """
        Permanently delete backup file
        
        Args:
            backup_id: ID of backup to delete
        
        Returns:
            Result dictionary
        """
        backup = self.db.query(BackupFile).filter_by(id=backup_id).first()
        
        if not backup:
            return {'success': False, 'error': 'Backup not found'}
        
        try:
            backup_path = Path(backup.backup_path)
            self.cleanup_manager.permanently_delete(backup_path)
            
            backup.permanently_deleted_at = datetime.utcnow()
            self.db.commit()
            
            logger.info(f"Permanently deleted backup: {backup_id}")
            
            return {'success': True}
        
        except Exception as e:
            logger.error(f"Failed to delete backup {backup_id}: {e}")
            return {
                'success': False,
                'error': str(e),
            }
    
    def cleanup_old_backups(self, max_age_days: int = 30) -> Dict:
        """
        Clean up old backups
        
        Args:
            max_age_days: Maximum age of backups to keep
        
        Returns:
            Result dictionary
        """
        logger.info(f"Cleaning up backups older than {max_age_days} days")
        
        deleted = self.cleanup_manager.cleanup_old_backups(max_age_days)
        
        return {
            'deleted_count': deleted,
            'message': f'Cleaned up {deleted} old backup directories',
        }
    
    def get_cleanup_stats(self) -> Dict:
        """
        Get cleanup statistics
        
        Returns:
            Statistics dictionary
        """
        backups = self.db.query(BackupFile).filter(
            BackupFile.permanently_deleted_at.is_(None)
        ).all()
        
        total_size = sum(b.file_size for b in backups)
        active_backups = [b for b in backups if b.restored_at is None]

        backup_root = Path(self.cleanup_manager.backup_root)
        probe = backup_root if backup_root.exists() else Path(backup_root.anchor or '.')
        disk_free = shutil.disk_usage(probe).free

        return {
            'total_backups': len(backups),
            'active_backups': len(active_backups),
            'total_backup_size': total_size,
            'backup_root': str(backup_root),
            'disk_free': disk_free,
        }
