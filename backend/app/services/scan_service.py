"""
Scan service - orchestrates file scanning and database persistence
"""
from pathlib import Path
from typing import Optional, Dict
import logging
import itertools
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from sqlalchemy.orm import Session

from ..core.scanner import FileScanner, EXCLUDED_DIRS, EXCLUDED_EXTENSIONS
from ..db.models import File, ScanSession
from ..db.connection import get_session
from ..utils.file_utils import get_file_size
from .usage_service import UsageService
from .duplicate_service import DuplicateService

logger = logging.getLogger(__name__)

# Live progress for scans running in background threads, keyed by scan id.
# Read by the status endpoint and the /ws/scan WebSocket while a scan runs.
_progress: Dict[str, dict] = {}
_progress_lock = threading.Lock()


LOOKUP_CHUNK = 500
# Parallel file reads while hashing. Reads are I/O bound and BLAKE3 releases the GIL.
# Override with SSM_HASH_WORKERS (use 1 for a spinning disk or a network share).
HASH_WORKERS = max(1, int(os.getenv('SSM_HASH_WORKERS', '4') or 4))
_MTIME_TOLERANCE_S = 0.002
_BARE_DRIVE = re.compile(r'^[A-Za-z]:$')


def normalize_scan_path(path) -> Path:
    """
    Turn a bare Windows drive ("D:") into its root ("D:\\").

    Path("D:") / "x" yields "D:x" (drive-relative, no separator), which never
    matches paths stored by earlier scans and collides on files.path.
    """
    text = str(path).strip()
    if _BARE_DRIVE.match(text):
        text += '\\'
    return Path(text)


def get_live_progress(scan_id: str) -> Optional[dict]:
    """Return a copy of the in-memory progress for a scan, or None if not tracked"""
    with _progress_lock:
        info = _progress.get(scan_id)
        return dict(info) if info else None


def _set_progress(scan_id: str, **fields) -> None:
    with _progress_lock:
        _progress.setdefault(scan_id, {}).update(fields)


class ScanService:
    """Service for managing file scans"""

    def __init__(self, db_session: Session, compute_hashes: bool = True):
        """
        Initialize scan service

        Args:
            db_session: SQLAlchemy session
            compute_hashes: Compute a BLAKE3 content hash for each file
        """
        self.db = db_session
        self.compute_hashes = compute_hashes
        # Hashing is done by this service (after deciding which files need it),
        # so the scanner itself only collects metadata.
        self.scanner = FileScanner(compute_hashes=False)

    def create_scan(self, start_path: Path) -> str:
        """
        Create a running scan session row and return its ID

        Args:
            start_path: Root directory to scan
        """
        scan_session = ScanSession(
            start_path=str(start_path),
            status="running",
        )
        self.db.add(scan_session)
        self.db.commit()
        _set_progress(
            scan_session.id,
            status="running",
            files_found=0,
            total_size=0,
            current_file="",
            current_folder="",
            percentage=0,
            total_estimated=0,
            potential_savings=0,
            error_message=None,
        )
        return scan_session.id

    def start_scan_background(
        self,
        start_path: Path,
        recursive: bool = True,
        include_hidden: bool = False,
    ) -> str:
        """
        Create a scan session and run the scan in a background thread

        The thread opens its own database session, so the caller's session
        can be closed as soon as this returns.

        Returns:
            Scan session ID
        """
        start_path = normalize_scan_path(start_path)
        scan_id = self.create_scan(start_path)
        compute_hashes = self.compute_hashes

        def worker():
            worker_db = get_session()
            try:
                ScanService(worker_db, compute_hashes=compute_hashes).run_scan(
                    scan_id, start_path, recursive, include_hidden
                )
            finally:
                worker_db.close()

        threading.Thread(target=worker, name=f"scan-{scan_id}", daemon=True).start()
        logger.info(f"Scan {scan_id} started in background for: {start_path}")
        return scan_id

    def start_scan(
        self,
        start_path: Path,
        recursive: bool = True,
        include_hidden: bool = False,
    ) -> str:
        """
        Run a file scan synchronously and store results in database

        Returns:
            Scan session ID
        """
        start_path = normalize_scan_path(start_path)
        scan_id = self.create_scan(start_path)
        self.run_scan(scan_id, start_path, recursive, include_hidden)
        return scan_id

    def _survey(self, start_path: Path, recursive: bool):
        """
        Pre-pass using the scanner's own traversal (stat only, no hashing).

        Returns ``(file_count, {size: how_many_files})``. The count drives the
        progress bar; the size table lets the scan skip hashing files whose size is
        unique (they cannot be duplicates of anything in this scan). Any failure is
        reported to the caller, which then hashes everything.
        """
        counts: Dict[int, int] = {}
        total = 0
        for size in self.scanner.scan_sizes(start_path, recursive):
            total += 1
            counts[size] = counts.get(size, 0) + 1
        return total, counts

    @staticmethod
    def _attach_hashes(chunk, paths, found, size_counts, scheme, stats, pool) -> None:
        """
        Fill in content hashes for one chunk of scanned files, reading as little as possible:

          reuse   - file unchanged since the last scan (same size and modified time) and
                    already hashed with the current scheme: copy the stored hash
          skip    - its size is unique in this scan, so it cannot be a duplicate
          hash    - everything else, read in parallel

        Hashes of files that changed are never carried over.
        """
        to_hash = []
        for m, path_str in zip(chunk, paths):
            old = found.get(path_str)
            stored = None
            if old is not None and old.size == m.size and old.modified_at is not None \
                    and abs((old.modified_at - m.modified_at).total_seconds()) <= _MTIME_TOLERANCE_S:
                stored = old.hash_blake3 if scheme == 'blake3' else old.hash_md5
            if stored:
                m.hash_blake3, m.hash_md5 = old.hash_blake3, old.hash_md5
                stats['reused'] += 1
            elif size_counts is not None and size_counts.get(m.size, 2) <= 1:
                stats['skipped_unique'] += 1
            else:
                to_hash.append(m)
        if to_hash:
            for m, (b3, md5) in zip(to_hash, pool.map(lambda x: FileScanner.content_hashes(x.path), to_hash)):
                m.hash_blake3, m.hash_md5 = b3, md5
            stats['hashed'] += len(to_hash)

    def run_scan(
        self,
        scan_id: str,
        start_path: Path,
        recursive: bool = True,
        include_hidden: bool = False,
    ) -> None:
        """
        Walk a directory and store/refresh a File record for every file found

        A path that an earlier scan already indexed is updated in place (moved
        to this scan) instead of inserted again, because files.path is unique.
        Errors are recorded on the scan session; they are not re-raised.
        """
        start_path = normalize_scan_path(start_path)
        logger.info(f"Running scan {scan_id} for path: {start_path}")

        try:
            self.scanner.include_hidden = include_hidden
            now = datetime.utcnow()

            try:
                total_estimated, size_counts = self._survey(start_path, recursive)
            except Exception as e:
                logger.warning(f"Pre-scan failed for scan {scan_id}, hashing every file: {e}")
                total_estimated, size_counts = 0, None
            _set_progress(scan_id, total_estimated=total_estimated)
            stats = {'hashed': 0, 'reused': 0, 'skipped_unique': 0}
            scheme = FileScanner.hash_scheme()

            total_files = 0
            total_size = 0
            scanned_paths = []
            seen_hashes: Dict[str, int] = {}
            potential_savings = 0

            def batches():
                it = iter(self.scanner.scan(start_path, recursive))
                while True:
                    chunk = list(itertools.islice(it, LOOKUP_CHUNK))
                    if not chunk:
                        return
                    yield chunk

            def records():
                # Look up existing rows by exact path, one chunk at a time, so
                # lookups never depend on how the root path was spelled.
                with ThreadPoolExecutor(max_workers=HASH_WORKERS) as pool:
                    for chunk in batches():
                        self.db.flush()  # sessions use autoflush=False
                        paths = [str(m.path) for m in chunk]
                        found = {
                            f.path: f
                            for f in self.db.query(File).filter(File.path.in_(paths)).all()
                        }
                        if self.compute_hashes:
                            self._attach_hashes(chunk, paths, found, size_counts, scheme, stats, pool)
                        for m, path_str in zip(chunk, paths):
                            yield m, path_str, found.get(path_str)

            for metadata, path_str, file_record in records():
                if file_record is None:
                    file_record = File(path=path_str)
                    self.db.add(file_record)

                file_record.scan_id = scan_id
                file_record.name = metadata.name
                file_record.size = metadata.size
                file_record.mime_type = metadata.mime_type
                file_record.hash_md5 = metadata.hash_md5
                file_record.hash_blake3 = metadata.hash_blake3
                file_record.hash_sha256 = metadata.hash_sha256
                file_record.created_at = metadata.created_at
                file_record.modified_at = metadata.modified_at
                file_record.indexed_at = now

                total_files += 1
                total_size += metadata.size
                scanned_paths.append(metadata.path)

                # Running count of recoverable space: every repeat of a hash
                # (only populated when compute_hashes is on) is an extra copy
                content_hash = metadata.hash_blake3 or metadata.hash_md5
                if content_hash:
                    if content_hash in seen_hashes:
                        potential_savings += metadata.size
                    else:
                        seen_hashes[content_hash] = metadata.size

                percentage = (
                    min(99, round(total_files / total_estimated * 100))
                    if total_estimated > 0 else 0
                )

                _set_progress(
                    scan_id,
                    files_found=total_files,
                    total_size=total_size,
                    current_file=metadata.name,
                    current_folder=str(metadata.path.parent),
                    percentage=percentage,
                    potential_savings=potential_savings,
                )

                # Batch commit
                if total_files % 500 == 0:
                    self.db.commit()

            scan_session = self.db.query(ScanSession).filter_by(id=scan_id).one()
            scan_session.status = "completed"
            scan_session.total_files = total_files
            scan_session.total_size = total_size
            scan_session.completed_at = datetime.utcnow()
            self.db.commit()

            _set_progress(scan_id, status="completed", percentage=100, **{f'hash_{k}': v for k, v in stats.items()})
            logger.info(
                f"Scan {scan_id} completed: {total_files} files, {total_size} bytes "
                f"(hashed {stats['hashed']}, reused {stats['reused']}, "
                f"skipped {stats['skipped_unique']} unique-size)"
            )

            # Usage analysis runs only after the file records are stored
            try:
                usage_service = UsageService(self.db)
                batch_size = 1000
                for i in range(0, len(scanned_paths), batch_size):
                    usage_service.batch_update_usage(scanned_paths[i:i + batch_size])
            except Exception as ue:
                logger.warning(f"Usage analysis post-scan failed: {ue}")

            # Duplicate detection runs automatically so results are ready
            # as soon as the scan finishes, without a separate manual step
            try:
                dup_service = DuplicateService(self.db)
                exact_groups = dup_service.detect_exact_duplicates(scan_id)
                image_groups = dup_service.detect_image_duplicates(scan_id)
                logger.info(
                    f"Scan {scan_id}: {len(exact_groups)} exact and "
                    f"{len(image_groups)} similar-image duplicate groups found"
                )
            except Exception as de:
                logger.warning(f"Duplicate detection post-scan failed: {de}")

        except Exception as e:
            logger.error(f"Scan {scan_id} failed: {e}", exc_info=True)
            self.db.rollback()
            scan_session = self.db.query(ScanSession).filter_by(id=scan_id).first()
            if scan_session:
                scan_session.status = "failed"
                scan_session.error_message = str(e)
                scan_session.completed_at = datetime.utcnow()
                self.db.commit()
            _set_progress(scan_id, status="failed", error_message=str(e))

    def get_progress_snapshot(self, scan_id: str) -> Optional[dict]:
        """
        Progress for a scan: live values while it runs, otherwise the stored session
        """
        live = get_live_progress(scan_id)
        if live and live.get("status") == "running":
            live.setdefault("total_estimated", 0)
            live.setdefault("potential_savings", 0)
            return live

        scan = self.db.query(ScanSession).filter_by(id=scan_id).first()
        if not scan:
            return None
        return {
            "status": scan.status,
            "files_found": scan.total_files,
            "total_size": scan.total_size,
            "current_file": "",
            "current_folder": "",
            "percentage": 100 if scan.status == "completed" else 0,
            "error_message": scan.error_message,
            # Historical (DB-fallback) snapshot: live-only figures reset to 0
            "total_estimated": 0,
            "potential_savings": 0,
        }

    def get_scan_status(self, scan_id: str) -> dict:
        """
        Get scan session status

        Args:
            scan_id: Scan session ID

        Returns:
            Scan status dictionary
        """
        scan = self.db.query(ScanSession).filter_by(id=scan_id).first()

        if not scan:
            return {}

        elapsed = None
        if scan.completed_at:
            elapsed = (scan.completed_at - scan.started_at).total_seconds()
        elif scan.status == "running":
            elapsed = (datetime.utcnow() - scan.started_at).total_seconds()

        return {
            'id': scan.id,
            'path': scan.start_path,
            'status': scan.status,
            'total_files': scan.total_files,
            'total_size': scan.total_size,
            'started_at': scan.started_at.isoformat(),
            'completed_at': scan.completed_at.isoformat() if scan.completed_at else None,
            'elapsed_seconds': elapsed,
            'error_message': scan.error_message,
            'progress': self.get_progress_snapshot(scan_id),
        }

    def get_scan_files(
        self,
        scan_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """
        Get files from a scan session

        Args:
            scan_id: Scan session ID
            limit: Number of files to return
            offset: Number of files to skip

        Returns:
            Dictionary with files list and total count
        """
        query = self.db.query(File).filter_by(scan_id=scan_id)
        total = query.count()

        files = query.offset(offset).limit(limit).all()

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
                    'hash_md5': f.hash_md5,
                    'hash_blake3': f.hash_blake3,
                    'hash_sha256': f.hash_sha256,
                    'created_at': f.created_at.isoformat(),
                    'modified_at': f.modified_at.isoformat(),
                }
                for f in files
            ]
        }

    def get_storage_stats(self) -> dict:
        """
        Get overall storage statistics

        Returns:
            Storage stats dictionary
        """
        latest_scan = self.db.query(ScanSession)\
            .filter_by(status="completed")\
            .order_by(ScanSession.completed_at.desc())\
            .first()

        if not latest_scan:
            return {
                'total_files': 0,
                'total_size': 0,
                'total_size_formatted': '0 B',
                'last_scan': None,
            }

        return {
            'total_files': latest_scan.total_files,
            'total_size': latest_scan.total_size,
            'total_size_formatted': get_file_size(latest_scan.total_size),
            'last_scan': latest_scan.completed_at.isoformat(),
        }
