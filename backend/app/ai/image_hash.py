"""
Image hashing module for perceptual duplicate detection
"""
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import logging

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    Image = None

import numpy as np

logger = logging.getLogger(__name__)

# Image extensions to process
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}


class ImageHasher:
    """Compute perceptual hashes for images"""
    
    # Hash size (lower = faster but less accurate)
    HASH_SIZE = 8
    
    @staticmethod
    def compute_phash(image_path: Path) -> Optional[str]:
        """
        Compute Perceptual Hash (pHash)
        
        Uses Discrete Cosine Transform to create hash robust to scaling/rotation
        
        Args:
            image_path: Path to image file
        
        Returns:
            64-bit hex hash string or None if image is unreadable or Pillow unavailable
        """
        if not PILLOW_AVAILABLE:
            logger.warning("Pillow not installed. Image hashing disabled. Install pillow to enable image duplicate detection.")
            return None
        
        try:
            img = Image.open(image_path).convert('L')  # Convert to grayscale
            img = img.resize((32, 32), Image.Resampling.LANCZOS)
            
            pixels = np.array(img, dtype=np.float32)
            
            # Simplified DCT (Discrete Cosine Transform)
            dct = np.abs(np.fft.fft2(pixels))
            dct_reduced = dct[:8, :8]
            
            # Calculate average
            avg = dct_reduced.mean()
            
            # Create hash
            hash_bits = ''.join('1' if pixel >= avg else '0' 
                              for pixel in dct_reduced.flatten())
            return hex(int(hash_bits, 2))[2:].zfill(16)
        
        except Exception as e:
            logger.warning(f"Failed to compute pHash for {image_path}: {e}")
            return None
    
    @staticmethod
    def compute_dhash(image_path: Path) -> Optional[str]:
        """
        Compute Difference Hash (dHash)
        
        Compares adjacent pixels to create hash
        
        Args:
            image_path: Path to image file
        
        Returns:
            64-bit hex hash string or None
        """
        try:
            img = Image.open(image_path).convert('L')
            img = img.resize((9, 8), Image.Resampling.LANCZOS)
            
            pixels = np.array(img, dtype=np.float32)
            
            # Compute differences between adjacent pixels
            diff = pixels[:, 1:] > pixels[:, :-1]
            hash_bits = ''.join('1' if d else '0' for d in diff.flatten())
            
            return hex(int(hash_bits, 2))[2:].zfill(16)
        
        except Exception as e:
            logger.warning(f"Failed to compute dHash for {image_path}: {e}")
            return None
    
    @staticmethod
    def compute_ahash(image_path: Path) -> Optional[str]:
        """
        Compute Average Hash (aHash)
        
        Compares pixels to average value
        
        Args:
            image_path: Path to image file
        
        Returns:
            64-bit hex hash string or None
        """
        try:
            img = Image.open(image_path).convert('L')
            img = img.resize((8, 8), Image.Resampling.LANCZOS)
            
            pixels = np.array(img, dtype=np.float32)
            avg = pixels.mean()
            
            # Hash based on comparison to average
            hash_bits = ''.join('1' if pixel >= avg else '0' 
                              for pixel in pixels.flatten())
            return hex(int(hash_bits, 2))[2:].zfill(16)
        
        except Exception as e:
            logger.warning(f"Failed to compute aHash for {image_path}: {e}")
            return None
    
    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        """
        Calculate Hamming distance between two hashes
        
        Args:
            hash1: First hash (hex string)
            hash2: Second hash (hex string)
        
        Returns:
            Hamming distance (0-64)
        """
        try:
            # Convert hex to binary
            bin1 = bin(int(hash1, 16))[2:].zfill(64)
            bin2 = bin(int(hash2, 16))[2:].zfill(64)
            
            # Count differences
            return sum(b1 != b2 for b1, b2 in zip(bin1, bin2))
        
        except (ValueError, TypeError):
            return 999  # Max distance for invalid hashes
    
    @staticmethod
    def similarity_score(hash1: str, hash2: str) -> float:
        """
        Calculate similarity score between two hashes
        
        Args:
            hash1: First hash
            hash2: Second hash
        
        Returns:
            Similarity score (0.0-1.0, where 1.0 = identical)
        """
        distance = ImageHasher.hamming_distance(hash1, hash2)
        return max(0.0, (64 - distance) / 64.0)


class NearDuplicateDetector:
    """Detect near-duplicate images using pHash with Hamming distance threshold"""
    
    # Default Hamming distance thresholds (0-64)
    # Lower = stricter matching, higher = looser matching
    DEFAULT_HAMMING_THRESHOLD = 5  # ~92% similarity
    
    def __init__(self, hamming_threshold: int = DEFAULT_HAMMING_THRESHOLD):
        """
        Initialize near-duplicate detector
        
        Args:
            hamming_threshold: Hamming distance threshold for considering images duplicates
                             (0-64, where 0 = identical, 64 = completely different)
        """
        if not 0 <= hamming_threshold <= 64:
            raise ValueError("hamming_threshold must be between 0 and 64")
        
        self.hamming_threshold = hamming_threshold
        self.image_hashes: Dict[Path, str] = {}  # path -> phash
    
    def add_image(self, image_path: Path) -> bool:
        """
        Add image to detector and compute pHash
        
        Args:
            image_path: Path to image file
        
        Returns:
            True if successfully added, False if file is unreadable
        """
        if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            return False
        
        if image_path in self.image_hashes:
            return True
        
        phash = ImageHasher.compute_phash(image_path)
        if not phash:
            return False
        
        self.image_hashes[image_path] = phash
        return True
    
    def find_duplicates(self, image_path: Path) -> List[Tuple[Path, int, float]]:
        """
        Find near-duplicate images using Hamming distance
        
        Args:
            image_path: Path to query image
        
        Returns:
            List of (path, hamming_distance, similarity_score) tuples, sorted by similarity
        """
        if image_path not in self.image_hashes:
            self.add_image(image_path)
        
        if image_path not in self.image_hashes:
            return []
        
        query_hash = self.image_hashes[image_path]
        duplicates = []
        
        for db_image_path, db_hash in self.image_hashes.items():
            if db_image_path == image_path:
                continue
            
            distance = ImageHasher.hamming_distance(query_hash, db_hash)
            
            if distance <= self.hamming_threshold:
                similarity = ImageHasher.similarity_score(query_hash, db_hash)
                duplicates.append((db_image_path, distance, similarity))
        
        # Sort by distance ascending (most similar first)
        return sorted(duplicates, key=lambda x: x[1])
    
    def find_all_duplicate_groups(self) -> List[List[Tuple[Path, int, float]]]:
        """
        Find all duplicate groups in the database
        
        Returns:
            List of duplicate groups, where each group is a list of tuples
            (path, hamming_distance_to_primary, similarity_score)
        """
        if not self.image_hashes:
            return []
        
        visited = set()
        groups = []
        
        for image_path in self.image_hashes.keys():
            if image_path in visited:
                continue
            
            duplicates = self.find_duplicates(image_path)
            
            if duplicates:
                # Create group with primary image
                group = [(image_path, 0, 1.0)]
                group.extend(duplicates)
                groups.append(group)
                
                # Mark all as visited
                visited.add(image_path)
                for dup_path, _, _ in duplicates:
                    visited.add(dup_path)
        
        # Filter out single-image "groups"
        return [g for g in groups if len(g) > 1]
    
    def get_statistics(self) -> Dict:
        """
        Get detector statistics
        
        Returns:
            Dictionary with statistics
        """
        groups = self.find_all_duplicate_groups()
        total_duplicates = sum(len(g) - 1 for g in groups)
        
        return {
            'total_images': len(self.image_hashes),
            'duplicate_groups': len(groups),
            'total_duplicates': total_duplicates,
            'hamming_threshold': self.hamming_threshold,
        }


class ImageHashDatabase:
    """In-memory image hash database for efficient duplicate finding"""
    
    def __init__(self, similarity_threshold: float = 0.85):
        """
        Initialize image hash database
        
        Args:
            similarity_threshold: Threshold for considering images similar (0.0-1.0)
        """
        self.hashes: Dict[Path, Dict[str, str]] = {}  # path -> {algorithm -> hash}
        self.similarity_threshold = similarity_threshold
    
    def add_image(self, image_path: Path) -> bool:
        """
        Add image to database with all hash algorithms
        
        Args:
            image_path: Path to image file
        
        Returns:
            True if successfully added, False if file is unreadable
        """
        if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            return False
        
        if image_path in self.hashes:
            return True  # Already in database
        
        phash = ImageHasher.compute_phash(image_path)
        dhash = ImageHasher.compute_dhash(image_path)
        ahash = ImageHasher.compute_ahash(image_path)
        
        if not any([phash, dhash, ahash]):
            return False
        
        self.hashes[image_path] = {
            'phash': phash or '',
            'dhash': dhash or '',
            'ahash': ahash or '',
        }
        
        return True
    
    def find_similar(self, image_path: Path) -> List[Tuple[Path, float]]:
        """
        Find similar images in database
        
        Args:
            image_path: Path to query image
        
        Returns:
            List of (path, similarity_score) tuples, sorted by similarity
        """
        if image_path not in self.hashes:
            self.add_image(image_path)
        
        if image_path not in self.hashes:
            return []
        
        query_hashes = self.hashes[image_path]
        similar_images = []
        
        for db_image_path, db_hashes in self.hashes.items():
            if db_image_path == image_path:
                continue
            
            # Use average similarity across all algorithms
            scores = []
            for algorithm in ['phash', 'dhash', 'ahash']:
                if query_hashes[algorithm] and db_hashes[algorithm]:
                    score = ImageHasher.similarity_score(
                        query_hashes[algorithm],
                        db_hashes[algorithm]
                    )
                    scores.append(score)
            
            if scores:
                avg_score = sum(scores) / len(scores)
                if avg_score >= self.similarity_threshold:
                    similar_images.append((db_image_path, avg_score))
        
        # Sort by similarity descending
        return sorted(similar_images, key=lambda x: x[1], reverse=True)    
    def add_images_batch(self, image_paths: List[Path]) -> Dict[str, int]:
        """
        Add multiple images to database in batch
        
        Args:
            image_paths: List of paths to image files
        
        Returns:
            Dictionary with statistics: {total: int, added: int, failed: int}
        """
        stats = {'total': len(image_paths), 'added': 0, 'failed': 0}
        
        for image_path in image_paths:
            if self.add_image(image_path):
                stats['added'] += 1
            else:
                stats['failed'] += 1
        
        return stats
    
    def find_all_similar_groups(self) -> List[List[Tuple[Path, float]]]:
        """
        Find all groups of similar images in database
        
        Returns:
            List of similar image groups, sorted by group size
        """
        if not self.hashes:
            return []
        
        visited = set()
        groups = []
        
        for image_path in self.hashes.keys():
            if image_path in visited:
                continue
            
            similar = self.find_similar(image_path)
            
            if similar:
                # Create group with query image as primary
                group = [(image_path, 1.0)]
                group.extend(similar)
                groups.append(group)
                
                # Mark all as visited
                visited.add(image_path)
                for sim_path, _ in similar:
                    visited.add(sim_path)
        
        # Sort by group size (largest first)
        return sorted(groups, key=len, reverse=True)
    
    def get_database_statistics(self) -> Dict:
        """
        Get comprehensive database statistics
        
        Returns:
            Dictionary with statistics
        """
        groups = self.find_all_similar_groups()
        total_similar = sum(len(g) - 1 for g in groups)
        
        return {
            'total_images': len(self.hashes),
            'similar_groups': len(groups),
            'total_similar': total_similar,
            'similarity_threshold': self.similarity_threshold,
        }