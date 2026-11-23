"""
File system scanning module
"""
from pathlib import Path
from typing import Generator, Optional, Dict, Set
import mimetypes
import hashlib
import logging
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


class FileMetadata:
    """Container for file metadata"""
    
    def __init__(
        self,
        path: Path,
        name: str,
        size: int,
        mime_type: Optional[str],
        created_at: datetime,
        modified_at: datetime,
    ):
        """
        Initialize file metadata
        
        Args:
            path: Full path to file
            name: File name
            size: File size in bytes
            mime_type: MIME type
            created_at: Creation time
            modified_at: Modification time
        """
        self.path = path
        self.name = name
        self.size = size
        self.mime_type = mime_type
        self.created_at = created_at
        self.modified_at = modified_at
        self.hash_md5: Optional[str] = None
        self.hash_sha256: Optional[str] = None
    
    def __repr__(self):
        return f"<FileMetadata(path={self.path}, size={self.size})>"


class FileScanner:
    """Recursive file system scanner with metadata collection"""
    
    def __init__(
        self,
        include_hidden: bool = False,
        batch_size: int = 500,
        compute_hashes: bool = True,
    ):
        """
        Initialize file scanner
        
        Args:
            include_hidden: Include hidden files (default: False)
            batch_size: Number of files to batch before yielding
            compute_hashes: Compute MD5/SHA256 hashes (default: True)
        """
        self.include_hidden = include_hidden
        self.batch_size = batch_size
        self.compute_hashes = compute_hashes
        self._files_scanned = 0
    
    def scan(
        self,
        root_path: Path,
        recursive: bool = True,
    ) -> Generator[FileMetadata, None, None]:
        """
        Scan directory and yield file metadata
        
        Args:
            root_path: Root directory to scan
            recursive: Recursively scan subdirectories (default: True)
        
        Yields:
            FileMetadata objects
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
        
        try:
            for metadata in self._scan_recursive(root_path, recursive):
                self._files_scanned += 1
                yield metadata
        except Exception as e:
            logger.error(f"Error during scan: {e}", exc_info=True)
            raise
    
    def _scan_recursive(
        self,
        directory: Path,
        recursive: bool,
    ) -> Generator[FileMetadata, None, None]:
        """
        Recursively scan directory
        
        Args:
            directory: Directory to scan
            recursive: Whether to recurse into subdirectories
        
        Yields:
            FileMetadata objects
        """
        try:
            entries = list(directory.iterdir())
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot access directory {directory}: {e}")
            return
        
        for entry in entries:
            try:
                # Skip hidden files/dirs if not included
                if not self.include_hidden and entry.name.startswith('.'):
                    continue
                
                if entry.is_dir(follow_symlinks=False):
                    # Skip excluded directories
                    if entry.name not in EXCLUDED_DIRS:
                        if recursive:
                            yield from self._scan_recursive(entry, recursive)
                
                elif entry.is_file(follow_symlinks=False):
                    # Skip files with excluded extensions
                    if entry.suffix.lower() not in EXCLUDED_EXTENSIONS:
                        metadata = self._get_file_metadata(entry)
                        if metadata:
                            yield metadata
            
            except (PermissionError, OSError) as e:
                logger.warning(f"Cannot access {entry}: {e}")
                continue
    
    def _get_file_metadata(self, file_path: Path) -> Optional[FileMetadata]:
        """
        Extract metadata from a file
        
        Args:
            file_path: Path to file
        
        Returns:
            FileMetadata object or None if file is inaccessible
        """
        try:
            stat = file_path.stat()
            size = stat.st_size
            created_at = datetime.fromtimestamp(stat.st_ctime)
            modified_at = datetime.fromtimestamp(stat.st_mtime)
            
            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(str(file_path))
            
            metadata = FileMetadata(
                path=file_path,
                name=file_path.name,
                size=size,
                mime_type=mime_type,
                created_at=created_at,
                modified_at=modified_at,
            )
            
            # Compute hashes if requested
            if self.compute_hashes:
                metadata.hash_md5 = self._compute_hash(file_path, 'md5')
                metadata.hash_sha256 = self._compute_hash(file_path, 'sha256')
            
            return metadata
        
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot read file {file_path}: {e}")
            return None
    
    def _compute_hash(self, file_path: Path, algorithm: str) -> Optional[str]:
        """
        Compute file hash
        
        Args:
            file_path: Path to file
            algorithm: Hash algorithm ('md5' or 'sha256')
        
        Returns:
            Hex hash string or None if file is unreadable
        """
        try:
            hash_func = hashlib.new(algorithm)
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hash_func.update(chunk)
            return hash_func.hexdigest()
        
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot compute hash for {file_path}: {e}")
            return None
    
    @property
    def files_scanned(self) -> int:
        """Number of files scanned in last scan"""
        return self._files_scanned
