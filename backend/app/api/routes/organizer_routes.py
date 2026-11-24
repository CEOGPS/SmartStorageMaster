"""
File organizer API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import logging

from ...db import get_db
from ...services.organizer_service import OrganizerService
from ...api.schemas import (
    OrganizerMoveRequest,
    OrganizerCreateFolderRequest,
    OrganizerDeleteEmptyFoldersRequest,
    OrganizerDeleteFilesRequest,
    OrganizerSortRequest,
    OrganizerRenameRequest,
)
from ...services.rename_service import RenameService, RenameError
from ...services.sort_service import SortService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/organizer", tags=["organizer"])


@router.get("/files", response_model=dict)
def list_files(
    folder: str = None,
    file_type: str = None,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    List indexed files, optionally filtered by folder and/or file type

    Args:
        folder: Only return files whose path starts with this folder
        file_type: Coarse category (image, document, video, audio, archive, other)
        limit: Number of files to return
        offset: Number of files to skip
        db: Database session

    Returns:
        Paginated list of files
    """
    try:
        service = OrganizerService(db)
        result = service.list_files(folder, file_type, limit, offset)
        return {'success': True, 'data': result}

    except Exception as e:
        logger.error(f"Failed to list organizer files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/thumbnail/{file_id}")
def get_thumbnail(file_id: str, db: Session = Depends(get_db)):
    """
    Stream an indexed file's raw bytes, for image/video thumbnail previews.
    Only files already present in the index can be served (no arbitrary path input).

    Args:
        file_id: Indexed file ID
        db: Database session

    Returns:
        The file's bytes
    """
    service = OrganizerService(db)
    path = service.get_file_path(file_id)
    if not path:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(path))


@router.get("/folders", response_model=dict)
def list_folders(db: Session = Depends(get_db)):
    """
    List distinct folders present in the files table

    Returns:
        Sorted list of folder paths
    """
    try:
        service = OrganizerService(db)
        result = service.list_folders()
        return {'success': True, 'data': result}

    except Exception as e:
        logger.error(f"Failed to list organizer folders: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-folder", response_model=dict)
def create_folder(
    request: OrganizerCreateFolderRequest,
    db: Session = Depends(get_db),
):
    """
    Create a folder on disk

    Args:
        request: Folder path to create
        db: Database session

    Returns:
        Result dictionary
    """
    try:
        service = OrganizerService(db)
        result = service.create_folder(request.path)

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        return {'success': True, 'data': result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create folder: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/move", response_model=dict)
def move_files(
    request: OrganizerMoveRequest,
    db: Session = Depends(get_db),
):
    """
    Move files to a destination folder

    Args:
        request: File IDs, destination, and create_if_missing flag
        db: Database session

    Returns:
        Result dictionary with moved/failed/total counts
    """
    try:
        service = OrganizerService(db)
        result = service.move_files(
            request.file_ids, request.destination, request.create_if_missing
        )

        logger.info(f"Moved {result['moved']}/{result['total']} files to {request.destination}")
        return {'success': True, 'data': result}

    except Exception as e:
        logger.error(f"Failed to move files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delete-empty-folders", response_model=dict)
def delete_empty_folders(
    request: OrganizerDeleteEmptyFoldersRequest,
    db: Session = Depends(get_db),
):
    """
    Remove empty subfolders under a root directory

    Args:
        request: Root directory to clean up under
        db: Database session

    Returns:
        Result dictionary with removed folders and count
    """
    try:
        service = OrganizerService(db)
        result = service.delete_empty_folders(request.root)

        logger.info(f"Removed {result['count']} empty folders under {request.root}")
        return {'success': True, 'data': result}

    except Exception as e:
        logger.error(f"Failed to delete empty folders: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delete-files", response_model=dict)
def delete_files(
    request: OrganizerDeleteFilesRequest,
    db: Session = Depends(get_db),
):
    """
    Back up and delete files, via the same backup-before-delete path as cleanup

    Args:
        request: File IDs to delete
        db: Database session

    Returns:
        Result dictionary
    """
    try:
        service = OrganizerService(db)
        result = service.delete_files_with_backup(request.file_ids)

        logger.info(f"Deleted {result['deleted']}/{result['total']} files (organizer)")
        return {'success': True, 'data': result}

    except Exception as e:
        logger.error(f"Failed to delete files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _run_sort(request: OrganizerSortRequest, db: Session, apply: bool) -> dict:
    try:
        service = SortService(db)
        fn = service.apply if apply else service.plan
        result = fn(request.source, request.mode, request.granularity,
                    request.recursive, request.destination)
        if not apply:
            result = {k: v for k, v in result.items() if k != 'moves'}
        return {'success': True, 'data': result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Sort failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sort/preview", response_model=dict)
def preview_sort(request: OrganizerSortRequest, db: Session = Depends(get_db)):
    """Show what an auto-sort would move, without touching any file"""
    return _run_sort(request, db, apply=False)


@router.post("/sort/apply", response_model=dict)
def apply_sort(request: OrganizerSortRequest, db: Session = Depends(get_db)):
    """Apply an auto-sort. Returns an operation_id that can be undone via /api/journal."""
    return _run_sort(request, db, apply=True)


def _run_rename(request: OrganizerRenameRequest, db: Session, apply: bool) -> dict:
    try:
        service = RenameService(db)
        opts = request.model_dump() if hasattr(request, 'model_dump') else request.dict()
        result = service.apply(**opts) if apply else service.plan(**opts)
        if not apply:
            result = {k: v for k, v in result.items() if k != 'items'}
        return {'success': True, 'data': result}
    except RenameError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Rename failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rename/preview", response_model=dict)
def preview_rename(request: OrganizerRenameRequest, db: Session = Depends(get_db)):
    """Show old -> new names, conflicts and errors without renaming anything"""
    return _run_rename(request, db, apply=False)


@router.post("/rename/apply", response_model=dict)
def apply_rename(request: OrganizerRenameRequest, db: Session = Depends(get_db)):
    """Rename files. Returns an operation_id that can be undone via /api/journal."""
    return _run_rename(request, db, apply=True)
