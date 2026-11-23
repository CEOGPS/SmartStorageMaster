"""
Cleanup and backup API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import logging

from ...db import get_db
from ...services.cleanup_service import CleanupService
from ...api.schemas import (
    BackupFileIdsRequest,
    DeleteFileIdsRequest,
    RestoreFileRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cleanup", tags=["cleanup"])


@router.post("/backup", response_model=dict)
def backup_files(
    request: BackupFileIdsRequest,
    db: Session = Depends(get_db),
):
    """
    Backup files
    
    Args:
        request: File IDs to backup
        db: Database session
    
    Returns:
        Backup result
    """
    try:
        service = CleanupService(db)
        result = service.backup_files(request.file_ids)
        
        logger.info(
            f"Backed up {result['backed_up']}/{result['total']} files"
        )
        
        return {'success': True, 'data': result}
    
    except Exception as e:
        logger.error(f"Failed to backup files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete", response_model=dict)
def delete_files(
    request: DeleteFileIdsRequest,
    db: Session = Depends(get_db),
):
    """
    Delete files (after backup)
    
    Args:
        request: File IDs to delete
        db: Database session
    
    Returns:
        Delete result
    """
    try:
        service = CleanupService(db)
        result = service.delete_files(request.file_ids)
        
        logger.info(
            f"Deleted {result['deleted']}/{result['total']} files"
        )
        
        return {'success': True, 'data': result}
    
    except Exception as e:
        logger.error(f"Failed to delete files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backups", response_model=dict)
def get_backups(db: Session = Depends(get_db)):
    """
    Get list of backups
    
    Returns:
        List of backup files
    """
    try:
        service = CleanupService(db)
        backups = service.get_backups()
        
        return {
            'success': True,
            'data': {
                'backups': backups,
                'count': len(backups),
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get backups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restore", response_model=dict)
def restore_file(
    request: RestoreFileRequest,
    db: Session = Depends(get_db),
):
    """
    Restore file from backup
    
    Args:
        request: Restore configuration
        db: Database session
    
    Returns:
        Restore result
    """
    try:
        service = CleanupService(db)
        result = service.restore_file(request.backup_id, request.restore_to)
        
        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])
        
        logger.info(f"Restored file from backup {request.backup_id}")
        return {'success': True, 'data': result}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to restore file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup-old", response_model=dict)
def cleanup_old_backups(max_age_days: int = 30, db: Session = Depends(get_db)):
    """
    Clean up old backups
    
    Args:
        max_age_days: Maximum age of backups to keep
        db: Database session
    
    Returns:
        Cleanup result
    """
    try:
        service = CleanupService(db)
        result = service.cleanup_old_backups(max_age_days)
        
        logger.info(f"Cleaned up old backups: {result['deleted_count']} deleted")
        return {'success': True, 'data': result}
    
    except Exception as e:
        logger.error(f"Failed to cleanup old backups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear", response_model=dict)
def clear_backups(days: int = 30, db: Session = Depends(get_db)):
    """
    Clear backup folders older than the given number of days (frontend alias
    for /cleanup-old)
    """
    return cleanup_old_backups(max_age_days=days, db=db)


@router.get("/stats", response_model=dict)
def get_cleanup_stats(db: Session = Depends(get_db)):
    """
    Get cleanup statistics
    
    Returns:
        Cleanup stats
    """
    try:
        service = CleanupService(db)
        stats = service.get_cleanup_stats()
        return {'success': True, 'data': stats}
    
    except Exception as e:
        logger.error(f"Failed to get cleanup stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
