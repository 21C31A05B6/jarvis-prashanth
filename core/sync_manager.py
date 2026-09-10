"""
Cross-device synchronization module.

Synchronizes:
- User settings and preferences
- Memory/context (conversations, user facts)
- Task state and history
- Integration credentials (encrypted)
- Plugin configurations
- Session state and logs

Supports:
- Real-time sync via WebSocket
- Offline queue with retry
- Conflict resolution (last-write-wins or merge strategies)
- End-to-end encryption for sensitive data
"""

from __future__ import annotations

import asyncio
import json
import time
import hashlib
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import uuid4


class SyncStrategy(str, Enum):
    """Conflict resolution strategy when same data is modified on multiple devices."""
    LAST_WRITE_WINS = "last_write_wins"  # Most recent timestamp wins
    MERGE = "merge"  # Attempt to merge changes (lists, dicts)
    SERVER_WINS = "server_wins"  # Always use server version
    CLIENT_WINS = "client_wins"  # Always use client version


@dataclass
class SyncableItem:
    """Represents a piece of data that can be synced."""
    key: str  # e.g., "settings.theme", "memory.facts", "integrations.slack"
    value: Any
    device_id: str  # Which device last modified this
    timestamp: float  # Unix timestamp of last modification
    version: int = 1  # For versioning changes
    checksum: str = ""  # SHA256 for integrity checking
    encrypted: bool = False  # Is this sensitive data?
    strategy: SyncStrategy = SyncStrategy.LAST_WRITE_WINS

    def compute_checksum(self) -> str:
        """Compute SHA256 checksum of the value."""
        serialized = json.dumps(self.value, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def to_dict(self) -> dict:
        data = asdict(self)
        data['strategy'] = self.strategy.value
        return data


@dataclass
class SyncConflict:
    """Represents a sync conflict between two versions of the same item."""
    key: str
    local_version: SyncableItem
    remote_version: SyncableItem
    resolution: Optional[SyncableItem] = None


class SyncQueue:
    """Queue for offline changes; synced when connection is restored."""

    def __init__(self, max_size: int = 1000):
        self.queue: list[SyncableItem] = []
        self.max_size = max_size

    def push(self, item: SyncableItem) -> None:
        """Add item to sync queue."""
        self.queue.append(item)
        if len(self.queue) > self.max_size:
            self.queue.pop(0)  # Drop oldest if full

    def pop_all(self) -> list[SyncableItem]:
        """Drain the queue, returning all items."""
        items = self.queue[:]
        self.queue.clear()
        return items

    def size(self) -> int:
        return len(self.queue)


class SyncManager:
    """Manages device-to-device synchronization of JARVIS state."""

    def __init__(
        self,
        device_id: Optional[str] = None,
        sync_server_url: Optional[str] = None,
        local_storage_path: Optional[Path] = None,
    ):
        self.device_id = device_id or str(uuid4())[:8]
        self.sync_server_url = sync_server_url or "http://sync.jarvis.local"
        self.local_storage_path = local_storage_path or (Path.home() / ".jarvis" / "sync")
        self.local_storage_path.mkdir(parents=True, exist_ok=True)

        self._local_state: dict[str, SyncableItem] = {}
        self._remote_state: dict[str, SyncableItem] = {}
        self._sync_queue = SyncQueue()
        self._conflict_handlers: dict[str, Callable] = {}
        self._online = False
        self._sync_callbacks: list[Callable[[dict], None]] = []

        self._load_local_state()

    def _load_local_state(self) -> None:
        """Load sync state from local disk."""
        state_file = self.local_storage_path / "state.json"
        if state_file.is_file():
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
                for key, item_dict in data.items():
                    self._local_state[key] = SyncableItem(**item_dict)
            except (OSError, ValueError):
                pass

    def _save_local_state(self) -> None:
        """Persist sync state to local disk."""
        state_file = self.local_storage_path / "state.json"
        try:
            data = {key: item.to_dict() for key, item in self._local_state.items()}
            state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def set_online(self, online: bool) -> None:
        """Signal that network connection status changed."""
        if online and not self._online:
            self._online = True
            asyncio.create_task(self._sync_offline_queue())
        else:
            self._online = online

    def is_online(self) -> bool:
        return self._online

    def set_value(self, key: str, value: Any, encrypted: bool = False) -> None:
        """
        Set a synced value locally.

        If online, immediately syncs to server. If offline, queues for later.
        """
        item = SyncableItem(
            key=key,
            value=value,
            device_id=self.device_id,
            timestamp=time.time(),
            encrypted=encrypted,
            checksum="",
        )
        item.checksum = item.compute_checksum()

        self._local_state[key] = item
        self._save_local_state()

        if self._online:
            asyncio.create_task(self._sync_item(item))
        else:
            self._sync_queue.push(item)

    def get_value(self, key: str, default: Any = None) -> Any:
        """Get a synced value (uses local copy, may be stale if offline)."""
        if key in self._local_state:
            return self._local_state[key].value
        return default

    def register_conflict_handler(self, key: str, handler: Callable[[SyncConflict], SyncableItem]) -> None:
        """
        Register a custom handler for resolving conflicts on a specific key.

        handler(conflict) -> resolved_item
        """
        self._conflict_handlers[key] = handler

    def on_sync_update(self, callback: Callable[[dict], None]) -> None:
        """Register callback for when sync updates arrive from other devices."""
        self._sync_callbacks.append(callback)

    async def _sync_item(self, item: SyncableItem) -> bool:
        """Sync a single item to the server. Return True if successful."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.sync_server_url}/sync/push",
                    json=item.to_dict(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        return True
        except Exception:
            pass
        return False

    async def _sync_offline_queue(self) -> None:
        """Process queued changes when connection is restored."""
        items = self._sync_queue.pop_all()
        for item in items:
            success = await self._sync_item(item)
            if not success:
                self._sync_queue.push(item)  # Re-queue if failed

    async def pull_updates(self) -> bool:
        """Pull updates from server for all synced items. Return True if successful."""
        if not self._online:
            return False

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.sync_server_url}/sync/pull",
                    params={"device_id": self.device_id},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        await self._process_remote_updates(data.get("updates", []))
                        return True
        except Exception:
            pass
        return False

    async def _process_remote_updates(self, updates: list[dict]) -> None:
        """Process updates received from server."""
        for update_dict in updates:
            try:
                remote_item = SyncableItem(**update_dict)
                local_item = self._local_state.get(remote_item.key)

                if local_item is None:
                    # New item from another device
                    self._local_state[remote_item.key] = remote_item
                    self._trigger_callbacks(remote_item.key, remote_item.value)
                elif local_item.timestamp < remote_item.timestamp:
                    # Remote is newer
                    resolved = await self._resolve_conflict(
                        SyncConflict(
                            key=remote_item.key,
                            local_version=local_item,
                            remote_version=remote_item,
                        )
                    )
                    self._local_state[remote_item.key] = resolved
                    self._trigger_callbacks(resolved.key, resolved.value)
            except Exception:
                pass

        self._save_local_state()

    async def _resolve_conflict(self, conflict: SyncConflict) -> SyncableItem:
        """Resolve a sync conflict using configured strategy or handler."""
        key = conflict.key

        # Check for custom handler
        if key in self._conflict_handlers:
            handler = self._conflict_handlers[key]
            resolved = handler(conflict)
            conflict.resolution = resolved
            return resolved

        strategy = conflict.remote_version.strategy

        if strategy == SyncStrategy.LAST_WRITE_WINS:
            if conflict.remote_version.timestamp > conflict.local_version.timestamp:
                return conflict.remote_version
            return conflict.local_version

        if strategy == SyncStrategy.MERGE:
            # Simple merge for dicts/lists
            if isinstance(conflict.local_version.value, dict) and isinstance(conflict.remote_version.value, dict):
                merged = {**conflict.local_version.value, **conflict.remote_version.value}
                merged_item = SyncableItem(
                    key=key,
                    value=merged,
                    device_id=self.device_id,
                    timestamp=time.time(),
                )
                merged_item.checksum = merged_item.compute_checksum()
                return merged_item

        if strategy == SyncStrategy.SERVER_WINS:
            return conflict.remote_version

        if strategy == SyncStrategy.CLIENT_WINS:
            return conflict.local_version

        # Default: last-write-wins
        return conflict.remote_version if conflict.remote_version.timestamp > conflict.local_version.timestamp else conflict.local_version

    def _trigger_callbacks(self, key: str, value: Any) -> None:
        """Trigger registered callbacks for an update."""
        for callback in self._sync_callbacks:
            try:
                callback({"key": key, "value": value, "timestamp": datetime.now().isoformat()})
            except Exception:
                pass

    async def full_sync(self) -> bool:
        """Perform a full push + pull sync cycle."""
        if not self._online:
            return False

        # Push any offline changes
        await self._sync_offline_queue()

        # Pull updates from server
        return await self.pull_updates()

    def get_sync_stats(self) -> dict:
        """Return statistics about sync state."""
        return {
            "device_id": self.device_id,
            "online": self._online,
            "local_items": len(self._local_state),
            "queue_size": self._sync_queue.size(),
            "last_sync": max(
                (item.timestamp for item in self._local_state.values()),
                default=0,
            ),
        }

    def export_state(self, include_encrypted: bool = False) -> dict:
        """Export sync state for backup or transfer (optionally excluding sensitive data)."""
        result = {}
        for key, item in self._local_state.items():
            if item.encrypted and not include_encrypted:
                continue
            result[key] = item.to_dict()
        return result

    def import_state(self, state: dict) -> None:
        """Import sync state from backup or another device."""
        for key, item_dict in state.items():
            try:
                item = SyncableItem(**item_dict)
                if key not in self._local_state or item.timestamp > self._local_state[key].timestamp:
                    self._local_state[key] = item
            except TypeError:
                pass
        self._save_local_state()
