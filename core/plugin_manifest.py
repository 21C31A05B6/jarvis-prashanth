"""Plugin/skill manifest schema, validation, and discovery.

A JARVIS plugin is a self-contained module (typically a single Python file or
a folder with __init__.py) that:
  - exports one or more callable actions (functions matching the JARVIS action
    signature: fn(parameters, response, player, session_memory) -> str)
  - includes a manifest.json file declaring metadata, permissions, version,
    dependencies, and where the actions are.

This module validates manifests, discovers installed plugins, and enforces
version compatibility.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Optional
from enum import Enum


class PermissionLevel(str, Enum):
    """Action permission classification; used by plugin_permissions.py to guard execution."""
    SAFE = "safe"  # read-only, no external calls
    NETWORK = "network"  # external API calls (GitHub, Slack, etc.)
    LOCAL_READ = "local_read"  # read files on the local system
    LOCAL_WRITE = "local_write"  # writes to local FS
    LOCAL_EXEC = "local_exec"  # runs local code/commands
    SENSITIVE = "sensitive"  # access to passwords, keychain, private memory


@dataclass
class ActionSchema:
    """Schema for one action exported by a plugin."""
    name: str
    description: str
    permissions: list[PermissionLevel] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    returns: str = "string"


@dataclass
class PluginManifest:
    """Metadata for a plugin/skill."""
    name: str  # e.g., "jarvis-weather-pro" (kebab-case)
    title: str  # e.g., "Weather Pro"
    version: str  # semantic: "1.2.3"
    description: str
    author: str
    license: str = "MIT"
    homepage: str = ""
    repository: str = ""
    plugin_uri: str = ""  # path or URL to the plugin's root
    entry_point: str = ""  # e.g., "weather_pro:main" or "weather_pro.py"
    actions: list[ActionSchema] = field(default_factory=list)
    dependencies: dict[str, str] = field(default_factory=dict)  # name -> version_spec
    min_jarvis_version: str = "2.0.0"
    max_jarvis_version: str = ""  # empty = no upper bound
    permissions: list[PermissionLevel] = field(default_factory=list)  # min set the plugin needs
    config_schema: dict[str, Any] = field(default_factory=dict)  # JSON schema for plugin config
    tags: list[str] = field(default_factory=list)  # e.g. ["weather", "external-api"]
    enabled: bool = True

    def to_dict(self) -> dict:
        data = asdict(self)
        data["permissions"] = [p.value for p in self.permissions]
        data["actions"] = [asdict(a) if isinstance(a, ActionSchema) else a for a in self.actions]
        if isinstance(data["actions"], list):
            for action in data["actions"]:
                if "permissions" in action and isinstance(action["permissions"], list):
                    action["permissions"] = [
                        p.value if isinstance(p, PermissionLevel) else p for p in action["permissions"]
                    ]
        return data

    @staticmethod
    def from_dict(data: dict) -> PluginManifest:
        """Deserialize from dict, converting string enum values back to PermissionLevel."""
        if "permissions" in data and isinstance(data["permissions"], list):
            data["permissions"] = [
                PermissionLevel(p) if isinstance(p, str) else p for p in data["permissions"]
            ]
        if "actions" in data and isinstance(data["actions"], list):
            actions = []
            for a in data["actions"]:
                if isinstance(a, dict):
                    if "permissions" in a and isinstance(a["permissions"], list):
                        a["permissions"] = [
                            PermissionLevel(p) if isinstance(p, str) else p for p in a["permissions"]
                        ]
                    actions.append(ActionSchema(**a))
                else:
                    actions.append(a)
            data["actions"] = actions
        return PluginManifest(**data)


def discover_manifest(plugin_path: Path) -> Optional[PluginManifest]:
    """Discover and parse a manifest.json in a plugin directory or its parent."""
    candidates = [plugin_path / "manifest.json", plugin_path.parent / "manifest.json"]
    for candidate in candidates:
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8")
                data = json.loads(text)
                return PluginManifest.from_dict(data)
            except (OSError, ValueError, TypeError) as exc:
                raise ValueError(f"Invalid manifest at {candidate}: {exc}") from exc
    return None


def validate_manifest(manifest: PluginManifest, jarvis_version: str = "2.1.0") -> list[str]:
    """Return list of validation errors, empty if valid."""
    errors = []

    if not manifest.name or not manifest.name.replace("-", "").replace("_", "").isalnum():
        errors.append(f"Plugin name must be kebab-case or snake_case: {manifest.name}")

    if not manifest.version:
        errors.append("Plugin version is required")
    elif not _is_semver(manifest.version):
        errors.append(f"Plugin version is not semantic: {manifest.version}")

    if not manifest.title:
        errors.append("Plugin title is required")

    if not manifest.description:
        errors.append("Plugin description is required")

    if not manifest.entry_point:
        errors.append("Plugin entry_point is required (e.g., 'myplugin.py' or 'myplugin:main')")

    if manifest.min_jarvis_version and not _is_semver(manifest.min_jarvis_version):
        errors.append(f"min_jarvis_version is not semantic: {manifest.min_jarvis_version}")

    if manifest.max_jarvis_version and not _is_semver(manifest.max_jarvis_version):
        errors.append(f"max_jarvis_version is not semantic: {manifest.max_jarvis_version}")

    if manifest.min_jarvis_version and not _satisfies_version(jarvis_version, manifest.min_jarvis_version, ">="):
        errors.append(f"JARVIS {jarvis_version} < minimum required {manifest.min_jarvis_version}")

    if manifest.max_jarvis_version and not _satisfies_version(jarvis_version, manifest.max_jarvis_version, "<="):
        errors.append(f"JARVIS {jarvis_version} > maximum allowed {manifest.max_jarvis_version}")

    if not manifest.actions:
        errors.append("Plugin must export at least one action")
    else:
        seen_names = set()
        for action in manifest.actions:
            if not action.name:
                errors.append("Action name is required")
            elif action.name in seen_names:
                errors.append(f"Duplicate action name: {action.name}")
            seen_names.add(action.name)
            if not action.description:
                errors.append(f"Action {action.name} description is required")

    return errors


def _is_semver(version: str) -> bool:
    """Check if version string is roughly semantic (X.Y.Z[+metadata])."""
    parts = version.split("+", 1)
    main = parts[0].split("-", 1)[0]
    try:
        v_parts = main.split(".")
        return len(v_parts) >= 2 and all(p.isdigit() for p in v_parts[:3])
    except Exception:
        return False


def _satisfies_version(actual: str, required: str, op: str) -> bool:
    """Simple version comparison: >=, <=, ==, !=."""
    try:
        act_parts = [int(p) for p in actual.split(".")[:3]]
        req_parts = [int(p) for p in required.split(".")[:3]]
        act_parts += [0] * (3 - len(act_parts))
        req_parts += [0] * (3 - len(req_parts))
        act_tuple = tuple(act_parts)
        req_tuple = tuple(req_parts)
        if op == ">=":
            return act_tuple >= req_tuple
        if op == "<=":
            return act_tuple <= req_tuple
        if op == "==":
            return act_tuple == req_tuple
        if op == "!=":
            return act_tuple != req_tuple
        return False
    except (ValueError, AttributeError):
        return False


class ManifestError(ValueError):
    """Raised when a manifest is invalid or unsupported."""
