"""
Scan service - orchestrates file scanning and database persistence
"""
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
import os
import threading
import time
import uuid
from datetime import datetime

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from ..core.scanner import FileScanner, should_skip_dir, should_skip_file
from ..db.models import File, ScanSession
from ..db.connection import get_session
from ..utils.file_utils import get_file_size
from ..utils.path_utils import normalize_scan_path, path_key, paths_overlap
from .usage_service import UsageService
from .duplicate_service import DuplicateService

logger = logging.getLogger(__name__)

BATCH_SIZE = 500
PROGRESS_INTERVAL_SECONDS = 0.15
TERMINAL_STATUSES = ("completed", "failed", "cancelled", "interrupted")

# Live progress for scans running in background threads, keyed by scan id.
# Read by the status endpoint and the /ws/scan WebSocket while a scan runs.
_progress: Dict[str, dict] = {}
_progress_lock = threading.Lock()

# Scans running in this process: scan_id -> {"path": Path, "cancel": Event}.
# Used to refuse overlapping scans (two threads writing the same file rows is
# what produced "UNIQUE constraint failed: files.path" / "database is locked").
_active: Dict[str, dict] = {}
_active_lock = threading.Lock()


class ScanConflictError(Exception):
    """A scan of the same (or an overlapping) folder is already running."""

    def __init__(self, scan_id: str, path: str, same_path: bool):
        self.scan_id = scan_id
        self.path = path
        self.same_path = same_path
        kind = "this folder" if same_path else "an overlapping folder"
        super().__init__(f"A scan of {kind} is already running: {path}")


def get_live_progress(scan_id: str) -> Optional[dict]:
    """Return a copy of the in-memory progress for a scan, or None if not tracked"""
    with _progress_lock:
        info = _progress.get(scan_id)
        return dict(info) if info else None


def _set_progress(scan_id: str, **fields) -> None:
    with _progress_lock:
        _progress.setdefault(scan_id, {}).update(fields)


def active_scans() -> List[dict]:
    with _active_lock:
        return [{"scan_id": sid, "path": str(info["path"])} for sid, info in _active.items()]


def cancel_scan(scan_id: str) -> bool:
    """Ask a running scan to stop after the current file. Returns False if not running."""
    with _active_lock:
        info = _active.get(scan_id)
    if not info:
        return False
    info["cancel"].set()
    _set_progress(scan_id, phase="cancelling")
    return True


def mark_interrupted_scans() -> int:
    """
    Sessions left "running" by a previous server process can never finish
    (their threads died with it). Flag them so the UI stops waiting on them.
    """
    db = get_session()
    try:
        count = (
            db.query(ScanSession)
            .filter(ScanSession.status == "running")
            .update(
                {
                    ScanSession.status: "interrupted",
                    ScanSession.error_message: "The app was closed before this scan finished.",
                    ScanSession.completed_at: datetime.utcnow(),
                },
                synchronize_session=False,
            )
        )
        db.commit()
        if count:
            logger.info(f"Marked {count} orphaned scan session(s) as interrupted")
        return count
    finally:
        db.close()


def _like_prefix(prefix: str) -> str:
    return prefix.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


class ScanService:
    """Service for managing file scans"""

    def __init__(self, db_session: Session, compute_hashes: bool = True):
        self.db = db_session
        self.scanner = FileScanner(compute_hashes=compute_hashes)

    # ------------------------------------------------------------------ start

    def create_scan(self, start_path: Path) -> str:
        """Create a running scan session row and return its ID"""
        scan_session = ScanSession(start_path=str(start_path), status="running")
        self.db.add(scan_session)
        self.db.commit()
        _set_progress(
            scan_session.id,
            status="running",
            phase="starting",
            path=str(start_path),
            files_found=0,
            total_size=0,
            current_file="",
            current_folder="",
            percentage=0,
            total_estimated=0,
            potential_savings=0,
            hashes_reused=0,
            skipped_folders=0,
            files_per_second=0,
            error_message=None,
        )
        return scan_session.id

    def _claim(self, start_path: Path) -> Tuple[str, threading.Event]:
        """Atomically refuse overlapping scans and register this one."""
        with _active_lock:
            for sid, info in _active.items():
                if paths_overlap(info["path"], start_path):
                    same = path_key(info["path"]) == path_key(start_path)
                    raise ScanConflictError(sid, str(info["path"]), same)
            scan_id = self.create_scan(start_path)
            cancel = threading.Event()
            _active[scan_id] = {"path": start_path, "cancel": cancel}
        return scan_id, cancel

    def start_scan_background(
        self,
        start_path,
        recursive: bool = True,
        include_hidden: bool = False,
    ) -> str:
        """
        Normalize the path, create a scan session and run it in a background thread.

        Raises:
            ScanPathError: empty path
            FileNotFoundError / NotADirectoryError: bad folder
            ScanConflictError: an overlapping scan is already running
        """
        start_path = self.validate_root(start_path)
        scan_id, cancel = self._claim(start_path)
        compute_hashes = self.scanner.compute_hashes

        def worker():
            worker_db = get_session()
            try:
                ScanService(worker_db, compute_hashes=compute_hashes).run_scan(
                    scan_id, start_path, recursive, include_hidden, cancel
                )
            finally:
                worker_db.close()
                with _active_lock:
                    _active.pop(scan_id, None)

        threading.Thread(target=worker, name=f"scan-{scan_id}", daemon=True).start()
        logger.info(f"Scan {scan_id} started in background for: {start_path}")
        return scan_id

    def start_scan(self, start_path, recursive: bool = True, include_hidden: bool = False) -> str:
        """Run a file scan synchronously and store results in database"""
        start_path = self.validate_root(start_path)
        scan_id, cancel = self._claim(start_path)
        try:
            self.run_scan(scan_id, start_path, recursive, include_hidden, cancel)
        finally:
            with _active_lock:
                _active.pop(scan_id, None)
        return scan_id

    @staticmethod
    def validate_root(start_path) -> Path:
        path = normalize_scan_path(str(start_path))
        if not path.exists():
            raise FileNotFoundError(f"Folder not found: {path}")
        if not path.is_dir():
            raise NotADirectoryError(f"That is a file, not a folder: {path}")
        return path

    # ------------------------------------------------------------------- run

    def _count_files_fast(self, start_path: Path, recursive: bool, include_hidden: bool,
                          stop: Optional[threading.Event] = None) -> int:
        """
        Cheap pre-count used only to estimate progress. Mirrors the scanner's
        rules (excluded dirs/extensions, hidden files) without stat or hashing.
        Returns 0 on failure so callers fall back to an indeterminate bar.
        """
        count = 0
        stack = [str(start_path)]
        try:
            while stack:
                if stop is not None and stop.is_set():
                    return 0
                directory = stack.pop()
                try:
                    with os.scandir(directory) as it:
                        for entry in it:
                            try:
                                if entry.is_dir(follow_symlinks=False):
                                    if recursive and not should_skip_dir(entry.name, include_hidden):
                                        stack.append(entry.path)
                                elif not should_skip_file(entry.name, include_hidden):
                                    count += 1
                            except OSError:
                                continue
                except OSError:
                    continue
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Pre-count failed for {start_path}: {e}")
            return 0
        return count

    def _load_existing(self, start_path: Path) -> Tuple[Dict[str, tuple], Dict[str, tuple]]:
        """
        Lightweight index of rows already stored under this folder:
        (id, path, size, modified_at, md5, sha256). Only these columns are
        loaded - not ORM objects - so a re-scan of a big drive stays cheap.
        """
        prefix = str(start_path)
        if not prefix.endswith(os.sep):
            prefix += os.sep
        rows = (
            self.db.query(File.id, File.path, File.size, File.modified_at,
                          File.hash_md5, File.hash_sha256)
            .filter(File.path.like(_like_prefix(prefix), escape='\\'))
            .all()
        )
        by_path: Dict[str, tuple] = {}
        by_key: Dict[str, tuple] = {}
        for row in rows:
            t = tuple(row)
            by_path[t[1]] = t
            by_key.setdefault(path_key(t[1]), t)
        return by_path, by_key

    def run_scan(
        self,
        scan_id: str,
        start_path: Path,
        recursive: bool = True,
        include_hidden: bool = False,
        cancel: Optional[threading.Event] = None,
    ) -> None:
        """
        Walk a directory and store/refresh a File record for every file found.

        A path an earlier scan already indexed is updated in place (moved to
        this scan) instead of inserted again, because files.path is unique.
        Unchanged files (same size and modified time) reuse their stored
        hashes instead of being read again. Errors are recorded on the scan
        session; they are not re-raised.
        """
        start_path = Path(start_path)
        cancel = cancel or threading.Event()
        logger.info(f"Running scan {scan_id} for path: {start_path}")

        try:
            self.scanner.include_hidden = include_hidden
            self.scanner.should_stop = cancel.is_set
            _set_progress(scan_id, phase="indexing")

            by_path, by_key = self._load_existing(start_path)

            def lookup(path_str: str):
                return by_path.get(path_str) or by_key.get(path_key(path_str))

            def hash_lookup(path_str: str, size: int, mtime: datetime):
                row = lookup(path_str)
                if row and row[2] == size and row[3] == mtime and row[4]:
                    return row[4], row[5]
                return None

            self.scanner.hash_lookup = hash_lookup

            # Estimate the total in parallel instead of walking the tree twice
            # before showing anything.
            def precount():
                total = self._count_files_fast(start_path, recursive, include_hidden, cancel)
                _set_progress(scan_id, total_estimated=total)

            threading.Thread(target=precount, name=f"count-{scan_id}", daemon=True).start()

            now = datetime.utcnow()
            began = time.monotonic()
            last_progress = 0.0
            total_files = 0
            total_size = 0
            hashes_reused = 0
            potential_savings = 0
            seen_hashes: Dict[str, int] = {}
            scanned_paths: List[Path] = []
            inserts: List[dict] = []
            updates: List[dict] = []

            for metadata in self.scanner.scan(start_path, recursive):
                path_str = str(metadata.path)
                values = {
                    "scan_id": scan_id,
                    "path": path_str,
                    "name": metadata.name[:256],
                    "size": metadata.size,
                    "mime_type": metadata.mime_type,
                    "hash_md5": metadata.hash_md5,
                    "hash_sha256": metadata.hash_sha256,
                    "created_at": metadata.created_at,
                    "modified_at": metadata.modified_at,
                    "indexed_at": now,
                }
                existing = lookup(path_str)
                if existing:
                    values["id"] = existing[0]
                    updates.append(values)
                else:
                    values["id"] = str(uuid.uuid4())
                    inserts.append(values)
                    row = (values["id"], path_str, metadata.size, metadata.modified_at,
                           metadata.hash_md5, metadata.hash_sha256)
                    by_path[path_str] = row
                    by_key[path_key(path_str)] = row

                total_files += 1
                total_size += metadata.size
                hashes_reused += metadata.hash_reused
                scanned_paths.append(metadata.path)

                # Running count of recoverable space: every repeat of a hash
                # (only populated when compute_hashes is on) is an extra copy
                if metadata.hash_md5:
                    if metadata.hash_md5 in seen_hashes:
                        potential_savings += metadata.size
                    else:
                        seen_hashes[metadata.hash_md5] = metadata.size

                if len(inserts) + len(updates) >= BATCH_SIZE:
                    self._flush(inserts, updates)

                tick = time.monotonic()
                if tick - last_progress >= PROGRESS_INTERVAL_SECONDS:
                    last_progress = tick
                    self._report(scan_id, total_files, total_size, potential_savings,
                                 hashes_reused, metadata, tick - began)

            self._flush(inserts, updates)
            elapsed = time.monotonic() - began

            scan_session = self.db.query(ScanSession).filter_by(id=scan_id).one()
            scan_session.total_files = total_files
            scan_session.total_size = total_size
            final = dict(
                files_found=total_files,
                total_size=total_size,
                potential_savings=potential_savings,
                hashes_reused=hashes_reused,
                skipped_folders=self.scanner.skipped_dirs,
                files_per_second=round(total_files / elapsed, 1) if elapsed > 0 else 0,
            )

            if cancel.is_set():
                scan_session.status = "cancelled"
                scan_session.error_message = f"Stopped after {total_files:,} files."
                scan_session.completed_at = datetime.utcnow()
                self.db.commit()
                _set_progress(scan_id, status="cancelled", phase="cancelled",
                              error_message=scan_session.error_message, **final)
                logger.info(f"Scan {scan_id} cancelled after {total_files} files")
                return

            self.db.commit()
            _set_progress(scan_id, percentage=99, **final)

            # Usage analysis runs only after the file records are stored
            _set_progress(scan_id, phase="analyzing usage", current_file="", current_folder="")
            try:
                usage_service = UsageService(self.db)
                for i in range(0, len(scanned_paths), 1000):
                    if cancel.is_set():
                        break
                    usage_service.batch_update_usage(scanned_paths[i:i + 1000])
            except Exception as ue:
                logger.warning(f"Usage analysis post-scan failed: {ue}")
                self.db.rollback()

            # Duplicate detection runs automatically so results are ready
            # as soon as the scan finishes, without a separate manual step
            _set_progress(scan_id, phase="finding duplicates")
            try:
                dup_service = DuplicateService(self.db)
                exact_groups = dup_service.detect_exact_duplicates(scan_id)
                image_groups = dup_service.detect_image_duplicates(scan_id)
                _set_progress(scan_id, duplicate_groups=len(exact_groups) + len(image_groups))
                logger.info(
                    f"Scan {scan_id}: {len(exact_groups)} exact and "
                    f"{len(image_groups)} similar-image duplicate groups found"
                )
            except Exception as de:
                logger.warning(f"Duplicate detection post-scan failed: {de}")
                self.db.rollback()

            scan_session = self.db.query(ScanSession).filter_by(id=scan_id).one()
            scan_session.status = "completed"
            scan_session.completed_at = datetime.utcnow()
            self.db.commit()
            _set_progress(scan_id, status="completed", phase="done", percentage=100)
            logger.info(
                f"Scan {scan_id} completed: {total_files} files, {total_size} bytes, "
                f"{hashes_reused} hashes reused, {elapsed:.1f}s"
            )

        except Exception as e:
            logger.error(f"Scan {scan_id} failed: {e}", exc_info=True)
            self.db.rollback()
            scan_session = self.db.query(ScanSession).filter_by(id=scan_id).first()
            message = str(e).split("\n")[0]
            if scan_session:
                scan_session.status = "failed"
                scan_session.error_message = message
                scan_session.completed_at = datetime.utcnow()
                self.db.commit()
            _set_progress(scan_id, status="failed", phase="failed", error_message=message)

    def _report(self, scan_id, total_files, total_size, potential_savings,
                hashes_reused, metadata, elapsed) -> None:
        live = get_live_progress(scan_id) or {}
        total_estimated = live.get("total_estimated") or 0
        percentage = (
            min(98, round(total_files / total_estimated * 100)) if total_estimated > 0 else 0
        )
        _set_progress(
            scan_id,
            files_found=total_files,
            total_size=total_size,
            current_file=metadata.name,
            current_folder=str(metadata.path.parent),
            percentage=percentage,
            potential_savings=potential_savings,
            hashes_reused=hashes_reused,
            skipped_folders=self.scanner.skipped_dirs,
            files_per_second=round(total_files / elapsed, 1) if elapsed > 0 else 0,
        )

    def _flush(self, inserts: List[dict], updates: List[dict]) -> None:
        """Write a batch with two bulk statements instead of one ORM object per file."""
        if inserts:
            self.db.execute(File.__table__.insert(), inserts)
            inserts.clear()
        if updates:
            self.db.execute(update(File), updates)
            updates.clear()
        self.db.commit()

    # ---------------------------------------------------------------- queries

    def get_progress_snapshot(self, scan_id: str) -> Optional[dict]:
        """Progress for a scan: live values while it runs, otherwise the stored session"""
        live = get_live_progress(scan_id)
        if live and (live.get("status") == "running" or scan_id in _active):
            live.setdefault("total_estimated", 0)
            live.setdefault("potential_savings", 0)
            return live

        scan = self.db.query(ScanSession).filter_by(id=scan_id).first()
        if not scan:
            return None
        snapshot = {
            "status": scan.status,
            "phase": scan.status,
            "path": scan.start_path,
            "files_found": scan.total_files,
            "total_size": scan.total_size,
            "current_file": "",
            "current_folder": "",
            "percentage": 100 if scan.status == "completed" else 0,
            "error_message": scan.error_message,
            "total_estimated": 0,
            "potential_savings": 0,
        }
        if live:  # finished in this process: keep the richer live figures
            for key in ("potential_savings", "hashes_reused", "skipped_folders",
                        "files_per_second", "duplicate_groups"):
                if key in live:
                    snapshot[key] = live[key]
        return snapshot

    def get_scan_status(self, scan_id: str) -> dict:
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

    def get_scan_history(self, limit: int = 10) -> List[dict]:
        """Most recent scan sessions for the "Recent scans" list."""
        sessions = (
            self.db.query(ScanSession)
            .order_by(ScanSession.started_at.desc())
            .limit(max(1, min(limit, 100)))
            .all()
        )
        history = []
        for s in sessions:
            status = s.status
            if status == "running" and s.id not in _active:
                status = "interrupted"
            duration = (s.completed_at - s.started_at).total_seconds() if s.completed_at else None
            history.append({
                "id": s.id,
                "path": s.start_path,
                "status": status,
                "total_files": s.total_files,
                "total_size": s.total_size,
                "total_size_formatted": get_file_size(s.total_size or 0),
                "started_at": s.started_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "duration_seconds": duration,
                "error_message": s.error_message,
            })
        return history

    def get_scan_summary(self, scan_id: str, top: int = 10) -> dict:
        """Space by file category plus the largest files, for the results card."""
        rows = (
            self.db.query(File.mime_type, func.count(File.id), func.coalesce(func.sum(File.size), 0))
            .filter(File.scan_id == scan_id)
            .group_by(File.mime_type)
            .all()
        )
        categories: Dict[str, dict] = {}
        for mime, count, size in rows:
            cat = _category(mime)
            bucket = categories.setdefault(cat, {"category": cat, "count": 0, "size": 0})
            bucket["count"] += count
            bucket["size"] += int(size or 0)
        by_category = sorted(categories.values(), key=lambda c: c["size"], reverse=True)

        largest = (
            self.db.query(File.id, File.name, File.path, File.size, File.mime_type)
            .filter(File.scan_id == scan_id)
            .order_by(File.size.desc())
            .limit(max(1, min(top, 50)))
            .all()
        )
        return {
            "scan_id": scan_id,
            "by_category": by_category,
            "largest_files": [
                {"id": f.id, "name": f.name, "path": f.path, "size": f.size,
                 "size_formatted": get_file_size(f.size), "category": _category(f.mime_type)}
                for f in largest
            ],
        }

    def get_scan_files(self, scan_id: str, limit: int = 100, offset: int = 0) -> dict:
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
                    'hash_sha256': f.hash_sha256,
                    'created_at': f.created_at.isoformat(),
                    'modified_at': f.modified_at.isoformat(),
                }
                for f in files
            ]
        }

    def get_storage_stats(self) -> dict:
        latest_scan = (
            self.db.query(ScanSession)
            .filter_by(status="completed")
            .order_by(ScanSession.completed_at.desc())
            .first()
        )
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


def _category(mime: Optional[str]) -> str:
    if not mime:
        return "other"
    top = mime.split("/", 1)[0]
    if top in ("image", "video", "audio"):
        return top
    if top == "text" or any(k in mime for k in ("pdf", "word", "excel", "sheet",
                                                  "presentation", "powerpoint", "document")):
        return "document"
    if any(k in mime for k in ("zip", "compressed", "tar", "rar", "7z", "gzip")):
        return "archive"
    if any(k in mime for k in ("executable", "msdownload", "x-msi", "octet-stream")):
        return "program"
    return "other"
