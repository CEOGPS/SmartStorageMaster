"""
FastAPI Duplicate API endpoints
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.connection import get_db
from ..db.models import DuplicateGroup, ScanSession
from ..services.duplicate_service import DuplicateService

router = APIRouter(prefix="/api/duplicates", tags=["duplicates"])


def _get_latest_scan_id(db: Session):
    """Return the ID of the most recent completed scan, or None."""
    scan = (
        db.query(ScanSession)
        .filter_by(status="completed")
        .order_by(ScanSession.completed_at.desc())
        .first()
    )
    return scan.id if scan else None


@router.get("/stats")
async def get_duplicate_stats(db=Depends(get_db)):
    """Duplicate statistics summary for the dashboard."""
    scan_id = _get_latest_scan_id(db)
    if not scan_id:
        return {
            "success": False,
            "data": None,
            "error": "No completed scans found",
        }

    service = DuplicateService(db)
    stats = service.get_duplicate_stats(scan_id)

    total_size = sum(
        g.total_size
        for g in db.query(DuplicateGroup).filter_by(scan_id=scan_id).all()
    )

    return {
        "success": True,
        "data": {
            "total_groups": stats["total_groups"],
            "total_duplicates": stats["total_duplicates"],
            "total_size": total_size,
            "savings_possible": stats["total_savings"],
            "by_type": stats["by_type"],
        },
        "error": None,
    }


@router.get("/savings")
async def get_duplicate_savings(db=Depends(get_db)):
    """Duplicate savings summary for the dashboard."""
    scan_id = _get_latest_scan_id(db)
    if not scan_id:
        return {
            "success": True,
            "data": {
                "total_savings": 0,
                "total_size": 0,
                "file_count": 0,
                "scan_id": None,
            },
            "error": None,
        }

    service = DuplicateService(db)
    stats = service.get_duplicate_stats(scan_id)

    return {
        "success": True,
        "data": {
            "total_savings": stats["total_savings"],
            "total_size": 0,
            "file_count": stats["total_duplicates"],
            "scan_id": scan_id,
        },
        "error": None,
    }


@router.get("/groups")
async def get_duplicate_groups(
    file_type: Optional[str] = None,
    db=Depends(get_db),
):
    """List duplicate groups for the latest scan."""
    scan_id = _get_latest_scan_id(db)
    if not scan_id:
        return {"success": False, "data": None, "error": "No completed scans found"}

    service = DuplicateService(db)
    if file_type is None:
        groups = service.get_duplicate_groups(scan_id)
    else:
        groups = service.get_duplicate_groups(scan_id, group_type=file_type)
    return {"success": True, "data": groups, "error": None}