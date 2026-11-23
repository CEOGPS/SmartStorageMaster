"""
Scan API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pathlib import Path
import logging

from ...db import get_db
from ...services.scan_service import ScanService
from ...api.schemas import (
    ScanStartRequest,
    ScanStatusResponse,
    ScanFilesResponse,
    StorageStatsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scan", tags=["scan"])


@router.post("/start", response_model=dict)
def start_scan(
    request: ScanStartRequest,
    db: Session = Depends(get_db),
):
    """
    Start a file scan in a background thread

    Returns as soon as the scan is registered. Poll /api/scan/status/{scan_id}
    or connect to /ws/scan?scan_id=... for live progress.

    Args:
        request: Scan configuration
        db: Database session

    Returns:
        Scan session ID
    """
    try:
        path = Path(request.path).expanduser()
        if not path.exists():
            raise HTTPException(status_code=400, detail=f"Path does not exist: {path}")

        if not path.is_dir():
            raise HTTPException(status_code=400, detail=f"Path is not a directory: {path}")

        compute_hashes = (
            request.compute_hash if request.compute_hash is not None else request.compute_hashes
        )
        service = ScanService(db, compute_hashes=compute_hashes)
        scan_id = service.start_scan_background(
            path,
            recursive=request.recursive,
            include_hidden=request.include_hidden,
        )

        logger.info(f"Started scan {scan_id}")

        return {
            'success': True,
            'scan_id': scan_id,
            'message': f'Scan started for {path}',
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start scan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{scan_id}", response_model=dict)
def get_scan_status(scan_id: str, db: Session = Depends(get_db)):
    """
    Get scan status
    
    Args:
        scan_id: Scan session ID
        db: Database session
    
    Returns:
        Scan status information
    """
    try:
        service = ScanService(db)
        status = service.get_scan_status(scan_id)
        
        if not status:
            raise HTTPException(status_code=404, detail=f"Scan not found: {scan_id}")
        
        return {'success': True, 'data': status}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scan status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files/{scan_id}", response_model=dict)
def get_scan_files(
    scan_id: str,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    Get files from scan
    
    Args:
        scan_id: Scan session ID
        limit: Number of files to return
        offset: Number of files to skip
        db: Database session
    
    Returns:
        List of files
    """
    try:
        service = ScanService(db)
        files = service.get_scan_files(scan_id, limit, offset)
        return {'success': True, 'data': files}
    
    except Exception as e:
        logger.error(f"Failed to get scan files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/storage-stats", response_model=dict)
def get_storage_stats(db: Session = Depends(get_db)):
    """
    Get storage statistics
    
    Returns:
        Storage stats
    """
    try:
        service = ScanService(db)
        stats = service.get_storage_stats()
        return {'success': True, 'data': stats}
    
    except Exception as e:
        logger.error(f"Failed to get storage stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
