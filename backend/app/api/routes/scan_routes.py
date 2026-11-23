"""
Scan API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import logging

from ...db import get_db
from ...services.scan_service import (
    ScanService,
    ScanConflictError,
    active_scans,
    cancel_scan,
)
from ...utils.path_utils import ScanPathError, describe_path, list_roots, list_subfolders
from ...api.schemas import ScanStartRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scan", tags=["scan"])


@router.post("/start", response_model=dict)
def start_scan(request: ScanStartRequest, db: Session = Depends(get_db)):
    """
    Start a file scan in a background thread.

    The path is normalized first (quotes stripped, ``D:`` -> ``D:\\``,
    ``~``/env vars expanded, real letter case). If the same folder is already
    being scanned, the running scan's id is returned instead of starting a
    second one; an overlapping folder returns 409.
    """
    compute_hashes = (
        request.compute_hash if request.compute_hash is not None else request.compute_hashes
    )
    service = ScanService(db, compute_hashes=compute_hashes)
    try:
        scan_id = service.start_scan_background(
            request.path,
            recursive=request.recursive,
            include_hidden=request.include_hidden,
        )
    except ScanPathError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (FileNotFoundError, NotADirectoryError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ScanConflictError as e:
        if e.same_path:
            return {
                'success': True,
                'scan_id': e.scan_id,
                'path': e.path,
                'already_running': True,
                'message': f'Already scanning {e.path} - showing that scan',
            }
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to start scan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e).split("\n")[0])

    path = (service.get_scan_status(scan_id) or {}).get('path', request.path)
    logger.info(f"Started scan {scan_id} for {path}")
    return {
        'success': True,
        'scan_id': scan_id,
        'path': path,
        'already_running': False,
        'message': f'Scan started for {path}',
    }


@router.post("/cancel/{scan_id}", response_model=dict)
def stop_scan(scan_id: str):
    """Stop a running scan after the current file; files indexed so far are kept."""
    if not cancel_scan(scan_id):
        raise HTTPException(status_code=404, detail="That scan is not running")
    return {'success': True, 'data': {'scan_id': scan_id, 'status': 'cancelling'}}


@router.get("/validate", response_model=dict)
def validate_path(path: str = Query("", description="Folder path as typed by the user")):
    """Normalized form of a path plus whether it can be scanned (for live input hints)."""
    return {'success': True, 'data': describe_path(path)}


@router.get("/roots", response_model=dict)
def get_roots():
    """Drives and common user folders for quick-pick buttons."""
    return {'success': True, 'data': list_roots()}


@router.get("/browse", response_model=dict)
def browse(path: str = "", include_hidden: bool = False):
    """Child folders of a directory (or the roots when path is empty) for the folder picker."""
    try:
        return {'success': True, 'data': list_subfolders(path, include_hidden=include_hidden)}
    except ScanPathError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/active", response_model=dict)
def get_active():
    """Scans currently running in this server process."""
    return {'success': True, 'data': active_scans()}


@router.get("/history", response_model=dict)
def get_history(limit: int = 8, db: Session = Depends(get_db)):
    """Most recent scans, newest first."""
    return {'success': True, 'data': ScanService(db).get_scan_history(limit)}


@router.get("/summary/{scan_id}", response_model=dict)
def get_summary(scan_id: str, top: int = 8, db: Session = Depends(get_db)):
    """Space used per file category and the largest files of a scan."""
    return {'success': True, 'data': ScanService(db).get_scan_summary(scan_id, top)}


@router.get("/status/{scan_id}", response_model=dict)
def get_scan_status(scan_id: str, db: Session = Depends(get_db)):
    try:
        status = ScanService(db).get_scan_status(scan_id)
        if not status:
            raise HTTPException(status_code=404, detail=f"Scan not found: {scan_id}")
        return {'success': True, 'data': status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scan status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files/{scan_id}", response_model=dict)
def get_scan_files(scan_id: str, limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    try:
        return {'success': True, 'data': ScanService(db).get_scan_files(scan_id, limit, offset)}
    except Exception as e:
        logger.error(f"Failed to get scan files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/storage-stats", response_model=dict)
def get_storage_stats(db: Session = Depends(get_db)):
    try:
        return {'success': True, 'data': ScanService(db).get_storage_stats()}
    except Exception as e:
        logger.error(f"Failed to get storage stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
