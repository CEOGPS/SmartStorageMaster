"""
Organizer service - browse, move, and tidy up indexed files on disk
"""
from pathlib import Path
from typing import List, Dict, Optional
import logging
import os
import shutil

from sqlalchemy.orm import Session

from ..db.models import File
from .cleanup_service import CleanupService

logger = logging.getLogger(__name__)

# Coarse file-type categories derived from mime type / extension, used to
# filter the organizer's file list.
_EXTENSION_CATEGORIES = {
    'image': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.heic', '.tiff', '.tif'},
    'document': {'.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.xls', '.xlsx', '.ppt', '.pptx', '.csv'},
    'video': {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v'},
    'audio': {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma'},
    'archive': {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'},
}


def _categorize(mime_type: Optional[str], name: str) -> str:
    """Map a file's mime type / extension to a coarse category"""
    if mime_type:
        if mime_type.startswith('image/'):
            return 'image'
        if mime_type.startswith('video/'):
            return 'video'
        if mime_type.startswith('audio/'):
            return 'audio'
        if mime_type == 'application/pdf' or mime_type.startswith('text/') or \
                'msword' in mime_type or 'officedocument' in mime_type or 'spreadsheet' in mime_type or \
                'presentation' in mime_type:
            return 'document'
        if 'zip' in mime_type or 'compressed' in mime_type or 'archive' in mime_type:
            return 'archive'

    suffix = Path(name).suffix.lower()
    for category, extensions in _EXTENSION_CATEGORIES.items():
        if suffix in extensions:
            return category

    return 'other'


class OrganizerService:
    """Service for browsing, filtering, and moving indexed files"""

    def __init__(self, db_session: Session):
        """
        Initialize organizer service

        Args:
            db_session: SQLAlchemy session
        """
        self.db = db_session

    def list_files(
        self,
        folder: str = None,
        file_type: str = None,
        limit: int = 200,
        offset: int = 0,
    ) -> Dict:
        """
        List indexed files, optionally filtered by folder and/or coarse file type

        Args:
            folder: Only return files whose path starts with this folder
            file_type: Coarse category (image, document, video, audio, archive, other)
            limit: Number of files to return
            offset: Number of files to skip

        Returns:
            Dictionary with total count and paginated files list
        """
        query = self.db.query(File)

        if folder:
            normalized = str(Path(folder))
            query = query.filter(File.path.like(f"{normalized}%"))

        rows = query.all()

        if file_type and file_type != 'all':
            rows = [f for f in rows if _categorize(f.mime_type, f.name) == file_type]

        total = len(rows)
        page = rows[offset:offset + limit]

        return {
            'total': total,
            'limit': limit,
            'offset': offset,
            'files': [
                {
                    'id': f.id,
                    'path': f.path,
                    'name': f.name,
                    'size': f.size,
                    'mime_type': f.mime_type,
                }
                for f in page
            ],
        }

    def get_file_path(self, file_id: str) -> Optional[Path]:
        """
        Resolve a file's on-disk path by its indexed ID, for safe thumbnail/content serving

        Args:
            file_id: Indexed file ID

        Returns:
            Path if the file is indexed and exists on disk, else None
        """
        file_record = self.db.query(File).filter_by(id=file_id).first()
        if not file_record:
            return None
        path = Path(file_record.path)
        return path if path.exists() else None

    def list_folders(self) -> Dict:
        """
        List distinct parent folders present in the files table

        Returns:
            Dictionary with sorted list of folder paths
        """
        folders = set()
        for (path,) in self.db.query(File.path).all():
            parent = str(Path(path).parent)
            folders.add(parent)

        return {'folders': sorted(folders)}

    def create_folder(self, path: str) -> Dict:
        """
        Create a folder on disk (and any missing parents)

        Args:
            path: Folder path to create

        Returns:
            Result dictionary
        """
        try:
            target = Path(path)
            target.mkdir(parents=True, exist_ok=True)
            return {'success': True, 'path': str(target)}
        except Exception as e:
            logger.error(f"Failed to create folder {path}: {e}")
            return {'success': False, 'error': str(e)}

    def move_files(
        self,
        file_ids: List[str],
        destination: str,
        create_if_missing: bool = True,
    ) -> Dict:
        """
        Move indexed files to a destination folder, updating their DB records

        Args:
            file_ids: File IDs to move
            destination: Destination folder path
            create_if_missing: Create the destination folder if it doesn't exist

        Returns:
            Result dictionary with moved/failed/total counts
        """
        logger.info(f"Moving {len(file_ids)} files to {destination}")

        dest_folder = Path(destination)
        moved = 0
        failed = 0

        if not dest_folder.exists():
            if create_if_missing:
                try:
                    dest_folder.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    logger.error(f"Failed to create destination {destination}: {e}")
                    return {'moved': 0, 'failed': len(file_ids), 'total': len(file_ids)}
            else:
                logger.warning(f"Destination does not exist and create_if_missing=False: {destination}")
                return {'moved': 0, 'failed': len(file_ids), 'total': len(file_ids)}

        for file_id in file_ids:
            file_record = self.db.query(File).filter_by(id=file_id).first()
            if not file_record:
                failed += 1
                continue

            try:
                source_path = Path(file_record.path)
                if not source_path.exists():
                    logger.warning(f"File not found on disk: {source_path}")
                    failed += 1
                    continue

                dest_path = dest_folder / source_path.name
                if dest_path.exists() and dest_path.resolve() != source_path.resolve():
                    stem, suffix = dest_path.stem, dest_path.suffix
                    counter = 1
                    while dest_path.exists():
                        dest_path = dest_folder / f"{stem} ({counter}){suffix}"
                        counter += 1

                shutil.move(str(source_path), str(dest_path))

                file_record.path = str(dest_path)
                file_record.name = dest_path.name
                moved += 1

            except Exception as e:
                logger.error(f"Failed to move file {file_id}: {e}")
                failed += 1

        self.db.commit()

        return {'moved': moved, 'failed': failed, 'total': len(file_ids)}

    def delete_empty_folders(self, root: str) -> Dict:
        """
        Remove empty subfolders under root (root itself is never removed)

        Args:
            root: Root directory to clean up under

        Returns:
            Dictionary with list of removed paths and count
        """
        logger.info(f"Cleaning up empty folders under {root}")

        removed = []
        root_resolved = str(Path(root).resolve())

        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            if str(Path(dirpath).resolve()) == root_resolved:
                continue

            try:
                if not dirnames and not filenames:
                    os.rmdir(dirpath)
                    removed.append(dirpath)
            except PermissionError as e:
                logger.warning(f"Permission denied removing {dirpath}: {e}")
                continue
            except OSError as e:
                logger.warning(f"Failed to remove {dirpath}: {e}")
                continue

        return {'removed': removed, 'count': len(removed)}

    def delete_files_with_backup(self, file_ids: List[str]) -> Dict:
        """
        Back up then delete files, routing through CleanupService so organizer
        deletes go through the same backup-before-delete safety path as the
        rest of the app.

        Args:
            file_ids: File IDs to delete

        Returns:
            Merged result dictionary with backed_up/deleted/failed/total counts
        """
        cleanup_service = CleanupService(self.db)
        backup_result = cleanup_service.backup_files(file_ids)
        delete_result = cleanup_service.delete_files(file_ids)

        return {
            'backed_up': backup_result['backed_up'],
            'deleted': delete_result['deleted'],
            'failed': backup_result['failed'] + delete_result['failed'],
            'total': len(file_ids),
        }
