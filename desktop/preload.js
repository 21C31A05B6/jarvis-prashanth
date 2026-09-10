/**
 * Preload script: Bridges main process and renderer with secure IPC.
 * 
 * This runs before any user code and exposes a limited API to the renderer.
 * Ensures context isolation and prevents code injection.
 */

const { contextBridge, ipcRenderer } = require('electron');

// Expose safe IPC methods to renderer via window.jarvisAPI
contextBridge.exposeInMainWorld('jarvisAPI', {
  // ====== JARVIS Backend Connection ======
  async connect(host, port, token) {
    return await ipcRenderer.invoke('jarvis:connect', { host, port, token });
  },

  async sendCommand(command) {
    return await ipcRenderer.invoke('jarvis:sendCommand', command);
  },

  // ====== Settings & Storage ======
  async getSettings() {
    return await ipcRenderer.invoke('jarvis:getSettings');
  },

  async saveSetting(key, value) {
    return await ipcRenderer.invoke('jarvis:saveSetting', key, value);
  },

  // ====== File Operations ======
  async openFile(options = {}) {
    return await ipcRenderer.invoke('file:openDialog', {
      properties: ['openFile'],
      ...options,
    });
  },

  async openFolder(options = {}) {
    return await ipcRenderer.invoke('file:openDialog', {
      properties: ['openDirectory'],
      ...options,
    });
  },

  async saveFile(options = {}) {
    return await ipcRenderer.invoke('file:saveDialog', options);
  },

  async readFile(filePath) {
    return await ipcRenderer.invoke('file:read', filePath);
  },

  async writeFile(filePath, content) {
    return await ipcRenderer.invoke('file:write', filePath, content);
  },

  // ====== System Integration ======
  async openURL(url) {
    return await ipcRenderer.invoke('shell:openExternal', url);
  },

  async getSystemInfo() {
    return await ipcRenderer.invoke('system:info');
  },

  // ====== Event Listeners (Main → Renderer) ======
  onSettingChanged(callback) {
    ipcRenderer.on('sync:settingChanged', (event, { key, value }) => {
      callback(key, value);
    });
  },

  onCommandReceived(callback) {
    ipcRenderer.on('jarvis:commandResult', (event, result) => {
      callback(result);
    });
  },

  onSyncUpdate(callback) {
    ipcRenderer.on('sync:update', (event, data) => {
      callback(data);
    });
  },

  onConnectionStatusChanged(callback) {
    ipcRenderer.on('jarvis:connectionStatusChanged', (event, status) => {
      callback(status);
    });
  },

  // ====== Menu Events ======
  onMenuSettings(callback) {
    ipcRenderer.on('menu:settings', callback);
  },

  // ====== Utility ======
  getAppVersion: () => require('electron').app.getVersion(),
  getPlatform: () => process.platform,
  isDev: () => require('electron-is-dev'),
});

// Also expose 'window.electron' for compatibility
contextBridge.exposeInMainWorld('electron', {
  ipcRenderer: {
    send: (channel, data) => ipcRenderer.send(channel, data),
    on: (channel, func) => {
      ipcRenderer.on(channel, (event, ...args) => func(...args));
    },
    once: (channel, func) => {
      ipcRenderer.once(channel, (event, ...args) => func(...args));
    },
    invoke: (channel, data) => ipcRenderer.invoke(channel, data),
  },
});
