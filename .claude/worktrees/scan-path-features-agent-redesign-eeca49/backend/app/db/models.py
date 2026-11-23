"""
SQLAlchemy ORM models for Storage Manager
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, LargeBinary, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

Base = declarative_base()


class File(Base):
    """File metadata model"""
    __tablename__ = "files"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id = Column(String(36), nullable=False, index=True)
    path = Column(String(2048), nullable=False, unique=True, index=True)
    name = Column(String(256), nullable=False, index=True)
    size = Column(Integer, nullable=False, index=True)
    mime_type = Column(String(128), nullable=True)
    hash_md5 = Column(String(32), nullable=True, index=True)
    hash_sha256 = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    modified_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    indexed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # File usage tracking
    last_accessed = Column(DateTime, nullable=True, index=True)  # Last access time
    usage_category = Column(String(50), nullable=True, index=True)  # RECENTLY_USED, RARELY_USED, NOT_USED
    days_since_access = Column(Integer, nullable=True)  # Cached value for quick filtering
    usage_priority = Column(Float, nullable=True)  # Priority score for cleanup (0.0-1.0)
    
    # Relationships
    duplicate_entries = relationship("DuplicateEntry", back_populates="file", cascade="all, delete-orphan")
    backup_file = relationship("BackupFile", back_populates="original_file", uselist=False, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<File(id={self.id}, path={self.path}, size={self.size}, category={self.usage_category})>"


class DuplicateGroup(Base):
    """Group of duplicate files"""
    __tablename__ = "duplicate_groups"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id = Column(String(36), nullable=False, index=True)
    group_type = Column(String(50), nullable=False, index=True)  # "exact", "phash", "embedding"
    total_size = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    entries = relationship("DuplicateEntry", back_populates="group", cascade="all, delete-orphan")
    
    @property
    def file_count(self) -> int:
        """Number of files in this group"""
        return len(self.entries)
    
    @property
    def savings(self) -> int:
        """Potential storage savings (all but largest file)"""
        if self.file_count <= 1:
            return 0
        sizes = sorted([e.file.size for e in self.entries], reverse=True)
        return sum(sizes[1:])
    
    def __repr__(self):
        return f"<DuplicateGroup(id={self.id}, type={self.group_type}, count={self.file_count})>"


class DuplicateEntry(Base):
    """Individual entry in a duplicate group"""
    __tablename__ = "duplicate_entries"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(String(36), ForeignKey("duplicate_groups.id"), nullable=False, index=True)
    file_id = Column(String(36), ForeignKey("files.id"), nullable=False, index=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    similarity_score = Column(Float, nullable=False, default=1.0)  # 0.0-1.0
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    group = relationship("DuplicateGroup", back_populates="entries")
    file = relationship("File", back_populates="duplicate_entries")
    
    def __repr__(self):
        return f"<DuplicateEntry(file_id={self.file_id}, similarity={self.similarity_score})>"


class BackupFile(Base):
    """Backup of deleted files"""
    __tablename__ = "backup_files"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    original_file_id = Column(String(36), ForeignKey("files.id"), nullable=False, unique=True)
    original_path = Column(String(2048), nullable=False)
    backup_path = Column(String(2048), nullable=False, unique=True)
    file_size = Column(Integer, nullable=False)
    deleted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    restored_at = Column(DateTime, nullable=True)
    permanently_deleted_at = Column(DateTime, nullable=True)
    
    # Relationships
    original_file = relationship("File", back_populates="backup_file")
    
    @property
    def is_restored(self) -> bool:
        """Check if file has been restored"""
        return self.restored_at is not None
    
    @property
    def is_permanently_deleted(self) -> bool:
        """Check if file has been permanently deleted"""
        return self.permanently_deleted_at is not None
    
    def __repr__(self):
        return f"<BackupFile(id={self.id}, backup_path={self.backup_path})>"


class ScanSession(Base):
    """Metadata about scan sessions"""
    __tablename__ = "scan_sessions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    start_path = Column(String(2048), nullable=False)
    status = Column(String(50), nullable=False, default="running")  # running, completed, failed
    total_files = Column(Integer, nullable=False, default=0)
    total_size = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<ScanSession(id={self.id}, path={self.start_path}, status={self.status})>"


class UsageThreshold(Base):
    """Configurable thresholds for file usage categorization"""
    __tablename__ = "usage_thresholds"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    recently_used_days = Column(Integer, nullable=False, default=30, index=True)  # 0-30 days
    rarely_used_days = Column(Integer, nullable=False, default=180, index=True)   # 31-180 days
    not_used_days = Column(Integer, nullable=False, default=180, index=True)      # 180+ days
    min_priority_size_mb = Column(Integer, nullable=False, default=100)  # Minimum file size for high priority
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<UsageThreshold(recently={self.recently_used_days}d, rarely={self.rarely_used_days}d, not_used={self.not_used_days}d)>"
