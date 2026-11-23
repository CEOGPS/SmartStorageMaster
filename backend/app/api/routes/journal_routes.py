"""
Undo journal API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import logging

from ...db import get_db
from ...services.journal_service import JournalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/journal", tags=["journal"])


@router.get("", response_model=dict)
def list_operations(limit: int = 50, db: Session = Depends(get_db)):
    """Recent reversible operations, newest first"""
    return {'success': True, 'data': JournalService(db).list_operations(limit)}


@router.post("/{operation_id}/undo", response_model=dict)
def undo_operation(operation_id: str, db: Session = Depends(get_db)):
    """Reverse one operation. Items that cannot be safely restored are reported, not forced."""
    try:
        return {'success': True, 'data': JournalService(db).undo(operation_id)}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Undo failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
