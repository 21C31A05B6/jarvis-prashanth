"""
REST API server for web dashboard and mobile companion app.

Provides endpoints for:
  - Connection management
  - Command execution
  - Task management
  - Memory/context access
  - Integration status
  - Plugin management
  - Settings sync
  - Real-time updates via WebSocket
"""

from __future__ import annotations

import json
import asyncio
from typing import Any, Optional
from datetime import datetime
from pathlib import Path

try:
    from aiohttp import web
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    import aiofiles
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False


class RemoteAPIServer:
    """REST API server for remote clients (web, mobile, etc.)."""

    def __init__(self, host: str = "0.0.0.0", port: int = 5000, jarvis_backend=None):
        self.host = host
        self.port = port
        self.jarvis_backend = jarvis_backend  # Reference to main JARVIS instance
        self.app = None
        self.runner = None
        self._client_connections: set = set()

    def create_app(self) -> web.Application:
        """Create and configure aiohttp application."""
        if not HAS_AIOHTTP:
            raise ImportError("aiohttp is required for RemoteAPIServer")

        app = web.Application(
            middlewares=[self._cors_middleware, self._auth_middleware],
            client_max_size=10 * 1024 * 1024,  # 10 MB
        )

        # Routes
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/api/status", self._handle_status)
        app.router.add_get("/api/info", self._handle_info)
        app.router.add_post("/api/connect", self._handle_connect)
        app.router.add_post("/api/command", self._handle_command)
        app.router.add_get("/api/sync", self._handle_sync)
        app.router.add_get("/api/sync/mobile", self._handle_sync_mobile)
        app.router.add_post("/api/setting", self._handle_setting)
        app.router.add_get("/api/setting", self._handle_get_setting)
        app.router.add_get("/api/tasks", self._handle_tasks)
        app.router.add_post("/api/task", self._handle_create_task)
        app.router.add_get("/api/memory", self._handle_memory)
        app.router.add_get("/api/integrations", self._handle_integrations)
        app.router.add_get("/api/plugins", self._handle_plugins)
        app.router.add_ws("/ws", self._handle_websocket)

        return app

    async def start(self) -> None:
        """Start the API server."""
        self.app = self.create_app()
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        print(f"[API] Server listening on {self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the API server."""
        if self.runner:
            await self.runner.cleanup()

    # ====== Middleware ======

    @staticmethod
    async def _cors_middleware(app: web.Application, handler) -> Any:
        """Add CORS headers to all responses."""
        async def middleware_handler(request: web.Request) -> Any:
            response = await handler(request)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            return response

        return middleware_handler

    @staticmethod
    async def _auth_middleware(app: web.Application, handler) -> Any:
        """Simple authentication (bypass for now, can be enhanced)."""
        async def middleware_handler(request: web.Request) -> Any:
            # TODO: Implement token-based auth
            return await handler(request)

        return middleware_handler

    # ====== Handlers ======

    async def _handle_index(self, request: web.Request) -> web.Response:
        """Serve API documentation."""
        docs = """
        JARVIS Remote API v2.1.0
        
        Endpoints:
          GET  /api/status       - Connection status
          GET  /api/info         - System information
          POST /api/connect      - Connect to JARVIS backend
          POST /api/command      - Execute a command
          GET  /api/sync         - Sync with backend
          POST /api/setting      - Save a setting
          GET  /api/setting      - Get a setting
          GET  /api/tasks        - List tasks
          POST /api/task         - Create a task
          GET  /api/memory       - Search memory
          GET  /api/integrations - Integration status
          GET  /api/plugins      - Installed plugins
          WS   /ws               - WebSocket for real-time updates
        """
        return web.Response(text=docs, content_type="text/plain")

    async def _handle_status(self, request: web.Request) -> web.Response:
        """Check connection status."""
        status = {
            "connected": bool(self.jarvis_backend),
            "timestamp": datetime.now().isoformat(),
            "version": "2.1.0",
            "clients": len(self._client_connections),
        }
        return web.json_response(status)

    async def _handle_info(self, request: web.Request) -> web.Response:
        """Get system information."""
        from core.platform_detector import PlatformInfo
        info = PlatformInfo.get_info()
        return web.json_response(info)

    async def _handle_connect(self, request: web.Request) -> web.Response:
        """Connect to JARVIS backend."""
        data = await request.json()
        host = data.get("host")
        port = data.get("port")
        # TODO: Implement actual connection logic
        return web.json_response({"success": True, "message": "Connected"})

    async def _handle_command(self, request: web.Request) -> web.Response:
        """Execute a command on JARVIS backend."""
        data = await request.json()
        command = data.get("text") or data.get("command")

        if not command:
            return web.json_response({"error": "No command provided"}, status=400)

        # TODO: Forward to JARVIS backend
        result = f"Executed: {command}"

        return web.json_response({"success": True, "result": result})

    async def _handle_sync(self, request: web.Request) -> web.Response:
        """Sync with JARVIS backend."""
        sync_data = {
            "timestamp": datetime.now().isoformat(),
            "tasks": self._get_mock_tasks(),
            "settings": {},
        }
        return web.json_response(sync_data)

    async def _handle_sync_mobile(self, request: web.Request) -> web.Response:
        """Lightweight sync for mobile app."""
        sync_data = {
            "tasks": self._get_mock_tasks()[:5],  # Only recent tasks
            "notifications": [],
        }
        return web.json_response(sync_data)

    async def _handle_setting(self, request: web.Request) -> web.Response:
        """Save a setting."""
        data = await request.json()
        key = data.get("key")
        value = data.get("value")

        if not key:
            return web.json_response({"error": "No key provided"}, status=400)

        # TODO: Save to persistent storage
        return web.json_response({"success": True, "key": key, "value": value})

    async def _handle_get_setting(self, request: web.Request) -> web.Response:
        """Get a setting."""
        key = request.query.get("key")

        if not key:
            return web.json_response({"error": "No key provided"}, status=400)

        # TODO: Load from persistent storage
        return web.json_response({"key": key, "value": None})

    async def _handle_tasks(self, request: web.Request) -> web.Response:
        """List tasks."""
        tasks = self._get_mock_tasks()
        return web.json_response({"tasks": tasks})

    async def _handle_create_task(self, request: web.Request) -> web.Response:
        """Create a new task."""
        data = await request.json()
        title = data.get("title")

        if not title:
            return web.json_response({"error": "No title provided"}, status=400)

        task = {
            "id": "task_" + datetime.now().isoformat(),
            "title": title,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }

        return web.json_response({"success": True, "task": task})

    async def _handle_memory(self, request: web.Request) -> web.Response:
        """Search memory/context."""
        query = request.query.get("q", "")
        results = {
            "query": query,
            "results": [] if not query else [
                {"type": "fact", "text": f"Fact about: {query}"},
            ],
        }
        return web.json_response(results)

    async def _handle_integrations(self, request: web.Request) -> web.Response:
        """Get integration status."""
        integrations = {
            "gmail": {"connected": False, "status": "Disconnected"},
            "github": {"connected": False, "status": "Disconnected"},
            "slack": {"connected": False, "status": "Disconnected"},
        }
        return web.json_response(integrations)

    async def _handle_plugins(self, request: web.Request) -> web.Response:
        """List installed plugins."""
        plugins = {
            "installed": [
                {"name": "hello-skill", "version": "1.0.0", "enabled": True},
            ],
            "count": 1,
        }
        return web.json_response(plugins)

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections for real-time updates."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._client_connections.add(ws)

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    # Echo back for testing; real implementation would process commands
                    data = json.loads(msg.data)
                    await ws.send_json({"type": "echo", "data": data})
                elif msg.type == web.WSMsgType.ERROR:
                    print(f"WebSocket error: {ws.exception()}")
        finally:
            self._client_connections.discard(ws)

        return ws

    # ====== Utilities ======

    @staticmethod
    def _get_mock_tasks() -> list[dict]:
        """Return mock task list for testing."""
        return [
            {
                "id": "task_1",
                "title": "Review pull request",
                "status": "in_progress",
                "priority": "high",
                "created_at": datetime.now().isoformat(),
            },
            {
                "id": "task_2",
                "title": "Update documentation",
                "status": "pending",
                "priority": "medium",
                "created_at": datetime.now().isoformat(),
            },
        ]
