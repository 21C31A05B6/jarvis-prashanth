/**
 * JARVIS Web Dashboard - Main React App Component
 * 
 * Features:
 * - Connect to JARVIS backend (local or remote)
 * - Task management and monitoring
 * - Memory browser
 * - Settings and preferences
 * - Plugin management
 * - Integration status
 */

import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import axios from 'axios';
import './App.css';

import Dashboard from './pages/Dashboard';
import Tasks from './pages/Tasks';
import Memory from './pages/Memory';
import Integrations from './pages/Integrations';
import Plugins from './pages/Plugins';
import Settings from './pages/Settings';
import ConnectionSetup from './pages/ConnectionSetup';

function App() {
  const [connected, setConnected] = useState(false);
  const [jarvisHost, setJarvisHost] = useState(localStorage.getItem('jarvisHost') || '');
  const [jarvisPort, setJarvisPort] = useState(localStorage.getItem('jarvisPort') || '5000');
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [systemInfo, setSystemInfo] = useState(null);
  const [lastSync, setLastSync] = useState(new Date());

  // Try to connect on mount
  useEffect(() => {
    if (jarvisHost) {
      attemptConnection();
    }
  }, []);

  // Periodic sync with backend
  useEffect(() => {
    if (connected) {
      const interval = setInterval(() => {
        syncWithBackend();
      }, 5000); // Sync every 5 seconds
      return () => clearInterval(interval);
    }
  }, [connected]);

  const attemptConnection = async () => {
    if (!jarvisHost) return;

    try {
      setConnectionStatus('connecting');
      const url = `http://${jarvisHost}:${jarvisPort}/api/status`;
      const response = await axios.get(url, { timeout: 5000 });
      
      if (response.status === 200) {
        setConnected(true);
        setConnectionStatus('connected');
        localStorage.setItem('jarvisHost', jarvisHost);
        localStorage.setItem('jarvisPort', jarvisPort);
      }
    } catch (error) {
      setConnected(false);
      setConnectionStatus('disconnected');
      console.error('Connection failed:', error.message);
    }
  };

  const syncWithBackend = async () => {
    if (!connected) return;

    try {
      const response = await axios.get(
        `http://${jarvisHost}:${jarvisPort}/api/sync`,
        { timeout: 5000 }
      );
      setSystemInfo(response.data);
      setLastSync(new Date());
    } catch (error) {
      // Silent fail for periodic sync
    }
  };

  const handleConnect = (host, port) => {
    setJarvisHost(host);
    setJarvisPort(port);
    setTimeout(() => attemptConnection(), 100);
  };

  if (!connected) {
    return <ConnectionSetup onConnect={handleConnect} />;
  }

  return (
    <Router>
      <div className="app-container">
        <Sidebar />
        <MainContent />
        <StatusBar
          connected={connected}
          status={connectionStatus}
          lastSync={lastSync}
        />
      </div>
    </Router>
  );
}

function Sidebar() {
  return (
    <nav className="sidebar">
      <div className="sidebar-header">
        <h1>JARVIS</h1>
        <span className="version">v2.1.0</span>
      </div>

      <div className="sidebar-nav">
        <Link to="/" className="nav-item">
          <span className="icon">📊</span> Dashboard
        </Link>
        <Link to="/tasks" className="nav-item">
          <span className="icon">✓</span> Tasks
        </Link>
        <Link to="/memory" className="nav-item">
          <span className="icon">🧠</span> Memory
        </Link>
        <Link to="/integrations" className="nav-item">
          <span className="icon">🔗</span> Integrations
        </Link>
        <Link to="/plugins" className="nav-item">
          <span className="icon">🧩</span> Plugins
        </Link>
        <Link to="/settings" className="nav-item">
          <span className="icon">⚙️</span> Settings
        </Link>
      </div>

      <div className="sidebar-footer">
        <div className="user-info">
          <div className="avatar">👤</div>
          <div className="user-details">
            <div className="user-name">User</div>
            <div className="user-status">Online</div>
          </div>
        </div>
      </div>
    </nav>
  );
}

function MainContent() {
  return (
    <main className="main-content">
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/memory" element={<Memory />} />
        <Route path="/integrations" element={<Integrations />} />
        <Route path="/plugins" element={<Plugins />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </main>
  );
}

function StatusBar({ connected, status, lastSync }) {
  const statusColor = status === 'connected' ? '#4caf50' : '#f44336';
  const statusText = {
    connecting: 'Connecting...',
    connected: 'Connected',
    disconnected: 'Disconnected',
  }[status];

  return (
    <div className="status-bar">
      <div className="status-indicator" style={{ backgroundColor: statusColor }}>
        {statusText}
      </div>
      <div className="last-sync">
        Last sync: {lastSync.toLocaleTimeString()}
      </div>
    </div>
  );
}

export default App;
