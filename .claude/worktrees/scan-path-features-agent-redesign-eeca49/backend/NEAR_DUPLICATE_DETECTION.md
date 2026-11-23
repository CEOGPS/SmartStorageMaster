# Near-Duplicate Image Detection Implementation

## Overview

This document describes the near-duplicate image detection system using perceptual hashing (pHash) with Hamming distance thresholds.

## Components

### 1. ImageHasher (Static Methods)

Provides three perceptual hashing algorithms:

#### `compute_phash(image_path)`
- **Algorithm**: Perceptual Hash using Discrete Cosine Transform (DCT)
- **Robustness**: Tolerant to scaling, rotation, and compression
- **Hash Size**: 64-bit
- **Best for**: General-purpose duplicate detection
- **Returns**: 16-character hex string

```python
from app.ai.image_hash import ImageHasher
hash_value = ImageHasher.compute_phash(Path("image.jpg"))
```

#### `compute_dhash(image_path)`
- **Algorithm**: Difference Hash
- **Robustness**: Good for detecting resized images
- **Hash Size**: 64-bit
- **Best for**: Detecting scaled versions of images
- **Returns**: 16-character hex string

#### `compute_ahash(image_path)`
- **Algorithm**: Average Hash
- **Robustness**: Fast, good for exact duplicates
- **Hash Size**: 64-bit
- **Best for**: Quick approximate matching
- **Returns**: 16-character hex string

### 2. Hamming Distance Calculation

#### `hamming_distance(hash1, hash2)`
Compares two hashes bit-by-bit:
- **Range**: 0-64
- **0**: Identical images
- **1-5**: Near-duplicates (92-100% similar)
- **6-10**: Similar images (84-92% similar)
- **11-16**: Related images (75-84% similar)
- **17+**: Different images

```python
from app.ai.image_hash import ImageHasher

hash1 = ImageHasher.compute_phash(Path("image1.jpg"))
hash2 = ImageHasher.compute_phash(Path("image2.jpg"))

distance = ImageHasher.hamming_distance(hash1, hash2)
similarity = ImageHasher.similarity_score(hash1, hash2)

print(f"Distance: {distance}, Similarity: {similarity:.1%}")
```

### 3. NearDuplicateDetector

High-performance detector for finding near-duplicates using pHash.

#### Initialization

```python
from app.ai.image_hash import NearDuplicateDetector

# Create detector with Hamming threshold of 5 (strict)
detector = NearDuplicateDetector(hamming_threshold=5)
```

**Hamming Threshold Guidelines**:

| Threshold | Similarity | Use Case |
|-----------|-----------|----------|
| 0-2 | 97-100% | Exact/nearly identical |
| 3-5 | 92-97% | Near-duplicates (strict) |
| 6-8 | 88-92% | Similar images (moderate) |
| 9-12 | 81-88% | Related images (loose) |
| 13+ | <81% | Very loose matching |

#### Adding Images

```python
# Add single image
success = detector.add_image(Path("image.jpg"))

# Add multiple images
for path in image_paths:
    detector.add_image(path)
```

#### Finding Duplicates

```python
# Find all near-duplicates for a query image
duplicates = detector.find_duplicates(Path("query.jpg"))

for dup_path, distance, similarity in duplicates:
    print(f"{dup_path}: distance={distance}, similarity={similarity:.1%}")
```

Returns list of tuples: `(path, hamming_distance, similarity_score)`

#### Finding All Duplicate Groups

```python
# Find all duplicate groups in the detector
groups = detector.find_all_duplicate_groups()

for group in groups:
    primary_path, _, _ = group[0]
    print(f"Primary: {primary_path}")
    for dup_path, distance, similarity in group[1:]:
        print(f"  → {dup_path} (distance={distance}, similarity={similarity:.1%})")
```

#### Statistics

```python
stats = detector.get_statistics()
print(f"Total images: {stats['total_images']}")
print(f"Duplicate groups: {stats['duplicate_groups']}")
print(f"Total duplicates: {stats['total_duplicates']}")
print(f"Hamming threshold: {stats['hamming_threshold']}")
```

### 4. ImageHashDatabase

Multi-algorithm database for comprehensive duplicate detection.

#### Initialization

```python
from app.ai.image_hash import ImageHashDatabase

# Create with 85% similarity threshold
db = ImageHashDatabase(similarity_threshold=0.85)
```

#### Adding Images

Single image:
```python
db.add_image(Path("image.jpg"))
```

Batch operation:
```python
stats = db.add_images_batch(image_paths)
print(f"Added: {stats['added']}, Failed: {stats['failed']}")
```

#### Finding Similar Images

```python
# Find similar images to a query
similar = db.find_similar(Path("query.jpg"))

for similar_path, score in similar:
    print(f"{similar_path}: {score:.1%} similar")
```

#### Finding Similar Groups

```python
# Find all groups of similar images
groups = db.find_all_similar_groups()

for group in groups:
    print(f"Group size: {len(group)}")
    for path, score in group:
        print(f"  {path}: {score:.1%}")
```

#### Statistics

```python
stats = db.get_database_statistics()
print(f"Total images: {stats['total_images']}")
print(f"Similar groups: {stats['similar_groups']}")
print(f"Total similar: {stats['total_similar']}")
```

## Usage Examples

### Example 1: Find Near-Duplicates in a Folder

```python
from pathlib import Path
from app.ai.image_hash import NearDuplicateDetector

detector = NearDuplicateDetector(hamming_threshold=5)

# Scan folder
image_folder = Path("./images")
for image_file in image_folder.glob("**/*.jpg"):
    detector.add_image(image_file)

# Find all duplicate groups
groups = detector.find_all_duplicate_groups()
print(f"Found {len(groups)} duplicate groups")

for group in groups:
    print(f"\nGroup with {len(group)} images:")
    for path, distance, similarity in group:
        print(f"  {path.name}: {similarity:.1%} similar")
```

### Example 2: Compare Two Images

```python
from app.ai.image_hash import ImageHasher

path1 = Path("original.jpg")
path2 = Path("copy.jpg")

hash1 = ImageHasher.compute_phash(path1)
hash2 = ImageHasher.compute_phash(path2)

distance = ImageHasher.hamming_distance(hash1, hash2)
similarity = ImageHasher.similarity_score(hash1, hash2)

if distance <= 5:
    print(f"These are near-duplicates! Similarity: {similarity:.1%}")
else:
    print(f"Different images. Similarity: {similarity:.1%}")
```

### Example 3: Batch Processing

```python
from app.ai.image_hash import ImageHashDatabase

db = ImageHashDatabase(similarity_threshold=0.85)

# Add many images
image_paths = list(Path("./images").glob("**/*.jpg"))
stats = db.add_images_batch(image_paths)
print(f"Added {stats['added']} images, {stats['failed']} failed")

# Get all similar groups
groups = db.find_all_similar_groups()
print(f"Found {len(groups)} similar image groups")
```

## Algorithm Details

### Perceptual Hash (pHash)

1. Resize image to 32×32 pixels
2. Convert to grayscale
3. Compute 2D Discrete Cosine Transform (DCT)
4. Reduce to 8×8 coefficient matrix
5. Calculate average of coefficients
6. Create 64-bit hash: 1 if coefficient >= average, 0 otherwise

**Advantages**:
- Robust to compression, scaling, and rotation
- Good for finding similar/modified versions
- Standard algorithm in image forensics

### Hamming Distance

Compares bit-by-bit differences between two hashes:
- Count the number of positions where bits differ
- Range: 0 (identical) to 64 (completely different)
- Used as similarity metric

**Interpretation**:
- Distance 0: Perfect duplicate
- Distance 1-5: Near-duplicates (minor edits)
- Distance 6-10: Similar images (possible edits)
- Distance 11+: Different images

## Performance Considerations

### Time Complexity

- **Hash computation**: O(n) where n = image pixels (independent of image size due to resize)
- **Hamming distance**: O(1) (comparing two 64-bit hashes)
- **Finding duplicates**: O(m) where m = database size
- **Finding all groups**: O(m²) worst case

### Memory Usage

- **Per image**: ~16 bytes (one hex hash) + small overhead
- **Database**: Linear with number of images
- **For 100k images**: ~2-5 MB in-memory

### Optimization Tips

1. **Batch processing**: Use `add_images_batch()` for multiple files
2. **Threshold tuning**: Use stricter thresholds for faster processing
3. **Pre-filtering**: Filter by file size before processing
4. **Parallel processing**: Hash computation is embarrassingly parallel

## Integration with Smart Storage Manager

The near-duplicate detector integrates with the duplicate service:

```python
# In duplicate_service.py
from app.ai.image_hash import NearDuplicateDetector

class DuplicateService:
    def __init__(self):
        self.image_detector = NearDuplicateDetector(hamming_threshold=5)
    
    def find_image_duplicates(self, scan_results):
        # Add all images from scan
        for file_meta in scan_results:
            if file_meta.mime_type and 'image' in file_meta.mime_type:
                self.image_detector.add_image(file_meta.path)
        
        # Get duplicate groups
        return self.image_detector.find_all_duplicate_groups()
```

## Troubleshooting

**Issue**: "Failed to compute pHash for image.jpg"
- **Cause**: Corrupted or unsupported image format
- **Solution**: Verify image is valid, supported formats: JPG, PNG, GIF, BMP, WebP, TIFF

**Issue**: No duplicates found with low Hamming threshold
- **Cause**: Images may have different content despite visual similarity
- **Solution**: Increase Hamming threshold or use multi-algorithm approach

**Issue**: Too many false positives
- **Cause**: Hamming threshold too high (too lenient)
- **Solution**: Decrease threshold value (increase strictness)
