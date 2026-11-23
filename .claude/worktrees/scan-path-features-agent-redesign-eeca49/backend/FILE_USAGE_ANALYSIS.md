# File Usage Analysis Implementation

## Overview

Comprehensive file usage analysis system that categorizes files based on access patterns and provides intelligent cleanup recommendations.

**Features:**
- Analyzes file usage based on access time, modification time, and file size
- Categorizes files into RECENTLY_USED, RARELY_USED, and NOT_USED
- Calculates intelligent cleanup priority scores
- Configurable thresholds via REST API
- Cross-platform support (Windows, macOS, Linux)
- Memory-efficient with support for large directories

## Architecture

### Core Module: `app/core/usage_analyzer.py`

**UsageAnalyzer Class** - Computes file usage metadata

```python
analyzer = UsageAnalyzer(
    recently_used_days=30,      # 0-30 days
    rarely_used_days=180,       # 31-180 days
    not_used_days=180,          # 180+ days
    min_priority_size_mb=100,   # File size threshold for priority bonus
)

# Analyze single file
metadata = analyzer.analyze_file(Path("/path/to/file.txt"))

# Batch analysis
metadata_list = analyzer.batch_analyze(file_paths)

# Get cleanup candidates
candidates = analyzer.get_cleanup_candidates(
    metadata_list,
    min_priority=0.7,
    max_results=100
)
```

**UsageMetadata Class** - Container for file metadata
```python
@dataclass
class UsageMetadata:
    path: Path
    size: int
    created_at: datetime
    modified_at: datetime
    last_accessed: Optional[datetime]
    days_since_access: int
    usage_category: str              # RECENTLY_USED, RARELY_USED, NOT_USED
    usage_priority: float            # 0.0-1.0
```

### Service Layer: `app/services/usage_service.py`

**UsageService Class** - Business logic and database persistence

```python
service = UsageService(db_session=session)

# Get configuration
thresholds = service.get_thresholds()

# Update configuration
service.update_thresholds(
    recently_used_days=14,
    rarely_used_days=90,
    not_used_days=180,
)

# Analyze and store
service.analyze_and_store_usage(Path("/file.txt"))

# Get files by category
not_used = service.get_files_by_category(
    category="NOT_USED",
    limit=100,
    min_priority=0.7
)

# Get cleanup recommendations
recommendations = service.get_cleanup_recommendations(
    limit=100,
    min_priority=0.7
)

# Get summary
summary = service.get_usage_summary()
```

### API Layer: `app/api/usage_routes.py`

REST endpoints for usage analysis

## Usage Categories

### RECENTLY_USED
- **Range**: 0 to `recently_used_days` (default: 30 days)
- **Base Priority**: 0.1
- **Use Case**: Files actively in use
- **Action**: Keep

### RARELY_USED
- **Range**: `recently_used_days` + 1 to `rarely_used_days` (default: 30-180 days)
- **Base Priority**: 0.5
- **Use Case**: Files not frequently accessed
- **Action**: Review for cleanup

### NOT_USED
- **Range**: Over `not_used_days` (default: 180+ days)
- **Base Priority**: 0.9
- **Use Case**: Files untouched for extended period
- **Action**: Primary cleanup candidates

## Priority Score Calculation

Priority combines multiple factors:

```
Priority = Base_Score + Size_Bonus + Age_Bonus

Base_Score:
  - RECENTLY_USED: 0.1
  - RARELY_USED: 0.5
  - NOT_USED: 0.9

Size_Bonus:
  - +0.1 if file size >= min_priority_size_mb (default: 100 MB)

Age_Bonus (for NOT_USED only):
  - Increases from 0.0 to +0.1 as file age exceeds threshold
  - Older files = higher priority

Result: 0.0-1.0 (higher = higher cleanup priority)
```

### Example Priorities

| Category | Size | Days Since Access | Priority | Reason |
|----------|------|------------------|----------|--------|
| NOT_USED | 150 MB | 365 | 0.95 | Large, unused for 1+ year |
| NOT_USED | 50 MB | 200 | 0.85 | Medium, unused 6+ months |
| RARELY_USED | 200 MB | 120 | 0.60 | Large, rarely used |
| RARELY_USED | 10 MB | 60 | 0.50 | Small, rarely used |
| RECENTLY_USED | Any | <30 | 0.10 | Recently accessed |

## Database Schema Extensions

### File Model Fields Added
```sql
ALTER TABLE files ADD COLUMN last_accessed DATETIME;
ALTER TABLE files ADD COLUMN usage_category VARCHAR(50);
ALTER TABLE files ADD COLUMN days_since_access INT;
ALTER TABLE files ADD COLUMN usage_priority FLOAT;

CREATE INDEX idx_usage_category ON files(usage_category);
CREATE INDEX idx_usage_priority ON files(usage_priority);
CREATE INDEX idx_last_accessed ON files(last_accessed);
```

### UsageThreshold Model
```sql
CREATE TABLE usage_thresholds (
    id VARCHAR(36) PRIMARY KEY,
    recently_used_days INT DEFAULT 30,
    rarely_used_days INT DEFAULT 180,
    not_used_days INT DEFAULT 180,
    min_priority_size_mb INT DEFAULT 100,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## REST API Endpoints

### GET /api/usage/summary
Get overview of file usage statistics

**Response:**
```json
{
    "summary": {
        "RECENTLY_USED": {
            "count": 1500,
            "total_size_mb": 25000.0
        },
        "RARELY_USED": {
            "count": 250,
            "total_size_mb": 5000.0
        },
        "NOT_USED": {
            "count": 100,
            "total_size_mb": 8500.0
        }
    },
    "total_files": 1850,
    "total_size_mb": 38500.0,
    "potential_cleanup_mb": 12000.0,
    "thresholds": {
        "recently_used_days": 30,
        "rarely_used_days": 180,
        "not_used_days": 180,
        "min_priority_size_mb": 100
    }
}
```

### GET /api/usage/files
Get files by category

**Query Parameters:**
- `category` (required): RECENTLY_USED, RARELY_USED, or NOT_USED
- `limit` (optional): Maximum results
- `min_priority` (optional): Minimum priority score (0.0-1.0)

**Response:**
```json
[
    {
        "id": "file-id-1",
        "path": "/path/to/old_video.mp4",
        "name": "old_video.mp4",
        "size_mb": 2500.0,
        "usage_category": "NOT_USED",
        "usage_priority": 0.95,
        "days_since_access": 400,
        "last_accessed": "2023-01-15T10:30:00",
        "modified_at": "2023-01-15T10:30:00"
    }
]
```

### GET /api/usage/recommendations
Get prioritized cleanup recommendations

**Query Parameters:**
- `limit`: Maximum recommendations (default: 100)
- `min_priority`: Minimum priority threshold (default: 0.7)

**Response:**
```json
{
    "count": 45,
    "total_potential_cleanup_mb": 12000.0,
    "recommendations": [
        {
            "id": "file-id-1",
            "path": "/path/to/old_iso.iso",
            "name": "old_iso.iso",
            "size_mb": 4500.0,
            "usage_category": "NOT_USED",
            "priority": 0.98,
            "reason": "Not accessed for 400 days, Large file",
            "last_accessed": "2023-01-15T10:30:00"
        }
    ]
}
```

### GET /api/usage/file/{file_id}
Get detailed usage information for specific file

**Response:**
```json
{
    "id": "file-id-1",
    "path": "/path/to/file.txt",
    "name": "file.txt",
    "size_mb": 250.5,
    "created_at": "2023-01-01T10:30:00",
    "modified_at": "2024-01-19T10:30:00",
    "last_accessed": "2024-01-19T10:30:00",
    "days_since_access": 0,
    "usage_category": "RECENTLY_USED",
    "usage_priority": 0.1
}
```

### GET /api/usage/thresholds
Get current threshold configuration

**Response:**
```json
{
    "recently_used_days": 30,
    "rarely_used_days": 180,
    "not_used_days": 180,
    "min_priority_size_mb": 100
}
```

### PUT /api/usage/thresholds
Update threshold configuration

**Query Parameters:**
- `recently_used_days` (optional): Days for "recently used" (1-365)
- `rarely_used_days` (optional): Days for "rarely used" (1-1825)
- `not_used_days` (optional): Days for "not used" (1-1825)
- `min_priority_size_mb` (optional): Min file size for priority (1-100000 MB)

**Example:**
```
PUT /api/usage/thresholds?recently_used_days=14&rarely_used_days=90&not_used_days=180&min_priority_size_mb=50
```

**Response:**
```json
{
    "status": "success",
    "thresholds": {
        "recently_used_days": 14,
        "rarely_used_days": 90,
        "not_used_days": 180,
        "min_priority_size_mb": 50
    }
}
```

## Implementation Details

### Cross-Platform Access Time Handling

The implementation handles platform differences in file access time:

```python
# Linux: st_atime is reliable
# macOS: st_atime may be disabled (noatime mount)
# Windows: No direct atime support

# Fallback logic:
1. Try to get st_atime
2. Validate that atime >= mtime (atime shouldn't be older than mtime)
3. Return None if atime unavailable/invalid
4. Service layer falls back to modified_at
```

### Memory Efficiency

- **Streaming analysis**: Uses generators for large directory scans
- **Batch processing**: Configurable batch sizes (default: 500 files)
- **Database indexing**: Indexes on usage_category, usage_priority for fast queries
- **No file duplication**: Stores metadata only, not files

### Excluded Directories

System and protected directories are automatically skipped:
- Version control: .git, .svn, .hg
- Build caches: __pycache__, node_modules, .pytest_cache
- Virtual environments: venv, .venv, env
- IDE configs: .vscode, .idea
- System: $Recycle.Bin, System Volume Information
- OS specific: .Trash, .Spotlight-V100

## Usage Examples

### Example 1: Scan Directory and Get Cleanup Candidates

```python
from pathlib import Path
from app.services.usage_service import UsageService
from app.db.connection import get_session

# Initialize service
session = get_session()
service = UsageService(db_session=session)

# Get high-priority cleanup candidates
recommendations = service.get_cleanup_recommendations(
    limit=50,
    min_priority=0.8  # Very high priority only
)

print(f"Found {len(recommendations)} files to clean up")
for rec in recommendations:
    print(f"  {rec['path']} ({rec['size_mb']} MB) - {rec['reason']}")
```

### Example 2: Configure Custom Thresholds

```python
# Update thresholds
service.update_thresholds(
    recently_used_days=14,        # 2 weeks
    rarely_used_days=90,          # 3 months
    not_used_days=180,            # 6 months
    min_priority_size_mb=50,      # Files >50MB get priority bonus
)

# Get updated summary
summary = service.get_usage_summary()
print(f"NOT_USED files: {summary['summary']['NOT_USED']['count']} files")
print(f"Cleanup potential: {summary['potential_cleanup_mb']} MB")
```

### Example 3: Batch Update Usage for Scan Results

```python
from app.core.scanner import FileScanner

# Get files from scan
scanner = FileScanner()
scan_results = list(scanner.scan(Path("/data")))

# Extract paths
file_paths = [f.path for f in scan_results]

# Analyze and store usage
results = service.batch_update_usage(file_paths)
print(f"Updated {results['updated']} files, {results['failed']} failed")
```

## Integration Points

### With File Scanner
```python
# After scanning files, analyze usage
scanner = FileScanner()
for file_meta in scanner.scan(root_path):
    # Store to database first (scan_service)
    # Then analyze usage
    service.analyze_and_store_usage(file_meta.path)
```

### With Cleanup Service
```python
# Get cleanup recommendations
recommendations = service.get_cleanup_recommendations()

# Use recommendations for cleanup decisions
for rec in recommendations:
    if should_delete(rec):
        cleanup_service.mark_for_deletion(rec["id"])
```

## Testing

Run test suite:
```bash
pytest backend/tests/test_usage_analysis.py -v
```

Test coverage includes:
- Threshold configuration
- Category assignment
- Priority calculation
- Batch analysis
- Statistics generation
- Edge cases (very old files, large files, etc.)

## Configuration

All thresholds are configurable via API:

**Default Configuration:**
- Recently used: 30 days
- Rarely used: 180 days
- Not used: 180 days
- Min priority size: 100 MB

**Recommended Configurations:**

**Conservative** (keep more files):
```
recently_used_days=30, rarely_used_days=270, not_used_days=365
```

**Aggressive** (cleanup more files):
```
recently_used_days=14, rarely_used_days=90, not_used_days=180
```

**Very Aggressive** (aggressive cleanup):
```
recently_used_days=7, rarely_used_days=60, not_used_days=120
```

## Performance

- **Small directory** (<1000 files): <5 seconds
- **Medium directory** (10k files): <2 minutes
- **Large directory** (100k files): <20 minutes
- **Memory usage**: Constant (streaming analysis)

## Error Handling

- Permission errors: Logged and skipped, continues processing
- Inaccessible files: Gracefully handled
- Missing access time: Falls back to modified time
- Invalid thresholds: Validated before update
- Database errors: Logged with rollback

## Future Enhancements

1. **Incremental Analysis**: Only re-analyze modified files
2. **Machine Learning**: Predict file importance
3. **Pattern Recognition**: Identify backup files, temp files
4. **Scheduled Analysis**: Automatic periodic analysis
5. **Detailed Reports**: HTML/PDF cleanup reports
6. **Undo Functionality**: Restore from cleanup
