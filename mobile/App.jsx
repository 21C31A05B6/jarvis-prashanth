/**
 * JARVIS Mobile Companion App (React Native)
 * 
 * Provides:
 * - Quick access to JARVIS commands
 * - Task monitoring and updates
 * - Push notifications for important events
 * - Remote control of desktop JARVIS
 * - Quick message sending
 */

import React, { useState, useEffect } from 'react';
import {
  StyleSheet,
  Text,
  View,
  ScrollView,
  TouchableOpacity,
  TextInput,
  StatusBar,
  ActivityIndicator,
  FlatList,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';
import messaging from '@react-native-firebase/messaging';
import axios from 'axios';

export default function App() {
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [jarvisHost, setJarvisHost] = useState('');
  const [jarvisPort, setJarvisPort] = useState('5000');
  const [recentTasks, setRecentTasks] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [inputText, setInputText] = useState('');

  // Initialize on mount
  useEffect(() => {
    initializeApp();
  }, []);

  // Listen for push notifications
  useEffect(() => {
    const unsubscribe = messaging().onMessage(async (remoteMessage) => {
      handleNotification(remoteMessage);
    });

    messaging().onNotificationOpenedApp((remoteMessage) => {
      handleNotification(remoteMessage);
    });

    return unsubscribe;
  }, []);

  // Periodically sync with desktop
  useEffect(() => {
    if (connected) {
      const interval = setInterval(syncWithDesktop, 10000);
      return () => clearInterval(interval);
    }
  }, [connected]);

  const initializeApp = async () => {
    try {
      // Restore connection settings
      const host = await AsyncStorage.getItem('jarvisHost');
      const port = await AsyncStorage.getItem('jarvisPort');

      if (host) {
        setJarvisHost(host);
        setJarvisPort(port || '5000');
        
        // Try to connect
        const isConnected = await attemptConnection(host, port || '5000');
        setConnected(isConnected);
      }
    } catch (error) {
      console.error('Initialization error:', error);
    } finally {
      setLoading(false);
    }
  };

  const attemptConnection = async (host, port) => {
    try {
      const response = await axios.get(
        `http://${host}:${port}/api/status`,
        { timeout: 5000 }
      );
      return response.status === 200;
    } catch (error) {
      return false;
    }
  };

  const handleConnect = async () => {
    const isConnected = await attemptConnection(jarvisHost, jarvisPort);
    if (isConnected) {
      await AsyncStorage.setItem('jarvisHost', jarvisHost);
      await AsyncStorage.setItem('jarvisPort', jarvisPort);
      setConnected(true);
      syncWithDesktop();
    } else {
      alert('Could not connect to JARVIS. Check host and port.');
    }
  };

  const syncWithDesktop = async () => {
    if (!connected) return;

    try {
      const response = await axios.get(
        `http://${jarvisHost}:${jarvisPort}/api/sync/mobile`,
        { timeout: 5000 }
      );

      if (response.data) {
        setRecentTasks(response.data.tasks || []);
      }
    } catch (error) {
      console.error('Sync error:', error);
      setConnected(false);
    }
  };

  const sendCommand = async () => {
    if (!inputText.trim()) return;

    try {
      setLoading(true);
      const response = await axios.post(
        `http://${jarvisHost}:${jarvisPort}/api/command`,
        { text: inputText },
        { timeout: 10000 }
      );

      // Add to notifications
      if (response.data.result) {
        setNotifications([
          { id: Date.now().toString(), text: response.data.result, type: 'result' },
          ...notifications,
        ]);
      }

      setInputText('');
      syncWithDesktop();
    } catch (error) {
      setNotifications([
        { id: Date.now().toString(), text: 'Command failed: ' + error.message, type: 'error' },
        ...notifications,
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleNotification = (remoteMessage) => {
    const notification = {
      id: remoteMessage.messageId,
      title: remoteMessage.notification?.title || 'JARVIS',
      text: remoteMessage.notification?.body || '',
      type: 'notification',
      timestamp: new Date().toLocaleTimeString(),
    };

    setNotifications((prev) => [notification, ...prev.slice(0, 9)]);
  };

  const quickAction = async (action) => {
    setInputText(action);
    await new Promise((resolve) => setTimeout(resolve, 100));
    sendCommand();
  };

  if (loading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#0066ff" />
        <Text style={styles.loadingText}>Loading JARVIS...</Text>
      </View>
    );
  }

  if (!connected) {
    return (
      <View style={styles.container}>
        <StatusBar barStyle="dark-content" />
        <View style={styles.header}>
          <Text style={styles.headerTitle}>JARVIS Mobile</Text>
        </View>

        <View style={styles.setupContainer}>
          <Text style={styles.setupTitle}>Connect to JARVIS Desktop</Text>

          <TextInput
            style={styles.input}
            placeholder="Host (e.g., 192.168.1.100)"
            value={jarvisHost}
            onChangeText={setJarvisHost}
            autoCapitalize="none"
          />

          <TextInput
            style={styles.input}
            placeholder="Port (default: 5000)"
            value={jarvisPort}
            onChangeText={setJarvisPort}
            keyboardType="number-pad"
          />

          <TouchableOpacity style={styles.connectButton} onPress={handleConnect}>
            <Text style={styles.connectButtonText}>Connect</Text>
          </TouchableOpacity>

          <Text style={styles.hint}>
            Make sure your desktop JARVIS is running and accessible on your network.
          </Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#333" />

      <View style={styles.header}>
        <Text style={styles.headerTitle}>JARVIS</Text>
        <View style={styles.connectionBadge}>
          <View style={styles.connectionDot} />
          <Text style={styles.connectionText}>Connected</Text>
        </View>
      </View>

      <ScrollView style={styles.content}>
        {/* Quick Actions */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Quick Actions</Text>
          <View style={styles.quickActionsGrid}>
            <QuickActionButton
              title="📋 Tasks"
              onPress={() => quickAction('Show my tasks')}
            />
            <QuickActionButton
              title="🧠 Memory"
              onPress={() => quickAction('What do you know about me?')}
            />
            <QuickActionButton
              title="⚙️ Settings"
              onPress={() => quickAction('Open settings')}
            />
            <QuickActionButton
              title="🔗 Integrations"
              onPress={() => quickAction('Show integrations')}
            />
          </View>
        </View>

        {/* Recent Tasks */}
        {recentTasks.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Recent Tasks</Text>
            {recentTasks.map((task) => (
              <View key={task.id} style={styles.taskItem}>
                <Text style={styles.taskTitle}>{task.title}</Text>
                <Text style={styles.taskStatus}>{task.status}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Notifications */}
        {notifications.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Recent Activity</Text>
            {notifications.map((notif) => (
              <View key={notif.id} style={[styles.notificationItem, { borderLeftColor: notif.type === 'error' ? '#f44336' : '#4caf50' }]}>
                <Text style={styles.notificationText}>{notif.text}</Text>
                {notif.timestamp && <Text style={styles.notificationTime}>{notif.timestamp}</Text>}
              </View>
            ))}
          </View>
        )}
      </ScrollView>

      {/* Command Input */}
      <View style={styles.inputContainer}>
        <TextInput
          style={styles.commandInput}
          placeholder="Tell JARVIS something..."
          placeholderTextColor="#999"
          value={inputText}
          onChangeText={setInputText}
          editable={!loading}
        />
        <TouchableOpacity
          style={[styles.sendButton, loading && styles.sendButtonDisabled]}
          onPress={sendCommand}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator size="small" color="white" />
          ) : (
            <Text style={styles.sendButtonText}>Send</Text>
          )}
        </TouchableOpacity>
      </View>
    </View>
  );
}

function QuickActionButton({ title, onPress }) {
  return (
    <TouchableOpacity style={styles.quickActionButton} onPress={onPress}>
      <Text style={styles.quickActionText}>{title}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#fff',
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
    color: '#666',
  },
  header: {
    backgroundColor: '#333',
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
  },
  connectionBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1b5e20',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },
  connectionDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#4caf50',
    marginRight: 4,
  },
  connectionText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
  setupContainer: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  setupTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    marginBottom: 24,
    textAlign: 'center',
  },
  input: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 4,
    padding: 12,
    marginBottom: 12,
    fontSize: 14,
  },
  connectButton: {
    backgroundColor: '#0066ff',
    paddingVertical: 12,
    borderRadius: 4,
    alignItems: 'center',
    marginTop: 12,
  },
  connectButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },
  hint: {
    marginTop: 16,
    fontSize: 12,
    color: '#666',
    textAlign: 'center',
  },
  content: {
    flex: 1,
    padding: 16,
  },
  section: {
    marginBottom: 20,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: 'bold',
    marginBottom: 12,
    color: '#333',
    textTransform: 'uppercase',
  },
  quickActionsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  quickActionButton: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: '#fff',
    padding: 16,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: '#ddd',
    alignItems: 'center',
  },
  quickActionText: {
    fontSize: 14,
    textAlign: 'center',
  },
  taskItem: {
    backgroundColor: '#fff',
    padding: 12,
    marginBottom: 8,
    borderRadius: 4,
    borderLeftWidth: 4,
    borderLeftColor: '#0066ff',
  },
  taskTitle: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 4,
  },
  taskStatus: {
    fontSize: 12,
    color: '#666',
  },
  notificationItem: {
    backgroundColor: '#fff',
    padding: 12,
    marginBottom: 8,
    borderRadius: 4,
    borderLeftWidth: 4,
  },
  notificationText: {
    fontSize: 12,
    color: '#333',
  },
  notificationTime: {
    fontSize: 10,
    color: '#999',
    marginTop: 4,
  },
  inputContainer: {
    flexDirection: 'row',
    padding: 12,
    backgroundColor: '#fff',
    borderTopWidth: 1,
    borderTopColor: '#ddd',
  },
  commandInput: {
    flex: 1,
    backgroundColor: '#f5f5f5',
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 10,
    marginRight: 8,
    fontSize: 14,
  },
  sendButton: {
    backgroundColor: '#0066ff',
    paddingHorizontal: 20,
    justifyContent: 'center',
    borderRadius: 20,
  },
  sendButtonDisabled: {
    opacity: 0.6,
  },
  sendButtonText: {
    color: '#fff',
    fontWeight: 'bold',
  },
});
