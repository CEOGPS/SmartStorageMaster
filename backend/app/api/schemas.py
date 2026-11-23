"""
Pydantic models for API requests and responses
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ============================================================================
# Scan Requests/Responses
# ============================================================================

class ScanStartRequest(BaseModel):
    """Request to start file scan"""
    path: str = Field(..., description="Directory path to scan")
    recursive: bool = Field(True, description="Recursively scan subdirectories")
    include_hidden: bool = Field(False, description="Include hidden files")
    compute_hashes: bool = Field(True, description="Compute file hashes")
    compute_hash: Optional[bool] = Field(None, description="Alias of compute_hashes (frontend name)")


class ScanStatusResponse(BaseModel):
    """Scan session status"""
    id: str
    path: str
    status: str
    total_files: int
    total_size: int
    started_at: datetime
    completed_at: Optional[datetime]
    elapsed_seconds: Optional[float]
    error_message: Optional[str]


class FileMetadataResponse(BaseModel):
    """File metadata"""
    id: str
    path: str
    name: str
    size: int
    mime_type: Optional[str]
    hash_md5: Optional[str]
    hash_sha256: Optional[str]
    created_at: datetime
    modified_at: datetime


class ScanFilesResponse(BaseModel):
    """Files from scan"""
    total: int
    limit: int
    offset: int
    files: List[FileMetadataResponse]


class StorageStatsResponse(BaseModel):
    """Storage statistics"""
    total_files: int
    total_size: int
    total_size_formatted: str
    last_scan: Optional[datetime]


# ============================================================================
# Duplicate Detection Requests/Responses
# ============================================================================

class DuplicateDetectRequest(BaseModel):
    """Request to detect duplicates"""
    scan_id: str = Field(..., description="Scan session ID")
    detect_exact: bool = Field(True, description="Detect exact duplicates")
    detect_images: bool = Field(True, description="Detect image duplicates")
    image_similarity: float = Field(0.85, description="Image similarity threshold")


class DuplicateEntryResponse(BaseModel):
    """Individual duplicate entry"""
    id: str
    path: str
    name: str
    size: int
    mime_type: Optional[str]
    is_primary: bool
    similarity: float


class DuplicateGroupResponse(BaseModel):
    """Group of duplicates"""
    id: str
    type: str
    total_size: int
    file_count: int
    savings: int
    files: List[DuplicateEntryResponse]


class DuplicateGroupsResponse(BaseModel):
    """List of duplicate groups"""
    groups: List[DuplicateGroupResponse]
    total_groups: int
    total_savings: int


class DuplicateStatsResponse(BaseModel):
    """Duplicate detection statistics"""
    total_groups: int
    total_duplicates: int
    total_savings: int
    by_type: dict


# ============================================================================
# Cleanup Requests/Responses
# ============================================================================

class BackupFileIdsRequest(BaseModel):
    """Request to backup files"""
    file_ids: List[str] = Field(..., description="File IDs to backup")


class DeleteFileIdsRequest(BaseModel):
    """Request to delete files"""
    file_ids: List[str] = Field(..., description="File IDs to delete")


class BackupResultResponse(BaseModel):
    """Backup operation result"""
    backed_up: int
    failed: int
    total: int


class DeleteResultResponse(BaseModel):
    """Delete operation result"""
    deleted: int
    failed: int
    total: int


class BackupFileResponse(BaseModel):
    """Backup file information"""
    id: str
    original_path: str
    backup_path: str
    file_size: int
    deleted_at: datetime
    is_restored: bool


class BackupFilesListResponse(BaseModel):
    """List of backups"""
    backups: List[BackupFileResponse]


class RestoreFileRequest(BaseModel):
    """Request to restore file"""
    backup_id: str = Field(..., description="Backup ID to restore")
    restore_to: Optional[str] = Field(None, description="Custom restore path")


class RestoreResultResponse(BaseModel):
    """Restore operation result"""
    success: bool
    restored_path: Optional[str] = None
    error: Optional[str] = None


class CleanupStatsResponse(BaseModel):
    """Cleanup statistics"""
    total_backups: int
    active_backups: int
    total_backup_size: int
    backup_root: str


# ============================================================================
# Generic Responses
# ============================================================================

class APIResponse(BaseModel):
    """Generic API response wrapper"""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorResponse(BaseModel):
    """Error response"""
    detail: str
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatMessage(BaseModel):
    """A single turn in an agent chat history"""
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text")


class ChatRequest(BaseModel):
    """Request to the AI agent chat endpoint"""
    message: str = Field(..., description="The user's natural-language message")
    history: Optional[List[ChatMessage]] = Field(
        default=None, description="Prior conversation turns, oldest first"
    )


# ============================================================================
# Organizer Requests/Responses
# ============================================================================

class OrganizerMoveRequest(BaseModel):
    """Request to move files to a destination folder"""
    file_ids: List[str] = Field(..., description="File IDs to move")
    destination: str = Field(..., description="Destination folder path")
    create_if_missing: bool = Field(True, description="Create destination folder if missing")


class OrganizerCreateFolderRequest(BaseModel):
    """Request to create a folder on disk"""
    path: str = Field(..., description="Folder path to create")


class OrganizerDeleteEmptyFoldersRequest(BaseModel):
    """Request to remove empty subfolders under a root"""
    root: str = Field(..., description="Root directory to clean up under")


class OrganizerDeleteFilesRequest(BaseModel):
    """Request to backup and delete files"""
    file_ids: List[str] = Field(..., description="File IDs to delete")


class OrganizerSortRequest(BaseModel):
    """Request to preview or apply an auto-sort of a folder"""
    source: str = Field(..., description="Folder whose indexed files should be sorted")
    mode: str = Field(..., description="type | extension | date")
    granularity: str = Field('year', description="For date mode: year | month")
    recursive: bool = Field(False, description="Include files in subfolders")
    destination: Optional[str] = Field(None, description="Sort into this root instead of the source folder")
