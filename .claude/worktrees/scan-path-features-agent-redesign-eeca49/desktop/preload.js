const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electron', {
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  openFileDialog: () => ipcRenderer.invoke('open-file-dialog'),
  quit: () => ipcRenderer.send('app-quit'),
});