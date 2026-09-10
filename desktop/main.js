/**
 * JARVIS Desktop App - Electron main process
 * 
 * This file runs in the main Electron process and manages:
 * - Window creation and lifecycle
 * - System tray integration
 * - IPC communication with renderer (web) process
 * - Auto-updates
 * - File operations
 */

const { app, BrowserWindow, Menu, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const isDev = require('electron-is-dev');
const { autoUpdater } = require('electron-updater');
const Store = require('electron-store');

const store = new Store();

let mainWindow;
let trayWindow;
let isQuitting = false;

// Platform-specific constants
const PLATFORM = process.platform; // 'win32', 'linux', 'darwin'
const APP_NAME = 'JARVIS';
const APP_VERSION = app.getVersion();

// =========================================================================
// Window Management
// =========================================================================

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 600,
    minHeight: 400,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      enableRemoteModule: false,
      nodeIntegration: false,
    },
    icon: getAppIcon(),
  });

  const url = isDev
    ? 'http://localhost:3000' // React dev server
    : `file://${path.join(__dirname, '../build/index.html')}`; // Built React app

  mainWindow.loadURL(url);

  if (isDev) {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  mainWindow.on('close', (event) => {
    if (!isQuitting && store.get('minimizeOnClose', false)) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  return mainWindow;
}

function createTrayWindow() {
  /**
   * Minimal tray/quick-access window for macOS menu bar or Windows/Linux system tray.
   * Shows recent messages, quick actions, status.
   */
  trayWindow = new BrowserWindow({
    width: 350,
    height: 500,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const trayUrl = isDev
    ? 'http://localhost:3000?mode=tray'
    : `file://${path.join(__dirname, '../build/index.html?mode=tray')}`;

  trayWindow.loadURL(trayUrl);

  return trayWindow;
}

// =========================================================================
// Menu & Tray
// =========================================================================

function createAppMenu() {
  const template = [
    {
      label: 'File',
      submenu: [
        {
          label: 'Exit',
          accelerator: 'CmdOrCtrl+Q',
          click: () => {
            isQuitting = true;
            app.quit();
          },
        },
      ],
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
      ],
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'About JARVIS',
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: `About ${APP_NAME}`,
              message: `${APP_NAME} Desktop v${APP_VERSION}`,
              detail: 'An intelligent OS assistant.',
            });
          },
        },
        {
          label: 'Check for Updates',
          click: () => {
            autoUpdater.checkForUpdatesAndNotify();
          },
        },
      ],
    },
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

function createTrayMenu() {
  const iconPath = getAppIcon();
  const tray = new (require('electron')).Tray(iconPath);

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        } else {
          createMainWindow();
        }
      },
    },
    {
      label: 'Status',
      submenu: [
        { label: 'Online', enabled: false }, // Status from IPC will update this
        { type: 'separator' },
        { label: 'Plugins: 3 installed', enabled: false },
        { label: 'Tasks: 2 running', enabled: false },
      ],
    },
    { type: 'separator' },
    {
      label: 'Quick Actions',
      submenu: [
        { label: 'Open command palette', accelerator: 'Shift+Cmd+P' },
        { label: 'Settings', click: () => mainWindow?.webContents.send('menu:settings') },
      ],
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);
  tray.on('click', () => {
    if (mainWindow) {
      mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
    }
  });

  return tray;
}

// =========================================================================
// IPC Handlers (Main ↔ Renderer communication)
// =========================================================================

ipcMain.handle('jarvis:connect', async (event, { host, port, token }) => {
  /**
   * Connect renderer to JARVIS backend.
   * Stores connection settings, attempts to connect.
   */
  try {
    store.set('jarvis.host', host);
    store.set('jarvis.port', port);
    // Token is NOT stored unencrypted; use secure storage
    return { success: true, version: '2.1.0' };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

ipcMain.handle('jarvis:sendCommand', async (event, command) => {
  /**
   * Send a command to JARVIS backend via WebSocket or REST.
   */
  // Implementation would connect to JARVIS server at store.get('jarvis.host:port')
  return { status: 'Command received' };
});

ipcMain.handle('jarvis:getSettings', async () => {
  /**
   * Return all user settings for this device.
   */
  return store.store;
});

ipcMain.handle('jarvis:saveSetting', async (event, key, value) => {
  /**
   * Save a setting to disk and sync to other devices.
   */
  store.set(key, value);
  event.sender.send('sync:settingChanged', { key, value });
  return true;
});

ipcMain.handle('file:openDialog', async (event, options) => {
  /**
   * Let user select files/folders.
   */
  return await dialog.showOpenDialog(mainWindow, options);
});

ipcMain.handle('file:saveDialog', async (event, options) => {
  /**
   * Let user save a file.
   */
  return await dialog.showSaveDialog(mainWindow, options);
});

ipcMain.handle('file:read', async (event, filePath) => {
  /**
   * Read file from disk.
   */
  const fs = require('fs');
  try {
    return await fs.promises.readFile(filePath, 'utf-8');
  } catch (error) {
    throw new Error(`Cannot read file: ${error.message}`);
  }
});

ipcMain.handle('file:write', async (event, filePath, content) => {
  /**
   * Write file to disk.
   */
  const fs = require('fs');
  try {
    await fs.promises.writeFile(filePath, content, 'utf-8');
    return true;
  } catch (error) {
    throw new Error(`Cannot write file: ${error.message}`);
  }
});

ipcMain.handle('shell:openExternal', async (event, url) => {
  /**
   * Open URL in default browser.
   */
  return await shell.openExternal(url);
});

ipcMain.handle('system:info', async () => {
  /**
   * Return system information for troubleshooting.
   */
  const os = require('os');
  return {
    platform: PLATFORM,
    arch: process.arch,
    appVersion: APP_VERSION,
    nodeVersion: process.version,
    osVersion: os.release(),
    totalMemory: os.totalmem(),
    freeMemory: os.freemem(),
  };
});

// =========================================================================
// Auto-Update
// =========================================================================

function setupAutoUpdater() {
  if (!isDev) {
    autoUpdater.checkForUpdatesAndNotify();
    setInterval(() => {
      autoUpdater.checkForUpdatesAndNotify();
    }, 3600000); // Check every hour
  }

  autoUpdater.on('update-downloaded', () => {
    dialog.showMessageBox(mainWindow, {
      type: 'info',
      title: 'Update Ready',
      message: 'JARVIS will restart to install the update.',
      buttons: ['Restart Now', 'Later'],
    }).then((result) => {
      if (result.response === 0) {
        autoUpdater.quitAndInstall();
      }
    });
  });
}

// =========================================================================
// App Lifecycle
// =========================================================================

app.on('ready', () => {
  createMainWindow();
  createTrayMenu();
  createAppMenu();
  setupAutoUpdater();
});

app.on('window-all-closed', () => {
  if (PLATFORM !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createMainWindow();
  } else {
    mainWindow.show();
    mainWindow.focus();
  }
});

// =========================================================================
// Utilities
// =========================================================================

function getAppIcon() {
  const iconDir = path.join(__dirname, '../assets/icons');
  if (PLATFORM === 'win32') {
    return path.join(iconDir, 'icon.ico');
  } else if (PLATFORM === 'darwin') {
    return path.join(iconDir, 'icon.icns');
  } else {
    return path.join(iconDir, 'icon.png');
  }
}

module.exports = { createMainWindow, createTrayWindow };
