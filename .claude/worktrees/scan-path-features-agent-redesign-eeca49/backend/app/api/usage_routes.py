"""
REST API routes for file usage analysis and cleanup recommendations

Endpoints:
- GET /api/usage/summary - Usage statistics by category
- GET /api/usage/files?category=NOT_USED - Get files by category
- GET /api/usage/recommendations - Cleanup recommendations
- GET /api/usage/file/{file_id} - File usage details
- PUT /api/usage/thresholds - Update configuration thresholds
- GET /api/usage/thresholds - Get current thresholds
"""
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional, List
import logging

from app.services.usage_service import UsageService
from app.db.connection import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/usage", tags=["usage"])


def get_usage_service(db_session=Depends(get_db)) -> UsageService:
    """Dependency to get usage service instance"""
    return UsageService(db_session=db_session)


@router.get("/summary")
def get_usage_summary(service: UsageService = Depends(get_usage_service)):
    """
    Get summary of file usage statistics
    
    Returns summary of file counts and storage by usage category
    
    **Response:**
    ```json
    {
        "summary": {
            "RECENTLY_USED": {"count": 150, "total_size_mb": 2500.0},
            "RARELY_USED": {"count": 45, "total_size_mb": 850.0},
            "NOT_USED": {"count": 23, "total_size_mb": 1200.0}
        },
        "total_files": 218,
        "total_size_mb": 4550.0,
        "potential_cleanup_mb": 1200.0,
        "thresholds": {
            "recently_used_days": 30,
            "rarely_used_days": 180,
            "not_used_days": 180,
            "min_priority_size_mb": 100
        }
    }
    ```
    """
    try:
        return service.get_usage_summary()
    except Exception as e:
        logger.error(f"Error getting usage summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files")
def get_files_by_category(
    category: str = Query(..., description="Usage category: RECENTLY_USED, RARELY_USED, or NOT_USED"),
    limit: Optional[int] = Query(None, description="Maximum results"),
    min_priority: float = Query(0.0, ge=0.0, le=1.0, description="Minimum priority score"),
    service: UsageService = Depends(get_usage_service),
):
    """
    Get files filtered by usage category
    
    **Query Parameters:**
    - `category` (required): RECENTLY_USED, RARELY_USED, or NOT_USED
    - `limit`: Maximum number of results (optional)
    - `min_priority`: Minimum priority score 0.0-1.0 (default: 0.0)
    
    **Response:**
    ```json
    [
        {
            "id": "file-id-1",
            "path": "/path/to/file.txt",
            "name": "file.txt",
            "size_mb": 250.5,
            "usage_category": "NOT_USED",
            "usage_priority": 0.85,
            "days_since_access": 365,
            "last_accessed": "2024-01-19T10:30:00",
            "modified_at": "2024-01-19T10:30:00"
        }
    ]
    ```
    """
    try:
        # Validate category
        valid_categories = ["RECENTLY_USED", "RARELY_USED", "NOT_USED"]
        if category not in valid_categories:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category. Must be one of: {', '.join(valid_categories)}"
            )
        
        files = service.get_files_by_category(
            category=category,
            limit=limit,
            min_priority=min_priority,
        )
        return files
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching files by category: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recommendations")
def get_cleanup_recommendations(
    limit: int = Query(100, ge=1, le=10000, description="Maximum recommendations"),
    min_priority: float = Query(0.7, ge=0.0, le=1.0, description="Minimum priority threshold"),
    service: UsageService = Depends(get_usage_service),
):
    """
    Get prioritized cleanup recommendations
    
    Returns files sorted by cleanup priority, focusing on rarely-used and not-used files
    
    **Query Parameters:**
    - `limit`: Maximum results (default: 100, max: 10000)
    - `min_priority`: Minimum priority score 0.0-1.0 (default: 0.7)
    
    **Response:**
    ```json
    [
        {
            "id": "file-id-1",
            "path": "/path/to/unused_file.iso",
            "name": "unused_file.iso",
            "size_mb": 4500.0,
            "usage_category": "NOT_USED",
            "priority": 0.95,
            "reason": "Not accessed for 400 days, Large file",
            "last_accessed": "2023-01-15T10:30:00"
        }
    ]
    ```
    """
    try:
        if min_priority < 0.0 or min_priority > 1.0:
            raise HTTPException(
                status_code=400,
                detail="min_priority must be between 0.0 and 1.0"
            )
        
        recommendations = service.get_cleanup_recommendations(
            limit=limit,
            min_priority=min_priority,
        )
        
        return {
            "count": len(recommendations),
            "total_potential_cleanup_mb": round(
                sum(r["size_mb"] for r in recommendations),
                2
            ),
            "recommendations": recommendations,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting cleanup recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/file/{file_id}")
def get_file_usage_details(
    file_id: str,
    service: UsageService = Depends(get_usage_service),
):
    """
    Get detailed usage information for a specific file
    
    **Path Parameters:**
    - `file_id`: File identifier
    
    **Response:**
    ```json
    {
        "id": "file-id-1",
        "path": "/path/to/file.txt",
        "name": "file.txt",
        "size_mb": 250.5,
        "created_at": "2023-01-15T10:30:00",
        "modified_at": "2024-01-19T10:30:00",
        "last_accessed": "2024-01-19T10:30:00",
        "days_since_access": 0,
        "usage_category": "RECENTLY_USED",
        "usage_priority": 0.1
    }
    ```
    """
    try:
        details = service.get_file_usage_details(file_id)
        if not details:
            raise HTTPException(
                status_code=404,
                detail=f"File not found: {file_id}"
            )
        return details
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching file usage details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/thresholds")
def get_thresholds(service: UsageService = Depends(get_usage_service)):
    """
    Get current usage categorization thresholds
    
    **Response:**
    ```json
    {
        "recently_used_days": 30,
        "rarely_used_days": 180,
        "not_used_days": 180,
        "min_priority_size_mb": 100
    }
    ```
    """
    try:
        return service.get_thresholds()
    except Exception as e:
        logger.error(f"Error fetching thresholds: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/thresholds")
def update_thresholds(
    recently_used_days: Optional[int] = Query(None, ge=1, le=365),
    rarely_used_days: Optional[int] = Query(None, ge=1, le=1825),
    not_used_days: Optional[int] = Query(None, ge=1, le=1825),
    min_priority_size_mb: Optional[int] = Query(None, ge=1, le=100000),
    service: UsageService = Depends(get_usage_service),
):
    """
    Update usage categorization thresholds
    
    All parameters are optional. Only provided parameters will be updated.
    
    **Query Parameters:**
    - `recently_used_days`: Days to consider a file "recently used" (1-365)
    - `rarely_used_days`: Days to consider a file "rarely used" (1-1825)
    - `not_used_days`: Days to consider a file "not used" (1-1825)
    - `min_priority_size_mb`: Minimum file size (MB) for high cleanup priority (1-100000)
    
    **Example:**
    ```
    PUT /api/usage/thresholds?recently_used_days=14&rarely_used_days=90&not_used_days=180
    ```
    
    **Response:**
    ```json
    {
        "recently_used_days": 14,
        "rarely_used_days": 90,
        "not_used_days": 180,
        "min_priority_size_mb": 100
    }
    ```
    """
    try:
        # Validate consistency
        thresholds = {
            "recently_used_days": recently_used_days,
            "rarely_used_days": rarely_used_days,
            "not_used_days": not_used_days,
        }
        
        # Get current values to check those not being updated
        current = service.get_thresholds()
        new_recently = recently_used_days or current["recently_used_days"]
        new_rarely = rarely_used_days or current["rarely_used_days"]
        new_not_used = not_used_days or current["not_used_days"]
        
        # Validate thresholds are in ascending order
        if new_recently > new_rarely:
            raise HTTPException(
                status_code=400,
                detail="recently_used_days must be <= rarely_used_days"
            )
        if new_rarely > new_not_used:
            raise HTTPException(
                status_code=400,
                detail="rarely_used_days must be <= not_used_days"
            )
        
        updated = service.update_thresholds(
            recently_used_days=recently_used_days,
            rarely_used_days=rarely_used_days,
            not_used_days=not_used_days,
            min_priority_size_mb=min_priority_size_mb,
        )
        
        return {
            "status": "success",
            "thresholds": updated,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating thresholds: {e}")
        raise HTTPException(status_code=500, detail=str(e))
