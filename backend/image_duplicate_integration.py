"""
Integration examples for near-duplicate image detection with Smart Storage Manager
"""
from pathlib import Path
from typing import List, Dict
from app.ai.image_hash import NearDuplicateDetector, ImageHashDatabase
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ImageDuplicateAnalyzer:
    """
    Analyzes image duplicates and generates reports for cleanup
    """
    
    def __init__(self, hamming_threshold: int = 5):
        """
        Initialize analyzer with near-duplicate detector
        
        Args:
            hamming_threshold: Hamming distance threshold (lower = stricter)
        """
        self.detector = NearDuplicateDetector(hamming_threshold=hamming_threshold)
        self.logger = logging.getLogger(__name__)
    
    def scan_directory(self, root_path: Path) -> Dict:
        """
        Scan directory for image duplicates
        
        Args:
            root_path: Root directory to scan
        
        Returns:
            Dictionary with analysis results
        """
        self.logger.info(f"Starting image duplicate scan: {root_path}")
        
        # Find all images
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}
        image_files = []
        
        for ext in image_extensions:
            image_files.extend(root_path.glob(f"**/*{ext}"))
            image_files.extend(root_path.glob(f"**/*{ext.upper()}"))
        
        # Add to detector
        added_count = 0
        for image_path in image_files:
            if self.detector.add_image(image_path):
                added_count += 1
        
        self.logger.info(f"Added {added_count} images to detector")
        
        # Find duplicates
        duplicate_groups = self.detector.find_all_duplicate_groups()
        
        # Calculate statistics
        total_duplicate_files = sum(len(group) - 1 for group in duplicate_groups)
        potential_savings = self._calculate_savings(duplicate_groups)
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'root_path': str(root_path),
            'total_images_scanned': len(image_files),
            'images_processed': added_count,
            'duplicate_groups': len(duplicate_groups),
            'total_duplicate_files': total_duplicate_files,
            'potential_savings_bytes': potential_savings,
            'hamming_threshold': self.detector.hamming_threshold,
            'groups': self._format_groups(duplicate_groups),
        }
        
        return results
    
    def _calculate_savings(self, groups: List) -> int:
        """Calculate potential space savings (keep largest, delete others)"""
        total = 0
        for group in groups:
            # Sort by file size (largest first)
            files_with_sizes = []
            for file_path, _, _ in group:
                try:
                    size = file_path.stat().st_size
                    files_with_sizes.append((file_path, size))
                except OSError:
                    continue
            
            if len(files_with_sizes) > 1:
                # Sort and keep largest
                sorted_files = sorted(files_with_sizes, key=lambda x: x[1], reverse=True)
                # Sum all but the largest
                total += sum(size for _, size in sorted_files[1:])
        
        return total
    
    def _format_groups(self, groups: List) -> List[Dict]:
        """Format duplicate groups for output"""
        formatted = []
        
        for group_idx, group in enumerate(groups, 1):
            group_dict = {
                'group_id': group_idx,
                'size': len(group),
                'images': []
            }
            
            for image_path, distance, similarity in group:
                try:
                    size_bytes = image_path.stat().st_size
                    size_mb = size_bytes / (1024 * 1024)
                except OSError:
                    size_bytes = 0
                    size_mb = 0
                
                group_dict['images'].append({
                    'path': str(image_path),
                    'hamming_distance': distance,
                    'similarity': f"{similarity:.1%}",
                    'size_mb': f"{size_mb:.2f}",
                    'is_primary': distance == 0,
                })
            
            formatted.append(group_dict)
        
        return formatted
    
    def generate_report(self, results: Dict) -> str:
        """Generate human-readable report"""
        report = []
        report.append("=" * 70)
        report.append("IMAGE DUPLICATE DETECTION REPORT")
        report.append("=" * 70)
        report.append(f"\nScan Date: {results['timestamp']}")
        report.append(f"Directory: {results['root_path']}")
        report.append(f"Hamming Threshold: {results['hamming_threshold']} (0-64)")
        
        report.append("\n" + "-" * 70)
        report.append("SUMMARY")
        report.append("-" * 70)
        report.append(f"Total Images Scanned: {results['total_images_scanned']}")
        report.append(f"Images Processed: {results['images_processed']}")
        report.append(f"Duplicate Groups Found: {results['duplicate_groups']}")
        report.append(f"Total Duplicate Files: {results['total_duplicate_files']}")
        
        savings_mb = results['potential_savings_bytes'] / (1024 * 1024)
        report.append(f"Potential Savings: {savings_mb:.2f} MB")
        
        report.append("\n" + "-" * 70)
        report.append("DUPLICATE GROUPS")
        report.append("-" * 70)
        
        for group in results['groups']:
            report.append(f"\nGroup {group['group_id']} ({group['size']} images):")
            
            for img in group['images']:
                marker = "[PRIMARY]" if img['is_primary'] else "[DUPLICATE]"
                report.append(f"  {marker} {img['path']}")
                report.append(f"       Size: {img['size_mb']} MB, Similarity: {img['similarity']}")
        
        report.append("\n" + "=" * 70)
        return "\n".join(report)


class DuplicateCleanupHelper:
    """
    Helps identify and organize files for cleanup
    """
    
    @staticmethod
    def get_files_to_delete(group: List[tuple]) -> List[Path]:
        """
        Get files to delete from a duplicate group (keep largest)
        
        Args:
            group: List of (path, hamming_distance, similarity) tuples
        
        Returns:
            List of file paths to delete (all but largest)
        """
        # Sort by file size
        files_with_sizes = []
        for file_path, _, _ in group:
            try:
                size = file_path.stat().st_size
                files_with_sizes.append((file_path, size))
            except OSError:
                continue
        
        if not files_with_sizes:
            return []
        
        # Sort by size, keep largest
        sorted_files = sorted(files_with_sizes, key=lambda x: x[1], reverse=True)
        return [f[0] for f in sorted_files[1:]]
    
    @staticmethod
    def organize_by_similarity(group: List[tuple]) -> Dict[str, List[Path]]:
        """
        Organize duplicate group by similarity levels
        
        Args:
            group: List of (path, hamming_distance, similarity) tuples
        
        Returns:
            Dictionary organized by similarity level
        """
        organized = {
            'identical': [],      # distance 0
            'near_duplicate': [], # distance 1-3
            'similar': [],        # distance 4-8
            'related': [],        # distance 9+
        }
        
        for file_path, distance, _ in group:
            if distance == 0:
                organized['identical'].append(file_path)
            elif distance <= 3:
                organized['near_duplicate'].append(file_path)
            elif distance <= 8:
                organized['similar'].append(file_path)
            else:
                organized['related'].append(file_path)
        
        # Remove empty categories
        return {k: v for k, v in organized.items() if v}


# Example usage
if __name__ == "__main__":
    import json
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Scan directory
    analyzer = ImageDuplicateAnalyzer(hamming_threshold=5)
    results = analyzer.scan_directory(Path("./test_images"))
    
    # Print report
    print(analyzer.generate_report(results))
    
    # Save JSON results
    with open("duplicate_analysis.json", "w") as f:
        json.dump(results, f, indent=2)
    
    # Show cleanup suggestions
    print("\n" + "=" * 70)
    print("CLEANUP SUGGESTIONS")
    print("=" * 70)
    
    for group in results['groups']:
        images = [Path(img['path']) for img in group['images']]
        to_delete = DuplicateCleanupHelper.get_files_to_delete(
            [(p, 0, 1.0) for p in images]  # Simplified for demo
        )
        
        if to_delete:
            print(f"\nGroup {group['group_id']}: Can delete {len(to_delete)} file(s)")
            for file_path in to_delete:
                print(f"  - {file_path}")
