# Quick Start Guide - Storage Manager Backend

## Installation & Running

### 1. Setup Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the Server

```bash
# Development (with auto-reload)
python run.py --env development --reload

# Production
python run.py --env production --port 8000
```

Server runs at: **http://localhost:8000**

API Documentation: **http://localhost:8000/docs** (Swagger UI)

## Testing the API

### 1. Health Check

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "app": "Storage Manager Pro",
  "version": "1.0.0"
}
```

### 2. Start a Scan

```bash
curl -X POST http://localhost:8000/api/scan/start \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/path/to/scan",
    "recursive": true,
    "include_hidden": false,
    "compute_hashes": true
  }'
```

Response:
```json
{
  "success": true,
  "scan_id": "uuid-string",
  "message": "Scan started for /path/to/scan"
}
```

### 3. Check Scan Status

```bash
curl http://localhost:8000/api/scan/status/{scan_id}
```

Response:
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "status": "running",
    "total_files": 150,
    "total_size": 1073741824,
    "elapsed_seconds": 10.5
  }
}
```

### 4. Get Scanned Files

```bash
curl 'http://localhost:8000/api/scan/files/{scan_id}?limit=10&offset=0'
```

Response:
```json
{
  "success": true,
  "data": {
    "total": 150,
    "limit": 10,
    "offset": 0,
    "files": [
      {
        "id": "file-uuid",
        "path": "/full/path/to/file.txt",
        "name": "file.txt",
        "size": 1024,
        "mime_type": "text/plain",
        "hash_md5": "5d41402abc4b2a76b9719d911017c592"
      }
    ]
  }
}
```

### 5. Detect Duplicates

```bash
curl -X POST http://localhost:8000/api/duplicates/detect \
  -H "Content-Type: application/json" \
  -d '{
    "scan_id": "{scan_id}",
    "detect_exact": true,
    "detect_images": true,
    "image_similarity": 0.85
  }'
```

Response:
```json
{
  "success": true,
  "data": {
    "exact_groups": 5,
    "image_groups": 3,
    "total_groups": 8,
    "group_ids": ["uuid1", "uuid2", ...]
  }
}
```

### 6. Get Duplicate Groups

```bash
curl 'http://localhost:8000/api/duplicates/groups/{scan_id}?group_type=exact'
```

Response:
```json
{
  "success": true,
  "data": {
    "groups": [
      {
        "id": "group-uuid",
        "type": "exact",
        "total_size": 2048,
        "file_count": 2,
        "savings": 1024,
        "files": [
          {
            "id": "file-uuid",
            "path": "/path/file1.txt",
            "is_primary": true,
            "similarity": 1.0
          },
          {
            "id": "file-uuid",
            "path": "/path/file2.txt",
            "is_primary": false,
            "similarity": 1.0
          }
        ]
      }
    ],
    "count": 1
  }
}
```

### 7. Backup Files

```bash
curl -X POST http://localhost:8000/api/cleanup/backup \
  -H "Content-Type: application/json" \
  -d '{
    "file_ids": ["file-uuid-1", "file-uuid-2"]
  }'
```

Response:
```json
{
  "success": true,
  "data": {
    "backed_up": 2,
    "failed": 0,
    "total": 2
  }
}
```

### 8. Delete Backed-up Files

```bash
curl -X DELETE http://localhost:8000/api/cleanup/delete \
  -H "Content-Type: application/json" \
  -d '{
    "file_ids": ["file-uuid-1", "file-uuid-2"]
  }'
```

Response:
```json
{
  "success": true,
  "data": {
    "deleted": 2,
    "failed": 0,
    "total": 2
  }
}
```

### 9. List Backups

```bash
curl http://localhost:8000/api/cleanup/backups
```

Response:
```json
{
  "success": true,
  "data": {
    "backups": [
      {
        "id": "backup-uuid",
        "original_path": "/original/path/file.txt",
        "backup_path": "/backups/20240101_120000/file.txt",
        "file_size": 1024,
        "is_restored": false
      }
    ],
    "count": 1
  }
}
```

### 10. Restore File

```bash
curl -X POST http://localhost:8000/api/cleanup/restore \
  -H "Content-Type: application/json" \
  -d '{
    "backup_id": "backup-uuid",
    "restore_to": "/optional/custom/path"
  }'
```

Response:
```json
{
  "success": true,
  "data": {
    "success": true,
    "restored_path": "/path/to/restored/file"
  }
}
```

## Using with Python Requests

```python
import requests

BASE_URL = "http://localhost:8000"

# Start scan
response = requests.post(f"{BASE_URL}/api/scan/start", json={
    "path": "/path/to/scan",
    "recursive": True,
    "compute_hashes": True,
})
scan_id = response.json()["scan_id"]

# Check status
status = requests.get(f"{BASE_URL}/api/scan/status/{scan_id}").json()
print(f"Scan status: {status['data']['status']}")
print(f"Files found: {status['data']['total_files']}")

# Detect duplicates
duplicates = requests.post(f"{BASE_URL}/api/duplicates/detect", json={
    "scan_id": scan_id,
    "detect_exact": True,
    "detect_images": True,
}).json()
print(f"Found {duplicates['data']['total_groups']} duplicate groups")

# Get duplicate details
groups = requests.get(f"{BASE_URL}/api/duplicates/groups/{scan_id}").json()
for group in groups['data']['groups']:
    print(f"Group {group['id']}: {group['file_count']} files, savings: {group['savings']} bytes")
```

## Using with JavaScript/Fetch

```javascript
const baseUrl = 'http://localhost:8000';

// Start scan
const startScan = async () => {
  const response = await fetch(`${baseUrl}/api/scan/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      path: '/path/to/scan',
      recursive: true,
      compute_hashes: true,
    }),
  });
  const data = await response.json();
  return data.scan_id;
};

// Check status
const getScanStatus = async (scanId) => {
  const response = await fetch(`${baseUrl}/api/scan/status/${scanId}`);
  return (await response.json()).data;
};

// Detect duplicates
const detectDuplicates = async (scanId) => {
  const response = await fetch(`${baseUrl}/api/duplicates/detect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      scan_id: scanId,
      detect_exact: true,
      detect_images: true,
    }),
  });
  return (await response.json()).data;
};

// Usage
(async () => {
  const scanId = await startScan();
  console.log('Scan started:', scanId);
  
  const status = await getScanStatus(scanId);
  console.log('Status:', status);
  
  const result = await detectDuplicates(scanId);
  console.log('Duplicates found:', result.total_groups);
})();
```

## Database Inspection

```bash
# Connect to SQLite database
sqlite3 storage.db

# List tables
.tables

# View scan sessions
SELECT * FROM scan_sessions;

# View files
SELECT id, name, size FROM files LIMIT 10;

# View duplicate groups
SELECT id, group_type, total_size, file_count FROM duplicate_groups;

# Count duplicates
SELECT COUNT(*) as duplicate_files FROM duplicate_entries;
```

## Logs

Check application logs:

```bash
# Watch logs in real-time
tail -f logs/storage_manager.log

# View recent errors
grep ERROR logs/storage_manager.log | tail -20

# Full log with timestamps
cat logs/storage_manager.log
```

## Troubleshooting

### Port Already in Use

```bash
# Use different port
python run.py --port 9000
```

### Database Locked

```bash
# SQLite limitation - stop other connections and try again
rm storage.db  # Reset database
```

### Import Errors

```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

### Permission Errors

```bash
# Run with elevated privileges (use with caution)
sudo python run.py
```

## Performance Tips

1. **Disable hashing** for faster initial scans:
   ```json
   {"compute_hashes": false}
   ```

2. **Exclude hidden files** for faster scan:
   ```json
   {"include_hidden": false}
   ```

3. **Batch operations** - process multiple files at once

4. **Use image similarity** carefully - can be slow:
   ```json
   {"image_similarity": 0.95}  // Higher = faster
   ```

## Next Steps

1. Start the backend: `python run.py --env development --reload`
2. Access API docs: http://localhost:8000/docs
3. Connect frontend to `http://localhost:8000`
4. Run test scans on small directories first
5. Monitor logs for errors

---

Backend is ready to integrate with the React frontend! 🚀
