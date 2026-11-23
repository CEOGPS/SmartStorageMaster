# Quick Reference: Near-Duplicate Image Detection

## Installation

No new packages needed! Already in `requirements.txt`:
- Pillow
- NumPy

## Import

```python
from app.ai.image_hash import NearDuplicateDetector, ImageHashDatabase, ImageHasher
from pathlib import Path
```

## Basic Usage (2 minutes)

```python
# Create detector with default threshold (5 = ~92% similar)
detector = NearDuplicateDetector()

# Add images
for img in Path("./photos").glob("**/*.jpg"):
    detector.add_image(img)

# Find all duplicate groups
groups = detector.find_all_duplicate_groups()

# Process results
for group in groups:
    print(f"Found {len(group)} similar images:")
    for path, distance, similarity in group:
        print(f"  {path}: {similarity:.1%} similar")
```

## Threshold Selection

| Hamming | Similarity | When to Use |
|---------|-----------|------------|
| 0-2 | 97-100% | Exact/nearly identical |
| **3-5** | **92-97%** | **← DEFAULT (best)** |
| 6-8 | 88-92% | Catch edited versions |
| 9-12 | 81-88% | Very loose matching |

```python
# Strict matching (only very similar)
strict = NearDuplicateDetector(hamming_threshold=2)

# Balanced (default, recommended)
balanced = NearDuplicateDetector(hamming_threshold=5)

# Loose matching (catch many variants)
loose = NearDuplicateDetector(hamming_threshold=8)
```

## Core Methods

### Add Image
```python
detector.add_image(Path("image.jpg"))  # Returns: True/False
```

### Find Duplicates (for specific image)
```python
duplicates = detector.find_duplicates(Path("query.jpg"))
# Returns: [(path1, distance, similarity), (path2, distance, similarity), ...]

for path, distance, similarity in duplicates:
    print(f"{path}: hamming_distance={distance}, similarity={similarity:.1%}")
```

### Find All Duplicate Groups
```python
groups = detector.find_all_duplicate_groups()
# Returns: [group1, group2, ...] where each group = [(path, distance, similarity), ...]

for group in groups:
    primary, *duplicates = group
    print(f"Primary: {primary[0]}")
    for dup_path, dist, sim in duplicates:
        print(f"  Duplicate: {dup_path} ({sim:.1%})")
```

### Get Statistics
```python
stats = detector.get_statistics()
print(f"Total images: {stats['total_images']}")
print(f"Duplicate groups: {stats['duplicate_groups']}")
print(f"Total duplicates: {stats['total_duplicates']}")
print(f"Threshold: {stats['hamming_threshold']}")
```

## Understanding Results

### Hamming Distance (0-64)
- **0**: Identical (same file or perfect copy)
- **1-5**: Near-duplicates (edited slightly: resize, compress, color adjust)
- **6-10**: Similar (edited more: crop, rotate, brightness/contrast)
- **11+**: Different (substantially different)

### Similarity Score (0.0-1.0)
- **1.0**: Identical
- **0.92**: Very similar (distance=5, default threshold)
- **0.84**: Similar (distance=10)
- **0.0**: Completely different

## Common Patterns

### Find Duplicates in Folder
```python
detector = NearDuplicateDetector(hamming_threshold=5)

# Add all images
root = Path("./my_photos")
for img in root.glob("**/*.jpg"):
    detector.add_image(img)

# Get all groups
groups = detector.find_all_duplicate_groups()
print(f"Found {len(groups)} duplicate groups")
```

### Compare Two Images
```python
path1 = Path("original.jpg")
path2 = Path("edited.jpg")

hash1 = ImageHasher.compute_phash(path1)
hash2 = ImageHasher.compute_phash(path2)

distance = ImageHasher.hamming_distance(hash1, hash2)
similarity = ImageHasher.similarity_score(hash1, hash2)

if distance <= 5:
    print(f"These are near-duplicates! Similarity: {similarity:.1%}")
```

### Filter Groups by Size
```python
groups = detector.find_all_duplicate_groups()

# Get groups with at least 3 duplicates
large_groups = [g for g in groups if len(g) >= 3]

for group in large_groups:
    print(f"Group with {len(group)} images:")
    for path, dist, sim in group:
        size_mb = path.stat().st_size / (1024*1024)
        print(f"  {path.name}: {size_mb:.1f} MB")
```

### Calculate Cleanup Potential
```python
def get_cleanup_size(group):
    """How much space could be freed from this group"""
    total = 0
    
    # Sort by size, keep only the largest
    files = [(p, p.stat().st_size) for p, _, _ in group]
    files.sort(key=lambda x: x[1], reverse=True)
    
    # Sum all except largest
    return sum(size for _, size in files[1:])

groups = detector.find_all_duplicate_groups()
total_cleanup = sum(get_cleanup_size(g) for g in groups)
print(f"Can cleanup: {total_cleanup / (1024*1024):.1f} MB")
```

## Using Multi-Algorithm Database

```python
from app.ai.image_hash import ImageHashDatabase

# Create with similarity threshold (0.0-1.0)
db = ImageHashDatabase(similarity_threshold=0.85)

# Add images (computes all three hashes)
db.add_image(Path("image.jpg"))

# Or batch add
paths = list(Path("./photos").glob("**/*.jpg"))
stats = db.add_images_batch(paths)
print(f"Added {stats['added']} images, {stats['failed']} failed")

# Find similar
similar = db.find_similar(Path("query.jpg"))
for path, score in similar:
    print(f"{path}: {score:.1%} similar")

# Find all groups
groups = db.find_all_similar_groups()

# Statistics
stats = db.get_database_statistics()
print(f"Similar groups: {stats['similar_groups']}")
```

## Error Handling

```python
from pathlib import Path
from app.ai.image_hash import NearDuplicateDetector

detector = NearDuplicateDetector(hamming_threshold=5)

# Invalid threshold
try:
    bad = NearDuplicateDetector(hamming_threshold=100)
except ValueError as e:
    print(f"Error: {e}")  # hamming_threshold must be between 0 and 64

# Invalid file
success = detector.add_image(Path("not_exists.jpg"))
print(success)  # False

# Non-image file
success = detector.add_image(Path("document.pdf"))
print(success)  # False
```

## Performance Tips

1. **Pre-filter by file size** - Skip files that are obviously different
2. **Use stricter threshold for speed** - Lower threshold = faster (fewer comparisons)
3. **Process in batches** - Add many images before searching
4. **Parallel processing** - Hash computation is embarrassingly parallel (future enhancement)

## Files and Documentation

- **Code**: `backend/app/ai/image_hash.py` (434 lines)
- **Integration**: `backend/image_duplicate_integration.py` (examples)
- **Tests**: `backend/test_image_hash.py` (test suite)
- **Full Docs**: `backend/NEAR_DUPLICATE_DETECTION.md`
- **Comparison**: `backend/PHASH_COMPARISON.md` (vs other methods)

## Algorithm: pHash (Perceptual Hash)

1. Resize image to 32×32
2. Convert to grayscale
3. Apply DCT (Discrete Cosine Transform)
4. Take 8×8 coefficient matrix
5. Hash: 1 if coefficient ≥ average, else 0
6. Result: 64-bit binary string (16 hex chars)

**Why pHash?**
- ✓ Fast (~20ms per image)
- ✓ Robust to compression, scaling, rotation
- ✓ Simple (just compare hashes)
- ✓ Standard (used in forensics)
- ✓ No special hardware needed

## Troubleshooting

**Q: No duplicates found?**
- Try increasing threshold: `NearDuplicateDetector(hamming_threshold=8)`
- Check that images are actually similar

**Q: Too many false positives?**
- Lower threshold: `NearDuplicateDetector(hamming_threshold=2)`
- Use multi-algorithm database instead: `ImageHashDatabase(similarity_threshold=0.92)`

**Q: How fast is it?**
- Hash computation: 10-50ms per image
- Comparison: <1μs per pair
- 100k images: ~30 minutes to hash, then instant comparisons

**Q: How much memory?**
- ~16 bytes per image hash
- 100k images ≈ 2-5 MB
- Very efficient!

---

**Next Steps**: See `NEAR_DUPLICATE_DETECTION.md` for comprehensive documentation.
