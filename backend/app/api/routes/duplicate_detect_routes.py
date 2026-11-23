"""
Duplicate detection API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import logging

from ...db import get_db
from ...services.duplicate_service import DuplicateService
from ...api.schemas import (
    DuplicateDetectRequest,
    DuplicateGroupsResponse,
    DuplicateStatsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/duplicates", tags=["duplicates"])


@router.post("/detect", response_model=dict)
def detect_duplicates(
    request: DuplicateDetectRequest,
    db: Session = Depends(get_db),
):
    """
    Detect duplicate files
    
    Args:
        request: Detection configuration
        db: Database session
    
    Returns:
        Duplicate detection result
    """
    try:
        service = DuplicateService(db)
        
        exact_groups = []
        image_groups = []
        
        if request.detect_exact:
            exact_groups = service.detect_exact_duplicates(request.scan_id)
        
        if request.detect_images:
            image_groups = service.detect_image_duplicates(
                request.scan_id,
                request.image_similarity,
            )
        
        logger.info(
            f"Detected {len(exact_groups)} exact and {len(image_groups)} image duplicates"
        )
        
        return {
            'success': True,
            'data': {
                'exact_groups': len(exact_groups),
                'image_groups': len(image_groups),
                'total_groups': len(exact_groups) + len(image_groups),
                'group_ids': exact_groups + image_groups,
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to detect duplicates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/groups", response_model=dict)
def get_duplicate_groups_latest(
    group_type: str = None,
    db: Session = Depends(get_db),
):
    """
    Get duplicate groups from latest scan
    
    Args:
        group_type: Filter by type (exact, phash, embedding)
        db: Database session
    
    Returns:
        List of duplicate groups
    """
    try:
        from ...db.models import ScanSession
        latest_scan = db.query(ScanSession)\
            .filter(ScanSession.status == "completed")\
            .order_by(ScanSession.completed_at.desc())\
            .first()
        
        if not latest_scan:
            return {
                'success': False,
                'error': 'No completed scans found',
                'data': None
            }
        
        service = DuplicateService(db)
        groups = service.get_duplicate_groups(latest_scan.id, group_type)
        
        return {
            'success': True,
            'data': {
                'groups': groups,
                'count': len(groups),
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get duplicate groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/groups/{scan_id}", response_model=dict)
def get_duplicate_groups(
    scan_id: str = None,
    group_type: str = None,
    db: Session = Depends(get_db),
):
    """
    Get duplicate groups
    
    Args:
        scan_id: Scan session ID (optional, uses latest if not provided)
        group_type: Filter by type (exact, phash, embedding)
        db: Database session
    
    Returns:
        List of duplicate groups
    """
    try:
        # If no scan_id provided, get the latest completed scan
        if not scan_id or scan_id == "latest":
            from ...db.models import ScanSession
            latest_scan = db.query(ScanSession)\
                .filter(ScanSession.status == "completed")\
                .order_by(ScanSession.completed_at.desc())\
                .first()
            
            if not latest_scan:
                return {
                    'success': False,
                    'error': 'No completed scans found',
                    'data': None
                }
            scan_id = latest_scan.id
        
        service = DuplicateService(db)
        groups = service.get_duplicate_groups(scan_id, group_type)
        
        return {
            'success': True,
            'data': {
                'groups': groups,
                'count': len(groups),
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get duplicate groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/{scan_id}", response_model=dict)
def get_duplicate_stats(scan_id: str, db: Session = Depends(get_db)):
    """
    Get duplicate detection statistics
    
    Args:
        scan_id: Scan session ID
        db: Database session
    
    Returns:
        Statistics
    """
    try:
        service = DuplicateService(db)
        stats = service.get_duplicate_stats(scan_id)
        return {'success': True, 'data': stats}
    
    except Exception as e:
        logger.error(f"Failed to get duplicate stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
