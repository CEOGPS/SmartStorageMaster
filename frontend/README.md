# Frontend - Storage Manager Pro

Complete React-based frontend for the Storage Manager application.

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── Dashboard/
│   │   ├── FileScanner/
│   │   ├── DuplicateViewer/
│   │   ├── CleanupManager/
│   │   └── Charts/
│   ├── pages/
│   │   ├── Home.jsx
│   │   ├── Scan.jsx
│   │   ├── Duplicates.jsx
│   │   ├── Cleanup.jsx
│   │   └── Settings.jsx
│   ├── services/
│   │   └── api.js
│   ├── hooks/
│   │   ├── useFetch.js
│   │   └── useLocalStorage.js
│   ├── utils/
│   │   └── helpers.js
│   ├── App.jsx
│   ├── main.jsx
│   └── index.css
├── index.html
├── package.json
└── vite.config.js
```

## Installation

### Prerequisites
- Node.js 16+ 
- npm or yarn

### Setup

```bash
cd frontend
npm install
```

## Development

### Start Development Server

```bash
npm run dev
```

The app will open at `http://localhost:3000`

### Build for Production

```bash
npm run build
```

Output files will be in the `dist/` directory.

## Components

### Dashboard
- **File**: `components/Dashboard/Dashboard.jsx`
- **Purpose**: Main overview dashboard
- **Features**:
  - Storage usage statistics
  - Duplicate file count and potential savings
  - Quick action buttons
  - Recent activity feed
  - Real-time refresh

### FileScanner
- **File**: `components/FileScanner/FileScanner.jsx`
- **Purpose**: Directory scanning interface
- **Features**:
  - Path input with file browser dialog
  - Real-time progress tracking with WebSocket
  - Configurable scan options
  - Scan history
  - Size and file count statistics

### DuplicateViewer
- **File**: `components/DuplicateViewer/DuplicateViewer.jsx`
- **Purpose**: View and manage duplicate files
- **Features**:
  - Group-based duplicate display
  - Multi-select with group selection
  - Primary file marking (prevents deletion)
  - Filter by file type
  - Sort by size, name, date, or count
  - Potential savings calculation

### CleanupManager
- **File**: `components/CleanupManager/CleanupManager.jsx`
- **Purpose**: Manage backups and restore files
- **Features**:
  - Backup statistics
  - File type filtering
  - Restore functionality
  - Clear old backups
  - Safety information

### StorageChart
- **File**: `components/Charts/StorageChart.jsx`
- **Purpose**: Visual storage usage charts
- **Dependencies**: recharts

### DuplicatesSummary
- **File**: `components/Charts/DuplicatesSummary.jsx`
- **Purpose**: Visual duplicate statistics
- **Dependencies**: recharts

## Pages

### Home
- Main landing page
- Displays Dashboard component
- Entry point for new users

### Scan
- File scanning interface
- Includes FileScanner component
- Manage scan operations

### Duplicates
- Duplicate management interface
- Includes DuplicateViewer component
- Select and cleanup duplicates

### Cleanup
- Backup management interface
- Includes CleanupManager component
- Restore deleted files

### Settings
- Application configuration
- Scan options
- Cleanup preferences
- Theme selection

## Services

### API Service (`services/api.js`)

All API calls are centralized in this module:

#### Storage APIs
- `getStorageStats()` - Get storage overview
- `getDuplicateStats()` - Get duplicate statistics

#### Scan APIs
- `startScan(path, options)` - Start file scan
- `getScanStatistics(scanId)` - Get scan progress
- `getScanFiles(scanId, limit, offset)` - Get scanned files

#### Duplicate Detection APIs
- `detectDuplicates(scanId, options)` - Detect duplicate files
- `getDuplicates(filterType)` - Get detected duplicates
- `getDuplicateSavings()` - Get savings calculation

#### Cleanup APIs
- `selectForCleanup(fileIds)` - Mark files for deletion
- `backupFiles(fileIds)` - Create backup
- `getBackups()` - Get backup list
- `restoreFile(backupId)` - Restore backed-up file
- `clearBackups(days)` - Clear old backups

#### WebSocket
- `connectScanWebSocket(scanId, onProgress, onComplete, onError)` - Connect to scan progress
- `disconnectWebSocket(ws)` - Disconnect from WebSocket

## Hooks

### useFetch
Custom hook for API calls with loading and error states.

```javascript
const { data, loading, error, execute, reset } = useFetch(fetchFunction);
```

### useLocalStorage
Persist state to browser local storage.

```javascript
const [value, setValue] = useLocalStorage(key, initialValue);
```

## Utilities

### helpers.js
- `formatBytes(bytes)` - Format file size
- `formatDate(date)` - Format date/time
- `getFileIcon(fileName)` - Get emoji icon for file type
- `calculatePercentage(value, total)` - Calculate percentage
- `debounce(func, wait)` - Debounce function

## Styling

All components use inline CSS with className attributes. Color scheme:
- Primary: `#3498db` (blue)
- Success: `#27ae60` (green)
- Danger: `#e74c3c` (red)
- Dark: `#2c3e50` (dark gray)
- Light: `#ecf0f1` (light gray)

### Responsive Design
- Desktop-first approach
- Mobile responsive breakpoints at 768px

## Configuration

### Vite Configuration (`vite.config.js`)
- Dev server on port 3000
- API proxy to backend (http://localhost:8000)
- WebSocket proxy for real-time updates

### Build Options
- Output directory: `dist/`
- Source maps disabled in production

## Environment Variables

Create a `.env` file in the frontend directory:

```
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Performance Optimization

- React Router for efficient routing
- Component lazy loading ready
- Optimized CSS with no duplication
- WebSocket for real-time updates

## Common Issues

### CORS Errors
Ensure the backend is running on `http://localhost:8000` and CORS is properly configured.

### WebSocket Connection Failed
Check that the backend WebSocket server is running on `ws://localhost:8000`.

### Build Errors
Clear node_modules and reinstall:
```bash
rm -rf node_modules package-lock.json
npm install
```

## Dependencies

- **React**: UI framework
- **React Router**: Client-side routing
- **Recharts**: Chart components
- **Vite**: Build tool and dev server

## Development Tips

1. Use React DevTools browser extension for debugging
2. Check Network tab in DevTools for API calls
3. Use console.log for debugging
4. Test components in isolation first
5. Follow existing code patterns and styles

## Next Steps

1. Connect to backend API endpoints
2. Implement real-time WebSocket updates
3. Add error boundary components
4. Implement state management (Context API or Redux)
5. Add unit tests
6. Setup CI/CD pipeline
7. Create desktop wrapper with Electron
