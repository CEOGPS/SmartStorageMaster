"""
Duplicate detection service
"""
from typing import List, Dict
import logging
from sqlalchemy.orm import Session
from pathlib import Path

from ..db.models import File, DuplicateGroup, DuplicateEntry
from ..ai.image_hash import ImageHasher, ImageHashDatabase

logger = logging.getLogger(__name__)


class DuplicateService:
    """Service for detecting and managing duplicate files"""
    
    def __init__(self, db_session: Session):
        """
        Initialize duplicate service
        
        Args:
            db_session: SQLAlchemy session
        """
        self.db = db_session
    
    def clear_groups(self, scan_id: str, group_type: str = None) -> None:
        """
        Remove existing duplicate groups for a scan so detection can re-run cleanly

        Args:
            scan_id: Scan session ID
            group_type: Only remove groups of this type (default: all types)
        """
        query = self.db.query(DuplicateGroup).filter_by(scan_id=scan_id)
        if group_type:
            query = query.filter_by(group_type=group_type)
        for group in query.all():
            self.db.delete(group)
        self.db.commit()

    def detect_exact_duplicates(self, scan_id: str) -> List[str]:
        """
        Detect exact duplicates using file hashes

        Args:
            scan_id: Scan session ID

        Returns:
            List of duplicate group IDs
        """
        logger.info(f"Detecting exact duplicates for scan {scan_id}")
        self.clear_groups(scan_id, 'exact')

        # Group files by MD5 hash
        hash_groups = {}
        files = self.db.query(File).filter_by(scan_id=scan_id).all()
        
        for file in files:
            if not file.hash_md5:
                continue
            
            if file.hash_md5 not in hash_groups:
                hash_groups[file.hash_md5] = []
            hash_groups[file.hash_md5].append(file)
        
        group_ids = []
        
        # Create duplicate groups
        for hash_value, files_list in hash_groups.items():
            if len(files_list) < 2:
                continue
            
            total_size = sum(f.size for f in files_list)
            
            group = DuplicateGroup(
                scan_id=scan_id,
                group_type='exact',
                total_size=total_size,
            )
            self.db.add(group)
            self.db.flush()
            
            # Add entries
            for idx, file in enumerate(files_list):
                entry = DuplicateEntry(
                    group_id=group.id,
                    file_id=file.id,
                    is_primary=(idx == 0),  # First file is primary
                    similarity_score=1.0,
                )
                self.db.add(entry)
            
            group_ids.append(group.id)
        
        self.db.commit()
        logger.info(f"Found {len(group_ids)} exact duplicate groups")
        
        return group_ids
    
    def detect_image_duplicates(
        self,
        scan_id: str,
        similarity_threshold: float = 0.85,
    ) -> List[str]:
        """
        Detect near-duplicate images using perceptual hashing
        
        Args:
            scan_id: Scan session ID
            similarity_threshold: Similarity threshold (0.0-1.0)
        
        Returns:
            List of duplicate group IDs
        """
        logger.info(f"Detecting image duplicates for scan {scan_id}")
        self.clear_groups(scan_id, 'phash')

        db = ImageHashDatabase(similarity_threshold=similarity_threshold)
        
        # Load image files
        image_files = self.db.query(File).filter(
            File.scan_id == scan_id,
            File.mime_type.like('image/%'),
        ).all()
        
        logger.info(f"Found {len(image_files)} image files")
        
        group_ids = []
        processed = set()
        
        for file in image_files:
            if file.id in processed:
                continue
            
            file_path = Path(file.path)
            if not db.add_image(file_path):
                continue
            
            # Find similar images
            similar = db.find_similar(file_path)
            
            if not similar:
                continue
            
            # Create group
            total_size = file.size
            for sim_path, score in similar:
                sim_file = self.db.query(File).filter_by(
                    scan_id=scan_id,
                    path=str(sim_path),
                ).first()
                if sim_file:
                    total_size += sim_file.size
            
            group = DuplicateGroup(
                scan_id=scan_id,
                group_type='phash',
                total_size=total_size,
            )
            self.db.add(group)
            self.db.flush()
            
            # Add primary entry
            entry = DuplicateEntry(
                group_id=group.id,
                file_id=file.id,
                is_primary=True,
                similarity_score=1.0,
            )
            self.db.add(entry)
            processed.add(file.id)
            
            # Add similar entries
            for sim_path, score in similar:
                sim_file = self.db.query(File).filter_by(
                    scan_id=scan_id,
                    path=str(sim_path),
                ).first()
                if sim_file and sim_file.id not in processed:
                    entry = DuplicateEntry(
                        group_id=group.id,
                        file_id=sim_file.id,
                        is_primary=False,
                        similarity_score=score,
                    )
                    self.db.add(entry)
                    processed.add(sim_file.id)
            
            group_ids.append(group.id)
        
        self.db.commit()
        logger.info(f"Found {len(group_ids)} image duplicate groups")
        
        return group_ids
    
    def get_duplicate_groups(self, scan_id: str, group_type: str = None) -> List[Dict]:
        """
        Get duplicate groups
        
        Args:
            scan_id: Scan session ID
            group_type: Filter by type (exact, phash, embedding, etc.)
        
        Returns:
            List of group dictionaries
        """
        query = self.db.query(DuplicateGroup).filter_by(scan_id=scan_id)
        
        if group_type:
            query = query.filter_by(group_type=group_type)
        
        groups = query.all()
        
        result = []
        for group in groups:
            files_data = []
            for entry in group.entries:
                file = entry.file
                files_data.append({
                    'id': file.id,
                    'path': file.path,
                    'name': file.name,
                    'size': file.size,
                    'mime_type': file.mime_type,
                    'modified_at': file.modified_at.isoformat() if file.modified_at else None,
                    'is_primary': entry.is_primary,
                    'similarity': entry.similarity_score,
                })
            
            result.append({
                'id': group.id,
                'type': group.group_type,
                'total_size': group.total_size,
                'file_count': group.file_count,
                'savings': group.savings,
                'files': files_data,
            })
        
        return result
    
    def get_duplicate_stats(self, scan_id: str) -> Dict:
        """
        Get duplicate statistics
        
        Args:
            scan_id: Scan session ID
        
        Returns:
            Statistics dictionary
        """
        groups = self.db.query(DuplicateGroup).filter_by(scan_id=scan_id).all()
        
        total_groups = len(groups)
        total_duplicates = sum(g.file_count for g in groups)
        total_savings = sum(g.savings for g in groups)
        
        # Group by type
        by_type = {}
        for group in groups:
            if group.group_type not in by_type:
                by_type[group.group_type] = {'count': 0, 'savings': 0}
            by_type[group.group_type]['count'] += 1
            by_type[group.group_type]['savings'] += group.savings
        
        return {
            'total_groups': total_groups,
            'total_duplicates': total_duplicates,
            'total_savings': total_savings,
            'by_type': by_type,
        }
