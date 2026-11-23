#!/usr/bin/env python3
"""
Test script for image hashing and near-duplicate detection
"""
from pathlib import Path
from app.ai.image_hash import ImageHasher, NearDuplicateDetector, ImageHashDatabase

def test_near_duplicate_detector():
    """Test NearDuplicateDetector with various Hamming thresholds"""
    
    print("=" * 60)
    print("Testing NearDuplicateDetector")
    print("=" * 60)
    
    # Create detector with Hamming distance threshold of 5 (strict)
    detector = NearDuplicateDetector(hamming_threshold=5)
    
    print(f"\nDetector initialized with Hamming threshold: {detector.hamming_threshold}")
    print("Hamming distance interpretation:")
    print("  0   = Identical")
    print("  1-5 = Near-duplicates (92-100% similar)")
    print("  6-10 = Similar (84-92% similar)")
    print("  11+  = Different")
    
    # Example: Find duplicate statistics
    stats = detector.get_statistics()
    print(f"\nDetector Statistics:")
    print(f"  Total images in detector: {stats['total_images']}")
    print(f"  Duplicate groups found: {stats['duplicate_groups']}")
    print(f"  Total duplicates: {stats['total_duplicates']}")


def test_hamming_distance():
    """Test Hamming distance calculations"""
    
    print("\n" + "=" * 60)
    print("Testing Hamming Distance Calculations")
    print("=" * 60)
    
    # Example hashes (binary representation)
    hash1 = "f" * 16  # All 1s in binary
    hash2 = "0" * 16  # All 0s in binary
    
    distance = ImageHasher.hamming_distance(hash1, hash2)
    similarity = ImageHasher.similarity_score(hash1, hash2)
    
    print(f"\nHash 1 (hex): {hash1}")
    print(f"Hash 2 (hex): {hash2}")
    print(f"Hamming Distance: {distance}")
    print(f"Similarity Score: {similarity:.2%}")
    
    # Example with similar hashes
    hash3 = "e" * 16  # Almost all 1s
    distance2 = ImageHasher.hamming_distance(hash1, hash3)
    similarity2 = ImageHasher.similarity_score(hash1, hash3)
    
    print(f"\nHash 1 (hex): {hash1}")
    print(f"Hash 3 (hex): {hash3}")
    print(f"Hamming Distance: {distance2}")
    print(f"Similarity Score: {similarity2:.2%}")


def test_threshold_tuning():
    """Show how different Hamming thresholds affect duplicate detection"""
    
    print("\n" + "=" * 60)
    print("Hamming Threshold Tuning Guide")
    print("=" * 60)
    
    thresholds = [2, 5, 8, 12, 16, 20]
    
    print("\nRecommended thresholds by use case:")
    print("  Threshold  | Similarity Range | Use Case")
    print("  -----------+--------------+-----------")
    
    for threshold in thresholds:
        similarity_min = (64 - threshold) / 64.0 * 100
        similarity_max = 100
        print(f"  {threshold:2d}         | {similarity_min:5.1f}% - {similarity_max:5.1f}% | ", end="")
        
        if threshold <= 2:
            print("Exact/nearly identical (very strict)")
        elif threshold <= 5:
            print("Near-duplicates (strict)")
        elif threshold <= 10:
            print("Similar images (moderate)")
        elif threshold <= 16:
            print("Related images (loose)")
        else:
            print("Very loose matching")


def test_image_hash_database():
    """Test ImageHashDatabase batch operations"""
    
    print("\n" + "=" * 60)
    print("Testing ImageHashDatabase")
    print("=" * 60)
    
    # Create database with 85% similarity threshold
    db = ImageHashDatabase(similarity_threshold=0.85)
    
    print(f"\nDatabase initialized with similarity threshold: {db.similarity_threshold:.0%}")
    
    # Example statistics
    stats = db.get_database_statistics()
    print(f"\nDatabase Statistics:")
    print(f"  Total images: {stats['total_images']}")
    print(f"  Similar groups found: {stats['similar_groups']}")
    print(f"  Total similar images: {stats['total_similar']}")


if __name__ == "__main__":
    test_near_duplicate_detector()
    test_hamming_distance()
    test_threshold_tuning()
    test_image_hash_database()
    
    print("\n" + "=" * 60)
    print("Testing complete!")
    print("=" * 60)
