# Desktop Application - Storage Manager Pro

Electron-based desktop wrapper for the Storage Manager application.

## Project Structure

```
desktop/
├── main.js          # Main Electron process
├── preload.js       # Context bridge for IPC
└── package.json     # Desktop dependencies
```

## Quick Start

### Prerequisites
- Node.js 16+
- npm or yarn

### Installation

```bash
npm install
```

### Development

```bash
npm run dev
```

This will:
1. Start the React dev server on port 3000
2. Launch the Electron window
3. Enable hot reloading

### Build for Production

```bash
npm run build
```

Creates installers for Windows/Mac/Linux.

## Architecture

### Main Process (`main.js`)
- Creates and manages BrowserWindow
- Handles application lifecycle
- Provides IPC handlers
- Creates application menu
- Manages window state

### Preload Script (`preload.js`)
- Exposes safe APIs to renderer process
- Implements context isolation
- Handles file dialogs
- App version and quit commands

### IPC Handlers
- `get-app-version` - Returns app version
- `open-file-dialog` - Opens directory selection dialog
- `app-quit` - Quits the application

## Configuration

### Window Settings
- Default size: 1400x900px
- Minimum size: 800x600px
- Resizable and full-screen capable

### Dev vs Production
- **Development**: Loads from `http://localhost:3000`
- **Production**: Loads from bundled `dist/index.html`

## Building

### For Windows
```bash
npm run build
```

Creates:
- `dist/Storage Manager Pro Setup.exe` (installer)
- `dist/Storage Manager Pro Portable.exe` (portable)

### For macOS
```bash
npm run build
```

Creates:
- `dist/Storage Manager Pro-x.x.x.dmg` (installer)

### For Linux
```bash
npm run build
```

Creates:
- `dist/*.AppImage` (AppImage)
- `dist/*.deb` (Debian package)

## Electron Builder Configuration

Located in `package.json` under `build` key:

- **appId**: Unique application identifier
- **productName**: User-facing application name
- **directories**: Resource directories
- **files**: Files to include in distribution
- **win/nsis**: Windows-specific settings
- **build**: Build output options

## Development Tips

1. **DevTools**: Press F12 to open DevTools in development
2. **Reload**: Press Ctrl+R to reload the app
3. **Hot Reload**: React changes auto-reload without full restart
4. **IPC Debugging**: Check DevTools console for IPC messages

## API Integration with Electron

The frontend can access Electron APIs through the preload script:

```javascript
// In React components
const version = await window.electron.getAppVersion();
const filePath = await window.electron.openFileDialog();
```

## Packaging

### Windows Installer (NSIS)
- One-click disabled for safety
- Allows custom installation path
- Creates start menu shortcuts
- Adds uninstaller

### Code Signing
To sign the executable:

1. Obtain a code signing certificate
2. Set `CSC_LINK` and `CSC_KEY_PASSWORD` environment variables
3. Run `npm run build`

## Debugging

### Inspect Main Process
```bash
npm run dev
# In another terminal
node --inspect-brk ./node_modules/.bin/electron .
```

### Check Logs
Logs are stored in:
- **Windows**: `%APPDATA%\StorageManager\logs`
- **macOS**: `~/Library/Logs/StorageManager`
- **Linux**: `~/.cache/StorageManager`

## Troubleshooting

### App won't start
1. Clear cache: `rm -rf .electron-cache`
2. Reinstall: `npm install`
3. Check Node version: `node --version` (should be 16+)

### Build fails
1. Clear dist: `rm -rf dist`
2. Check dependencies: `npm list --depth=0`
3. Rebuild native modules: `npm rebuild`

### Window won't load
1. Check if dev server is running: `npm run dev` in frontend
2. Verify port 3000 is accessible
3. Check DevTools for errors

## Auto-Updates

To implement auto-updates:

1. Setup update server
2. Add electron-updater dependency
3. Implement update checks in main.js
4. Configure update provider in package.json

## Resources

- [Electron Documentation](https://www.electronjs.org/docs)
- [Electron Builder](https://www.electron.build/)
- [IPC Documentation](https://www.electronjs.org/docs/api/ipc-main)

## Next Steps

1. Add auto-update functionality
2. Implement native file associations
3. Add system tray integration
4. Create installers for all platforms
5. Setup code signing
6. Implement analytics/crash reporting
