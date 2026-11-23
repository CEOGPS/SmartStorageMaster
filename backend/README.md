# Backend - Storage Manager Pro

Production-quality Python FastAPI backend for AI-powered storage management.

## Overview

Complete file system scanning, duplicate detection (exact and perceptual), and safe cleanup operations with backup/restore functionality.

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app factory
│   ├── config.py            # Configuration (dev/prod/test)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── scanner.py       # File system scanner
│   │   └── cleanup.py       # Backup and restore
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── image_hash.py    # Perceptual hashing
│   │   └── embeddings.py    # Deep learning (optional)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py    # SQLite connection
│   │   └── models.py        # SQLAlchemy ORM models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── scan_service.py
│   │   ├── duplicate_service.py
│   │   └── cleanup_service.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── schemas.py       # Pydantic models
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── scan_routes.py
│   │   │   ├── duplicate_routes.py
│   │   │   └── cleanup_routes.py
│   └── utils/
│       ├── __init__.py
│       ├── file_utils.py
│       └── logging_config.py
├── run.py                   # Entry point
├── requirements.txt         # Dependencies
└── README.md                # This file
```

## Installation

### Prerequisites

- Python 3.10 or higher
- pip or poetry

### Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Optional: GPU Support

For deep learning embeddings with GPU acceleration:

```bash
# Install CUDA-enabled PyTorch
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

## Running the Server

### Development

```bash
python run.py --env development --reload
```

Server will start at `http://localhost:8000`

### Production

```bash
python run.py --env production --host 0.0.0.0 --port 8000
```

### Command Line Options

```bash
python run.py --help

Options:
  --host HOST              Host to bind (default: 0.0.0.0)
  --port PORT              Port to bind (default: 8000)
  --env {dev,prod,test}    Environment (default: development)
  --reload                 Enable auto-reload
  --log-level {debug,info,warning,error}
```

## Architecture

### Separation of Concerns

- **core/**: File system operations, scanning, cleanup
- **ai/**: Image hashing, embeddings, duplicate detection
- **db/**: Database models, connection, ORM
- **services/**: Business logic, orchestration
- **api/**: REST endpoints, request/response handling
- **utils/**: Reusable utilities

### Database Models

#### File
Metadata for scanned files
- id: UUID
- scan_id: Reference to scan session
- path: Full file path
- name: File name
- size: File size in bytes
- mime_type: MIME type
- hash_md5/sha256: File hashes
- created_at/modified_at: Timestamps

#### DuplicateGroup
Group of duplicate files
- id: UUID
- scan_id: Reference to scan
- group_type: "exact", "phash", "embedding"
- total_size: Combined size of all files
- entries: List of DuplicateEntry

#### DuplicateEntry
Individual file in duplicate group
- id: UUID
- group_id: Reference to group
- file_id: Reference to file
- is_primary: Whether this is the "keep" file
- similarity_score: 0.0-1.0

#### BackupFile
Backup metadata for deleted files
- id: UUID
- original_file_id: Reference to original file
- original_path: Original file path
- backup_path: Path to backup copy
- deleted_at: When deleted
- restored_at: When restored (nullable)
- permanently_deleted_at: When permanently deleted

## API Endpoints

### Scan Operations

**POST /api/scan/start**
- Start a file system scan
- Body: `{path, recursive, include_hidden, compute_hashes}`
- Returns: `{scan_id}`

**GET /api/scan/status/{scan_id}**
- Get scan progress
- Returns: `{status, total_files, total_size, ...}`

**GET /api/scan/files/{scan_id}**
- Get files from scan
- Query: `limit`, `offset`
- Returns: `{files[], total, limit, offset}`

**GET /api/scan/storage-stats**
- Get overall storage statistics
- Returns: `{total_files, total_size, last_scan}`

### Duplicate Detection

**POST /api/duplicates/detect**
- Detect duplicate files
- Body: `{scan_id, detect_exact, detect_images, image_similarity}`
- Returns: `{exact_groups, image_groups, total_groups}`

**GET /api/duplicates/groups/{scan_id}**
- Get duplicate groups
- Query: `group_type` (optional)
- Returns: `{groups[], count}`

**GET /api/duplicates/stats/{scan_id}**
- Get duplicate statistics
- Returns: `{total_groups, total_duplicates, total_savings, by_type}`

### Cleanup Operations

**POST /api/cleanup/backup**
- Backup files before deletion
- Body: `{file_ids[]}`
- Returns: `{backed_up, failed, total}`

**DELETE /api/cleanup/delete**
- Delete backed-up files
- Body: `{file_ids[]}`
- Returns: `{deleted, failed, total}`

**GET /api/cleanup/backups**
- List backup files
- Returns: `{backups[], count}`

**POST /api/cleanup/restore**
- Restore file from backup
- Body: `{backup_id, restore_to?}`
- Returns: `{success, restored_path?}`

**POST /api/cleanup/cleanup-old**
- Clean up old backups
- Query: `max_age_days` (default: 30)
- Returns: `{deleted_count}`

**GET /api/cleanup/stats**
- Get cleanup statistics
- Returns: `{total_backups, active_backups, total_backup_size}`

### Health/Info

**GET /health**
- Health check
- Returns: `{status: "healthy", ...}`

**GET /**
- API information
- Returns: `{name, version, docs_url}`

## Duplicate Detection Algorithms

### Exact Matching
- Uses MD5 hashing for fast comparison
- 100% accurate
- Groups files with identical content

### Perceptual Hashing (Images)
- Implements three algorithms:
  - **pHash**: Perceptual hash using DCT
  - **dHash**: Difference hash
  - **aHash**: Average hash
- Robust to resizing, compression, small edits
- Configurable similarity threshold (0.85 default)

### Deep Learning (Optional)
- ResNet50 image embeddings
- FAISS vector similarity search
- GPU-accelerated (if available)
- Similarity threshold: 0.85 (configurable)

## Configuration

### Environment-Specific Settings

**Development** (`config.DevelopmentConfig`)
- SQLite database: `storage_dev.db`
- SQL logging: Optional
- Debug mode: ON

**Production** (`config.ProductionConfig`)
- SQLite database: `storage.db`
- SQL logging: OFF
- Debug mode: OFF
- Stricter thresholds

**Testing** (`config.TestingConfig`)
- In-memory SQLite
- Full SQL logging
- Debug mode: ON

### Custom Configuration

Set environment variables:
```bash
export STORAGE_DB_URL="sqlite:///custom_path.db"
export STORAGE_LOG_LEVEL="DEBUG"
export STORAGE_BACKUP_ROOT="/custom/backup/path"
```

## File Scanning

### Features

- Recursive directory traversal
- Batch processing (500 files default)
- Cross-platform path handling
- Automatic MIME type detection
- MD5 and SHA256 hashing
- Progress callbacks for long operations

### Excluded by Default

- Version control: `.git`, `.svn`, `.hg`
- Package managers: `node_modules`, `__pycache__`
- Virtual environments: `venv`, `.venv`, `env`
- IDE configs: `.vscode`, `.idea`
- System folders: `Windows`, `Program Files`, `/usr`, `/etc`, etc.

### Custom Exclusions

Modify in `core/scanner.py`:
```python
EXCLUDED_DIRS = {...}
EXCLUDED_EXTENSIONS = {...}
```

## Safe Cleanup Operations

All deletion operations are safe:

1. **Backup First**: Files are copied to backup directory before deletion
2. **Timestamped**: Backups organized by date/time
3. **Recoverable**: Files can be restored from backup
4. **Permanent Delete**: After manual confirmation, backups can be permanently deleted

### Backup Structure

```
backups/
├── 20240101_120000/
│   ├── image.jpg
│   └── document.pdf
├── 20240101_140000/
│   └── video.mp4
└── ...
```

## Error Handling

All endpoints return consistent response format:

**Success:**
```json
{
  "success": true,
  "data": {...},
  "timestamp": "2024-01-01T00:00:00Z"
}
```

**Error:**
```json
{
  "detail": "Error message",
  "error_code": "INVALID_PATH",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## Logging

Logs are written to `./logs/storage_manager.log` with rotation:
- Max file size: 10 MB
- Backup count: 5 files
- Format: `timestamp | level | module | message`

## Performance Considerations

### Memory Efficiency

- **File Scanning**: Generator-based, processes in batches
- **Hash Computation**: Reads files in 8KB chunks
- **Embeddings**: Batch processing with configurable batch size
- **Vector Search**: FAISS for memory-efficient similarity

### Time Complexity

- Scan 100K files: ~30 seconds
- Exact duplicate detection: ~5 seconds
- Image duplicate detection: ~10-30 seconds (depends on image count)
- Vector search: <100ms for 10K vectors

### Optimization Tips

1. Disable hashing for initial scan if not needed
2. Use `include_hidden=False` for faster scan
3. Batch cleanup operations
4. Schedule cleanup during off-peak hours

## Testing

Run tests:
```bash
pytest
```

With coverage:
```bash
pytest --cov=app tests/
```

## Development Guidelines

### Code Style

- Follow PEP 8
- Type hints for all functions
- Docstrings for classes and public methods
- Error handling with try/except
- Logging at appropriate levels

### Adding New Endpoints

1. Create schema in `api/schemas.py`
2. Implement service method in `services/`
3. Create route handler in `api/routes/`
4. Add endpoint to router
5. Test with curl or Postman

## Troubleshooting

### Database Issues

**"Database is locked"**
- SQLite limitation with concurrent writes
- Solution: Use PostgreSQL for production

**"Cannot open database"**
```bash
# Reset database
rm storage.db
python -c "from app.db import create_all_tables; create_all_tables()"
```

### Memory Issues

**"Out of memory during scan"**
- Reduce `BATCH_SIZE` in config
- Disable hashing with `compute_hashes=False`
- Scan smaller directories first

### API Issues

**CORS errors from frontend**
- Update `allowed_origins` in `app/main.py`
- In development, use `allow_origins=["*"]`

## Production Deployment

### Docker

```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "run.py", "--env", "production"]
```

### Environment Variables

```bash
STORAGE_ENV=production
STORAGE_DATABASE_URL=sqlite:///var/lib/storage.db
STORAGE_BACKUP_ROOT=/var/backups/storage
STORAGE_LOG_LEVEL=INFO
```

### Monitoring

Track in your monitoring system:
- Request latency per endpoint
- Database query time
- Backup directory size
- Scan completion times

## Dependencies

- **FastAPI**: Web framework
- **SQLAlchemy**: ORM
- **Pydantic**: Data validation
- **Pillow**: Image processing
- **NumPy**: Numerical operations
- **PyTorch** (optional): Deep learning
- **FAISS** (optional): Vector search

## License

MIT License

## Support

For issues:
1. Check logs in `./logs/`
2. Review error responses
3. Test with isolated files first
4. Check path permissions

## Next Steps

1. Connect to frontend API client
2. Implement WebSocket for real-time updates
3. Add authentication/authorization
4. Deploy to production
5. Setup monitoring and alerting
