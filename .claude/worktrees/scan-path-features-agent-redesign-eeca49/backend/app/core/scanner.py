"""
File system scanning module
"""
from pathlib import Path
from typing import Callable, Generator, Optional, Tuple
import hashlib
import logging
import mimetypes
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# System folders and files to exclude
EXCLUDED_DIRS = {
    '.git', '.svn', '.hg',  # Version control
    '__pycache__', '.pytest_cache', '.mypy_cache', 'node_modules',  # Dev/build
    '.venv', 'venv', 'env',  # Virtual environments
    '.idea', '.vscode',  # IDE
    '$Recycle.Bin', 'System Volume Information', '$WINDOWS.~BT',  # Windows system
    '.Trash', '.Spotlight-V100', '.TemporaryItems',  # macOS
    '.cache', '.local',  # Linux
}

EXCLUDED_EXTENSIONS = {'.tmp', '.lock', '.swp', '.swo', '.bak'}

# Read files in 1 MiB chunks: far fewer syscalls than 8 KiB on large media
HASH_CHUNK_SIZE = 1024 * 1024

# (path, size, mtime) -> (md5, sha256) when the caller already knows the hashes
# of an unchanged file, otherwise None so the scanner computes them.
HashLookup = Callable[[str, int, datetime], Optional[Tuple[Optional[str], Optional[str]]]]


def is_hidden_name(name: str) -> bool:
    return name.startswith('.')


def should_skip_dir(name: str, include_hidden: bool) -> bool:
    return name in EXCLUDED_DIRS or (not include_hidden and is_hidden_name(name))


def should_skip_file(name: str, include_hidden: bool) -> bool:
    if not include_hidden and is_hidden_name(name):
        return True
    return os.path.splitext(name)[1].lower() in EXCLUDED_EXTENSIONS


class FileMetadata:
    """Container for file metadata"""

    __slots__ = ('path', 'name', 'size', 'mime_type', 'created_at', 'modified_at',
                 'hash_md5', 'hash_sha256', 'hash_reused')

    def __init__(
        self,
        path: Path,
        name: str,
        size: int,
        mime_type: Optional[str],
        created_at: datetime,
        modified_at: datetime,
    ):
        self.path = path
        self.name = name
        self.size = size
        self.mime_type = mime_type
        self.created_at = created_at
        self.modified_at = modified_at
        self.hash_md5: Optional[str] = None
        self.hash_sha256: Optional[str] = None
        self.hash_reused = False

    def __repr__(self):
        return f"<FileMetadata(path={self.path}, size={self.size})>"


class FileScanner:
    """File system scanner with metadata collection"""

    def __init__(
        self,
        include_hidden: bool = False,
        batch_size: int = 500,
        compute_hashes: bool = True,
    ):
        """
        Args:
            include_hidden: Include hidden files (default: False)
            batch_size: Kept for API compatibility
            compute_hashes: Compute MD5/SHA256 hashes (default: True)
        """
        self.include_hidden = include_hidden
        self.batch_size = batch_size
        self.compute_hashes = compute_hashes
        self.hash_lookup: Optional[HashLookup] = None
        self.should_stop: Callable[[], bool] = lambda: False
        self._files_scanned = 0
        self.skipped_dirs = 0

    def scan(
        self,
        root_path: Path,
        recursive: bool = True,
    ) -> Generator[FileMetadata, None, None]:
        """
        Scan a directory and yield file metadata.

        Uses an explicit stack (no recursion limit on deep trees) and
        os.scandir, whose directory entries carry cached stat data on Windows,
        so most files need no extra system call for size/timestamps.
        """
        root_path = Path(root_path)

        if not root_path.exists():
            logger.error(f"Path does not exist: {root_path}")
            return
        if not root_path.is_dir():
            logger.error(f"Path is not a directory: {root_path}")
            return

        logger.info(f"Starting scan of: {root_path}")
        self._files_scanned = 0
        self.skipped_dirs = 0

        stack = [str(root_path)]
        while stack:
            if self.should_stop():
                return
            directory = stack.pop()
            try:
                with os.scandir(directory) as it:
                    entries = list(it)
            except (PermissionError, OSError) as e:
                self.skipped_dirs += 1
                logger.debug(f"Cannot access directory {directory}: {e}")
                continue

            subdirs = []
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if recursive and not should_skip_dir(entry.name, self.include_hidden):
                            subdirs.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        if should_skip_file(entry.name, self.include_hidden):
                            continue
                        metadata = self._entry_metadata(entry)
                        if metadata:
                            self._files_scanned += 1
                            yield metadata
                            if self.should_stop():
                                return
                except (PermissionError, OSError) as e:
                    logger.debug(f"Cannot access {entry.path}: {e}")
                    continue
            # Reverse so folders are visited in listing order (stack is LIFO)
            stack.extend(reversed(subdirs))

    def _entry_metadata(self, entry: os.DirEntry) -> Optional[FileMetadata]:
        try:
            stat = entry.stat(follow_symlinks=False)
        except (PermissionError, OSError) as e:
            logger.debug(f"Cannot stat {entry.path}: {e}")
            return None
        return self._build_metadata(Path(entry.path), entry.name, stat)

    def _get_file_metadata(self, file_path: Path) -> Optional[FileMetadata]:
        """Extract metadata from a file path (kept for callers outside scan())."""
        try:
            stat = file_path.stat()
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot read file {file_path}: {e}")
            return None
        return self._build_metadata(file_path, file_path.name, stat)

    def _build_metadata(self, file_path: Path, name: str, stat) -> FileMetadata:
        mime_type, _ = mimetypes.guess_type(name)
        metadata = FileMetadata(
            path=file_path,
            name=name,
            size=stat.st_size,
            mime_type=mime_type,
            created_at=datetime.fromtimestamp(stat.st_ctime),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
        )

        if self.compute_hashes:
            known = None
            if self.hash_lookup is not None:
                known = self.hash_lookup(str(file_path), metadata.size, metadata.modified_at)
            if known and known[0]:
                metadata.hash_md5, metadata.hash_sha256 = known
                metadata.hash_reused = True
            else:
                metadata.hash_md5, metadata.hash_sha256 = self._compute_hashes(file_path)
        return metadata

    def _compute_hashes(self, file_path: Path) -> Tuple[Optional[str], Optional[str]]:
        """MD5 and SHA-256 from a single read of the file."""
        try:
            md5 = hashlib.md5()
            sha = hashlib.sha256()
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(HASH_CHUNK_SIZE)
                    if not chunk:
                        break
                    md5.update(chunk)
                    sha.update(chunk)
            return md5.hexdigest(), sha.hexdigest()
        except (PermissionError, OSError) as e:
            logger.debug(f"Cannot compute hash for {file_path}: {e}")
            return None, None

    def _compute_hash(self, file_path: Path, algorithm: str) -> Optional[str]:
        """Single-algorithm hash (kept for existing callers)."""
        try:
            hash_func = hashlib.new(algorithm)
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(HASH_CHUNK_SIZE), b''):
                    hash_func.update(chunk)
            return hash_func.hexdigest()
        except (PermissionError, OSError) as e:
            logger.debug(f"Cannot compute hash for {file_path}: {e}")
            return None

    @property
    def files_scanned(self) -> int:
        """Number of files scanned in last scan"""
        return self._files_scanned
