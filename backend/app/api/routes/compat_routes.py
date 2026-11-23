"""Compatibility routes for frontend expectations

Expose a couple of top-level `/api/...` endpoints the frontend expects
that live under different router prefixes (backwards-compatibility).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import logging

from ...db import get_db
from ...services.scan_service import ScanService
from ...services.duplicate_service import DuplicateService
from ...services.cleanup_service import CleanupService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["compat"])


@router.get("/storage/stats", response_model=dict)
def storage_stats_compat(db: Session = Depends(get_db)):
    """Compatibility endpoint for `/api/storage/stats` used by frontend."""
    try:
        service = ScanService(db)
        stats = service.get_storage_stats()
        return {"success": True, "data": stats}
    except Exception as e:
        logger.error(f"Failed to get storage stats (compat): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/duplicates/stats", response_model=dict)
def duplicates_stats_compat(db: Session = Depends(get_db)):
    """Compatibility endpoint for `/api/duplicates/stats` used by frontend."""
    try:
        # Use latest completed scan
        from ...db.models import ScanSession
        latest = db.query(ScanSession)\
            .filter(ScanSession.status == "completed")\
            .order_by(ScanSession.completed_at.desc())\
            .first()

        if not latest:
            return {"success": True, "data": {"stats": {}, "scan_id": None}}

        service = DuplicateService(db)
        stats = service.get_duplicate_stats(latest.id)
        return {"success": True, "data": stats}
    except Exception as e:
        logger.error(f"Failed to get duplicate stats (compat): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cleanup/backups", response_model=dict)
def cleanup_backups_compat(db: Session = Depends(get_db)):
    """Compatibility endpoint for `/api/cleanup/backups` used by frontend."""
    try:
        service = CleanupService(db)
        backups = service.get_backups()
        return {"success": True, "data": {"backups": backups, "count": len(backups)}}
    except Exception as e:
        logger.error(f"Failed to get backups (compat): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
