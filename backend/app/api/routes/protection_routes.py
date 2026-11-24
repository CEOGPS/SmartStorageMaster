"""
Protected folders API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session
import logging

from ...db import get_db
from ...services.protection_service import ProtectionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/protection", tags=["protection"])


class ProtectRequest(BaseModel):
    path: str = Field(..., description="Folder to protect")
    note: Optional[str] = Field(None, description="Why it is protected")


@router.get("", response_model=dict)
def list_protected(db: Session = Depends(get_db)):
    """Built-in (system) rules and the folders you protected"""
    return {'success': True, 'data': ProtectionService(db).list()}


@router.post("", response_model=dict)
def add_protected(request: ProtectRequest, db: Session = Depends(get_db)):
    """Protect a folder: its files can no longer be moved, renamed, sorted or deleted"""
    try:
        return {'success': True, 'data': ProtectionService(db).add(request.path, request.note)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{protected_id}", response_model=dict)
def remove_protected(protected_id: str, db: Session = Depends(get_db)):
    """Stop protecting a folder you added. Built-in rules cannot be removed."""
    if not ProtectionService(db).remove(protected_id):
        raise HTTPException(status_code=404, detail="Not found (built-in rules cannot be removed)")
    return {'success': True, 'data': {'removed': protected_id}}
