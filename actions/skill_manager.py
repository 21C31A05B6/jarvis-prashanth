"""Skill/plugin management: install, remove, list, configure, and manage plugins.

This action is the user-facing interface for the plugin system. It handles:
  - Installing/removing plugins
  - Listing installed and marketplace plugins
  - Enabling/disabling plugins
  - Configuring plugin settings
  - Checking plugin permissions
  - Viewing plugin details and version info
"""

from __future__ import annotations

from pathlib import Path
from core.plugin_installer import PluginInstaller
from core.plugin_registry import PluginRegistry, get_default_plugins_dir
from core.plugin_config import PluginConfigManager, ConfigError
from core.plugin_permissions import get_permission_guard, PluginPermissionGuard


_installer = None
_registry = None
_config_manager = None


def _get_installer() -> PluginInstaller:
    global _installer
    if _installer is None:
        plugins_dir = get_default_plugins_dir()
        _installer = PluginInstaller(plugins_dir)
    return _installer


def _get_registry() -> PluginRegistry:
    global _registry
    if _registry is None:
        plugins_dir = get_default_plugins_dir()
        _registry = PluginRegistry(plugins_dir)
    return _registry


def _get_config_manager() -> PluginConfigManager:
    global _config_manager
    if _config_manager is None:
        plugins_dir = get_default_plugins_dir()
        _config_manager = PluginConfigManager(plugins_dir)
    return _config_manager


def _install(params: dict) -> str:
    """Install a plugin from a local path or marketplace."""
    source = str(params.get("source") or params.get("path") or "").strip()
    allow_replace = str(params.get("allow_replace") or "false").lower() in ("true", "yes", "1")

    if not source:
        return (
            "To install a skill, provide either:\n"
            "- 'source' = local path to a .zip file or plugin directory\n"
            "- 'source' = plugin name from marketplace (searched online)\n"
            "Pass 'allow_replace=true' to overwrite an existing plugin."
        )

    installer = _get_installer()

    # Try as local path first
    local_path = Path(source).expanduser()
    if local_path.exists():
        success, msg = installer.install_from_path(local_path, allow_replace=allow_replace)
        if success:
            _refresh_registry()
        return msg

    # Try as marketplace name
    success, msg = installer.install_from_marketplace(source)
    if success:
        _refresh_registry()
    return msg


def _remove(params: dict) -> str:
    """Uninstall a plugin."""
    name = str(params.get("plugin") or params.get("name") or "").strip()
    if not name:
        return "A plugin name is required."
    keep_config = str(params.get("keep_config") or "false").lower() in ("true", "yes", "1")
    installer = _get_installer()
    success, msg = installer.uninstall(name, keep_config=keep_config)
    if success:
        _refresh_registry()
    return msg


def _upgrade(params: dict) -> str:
    """Upgrade a plugin to the latest or specified version."""
    name = str(params.get("plugin") or params.get("name") or "").strip()
    version = str(params.get("version") or "").strip() or None
    if not name:
        return "A plugin name is required."
    installer = _get_installer()
    success, msg = installer.upgrade(name, version=version)
    if success:
        _refresh_registry()
    return msg


def _enable(params: dict) -> str:
    """Enable a disabled plugin."""
    name = str(params.get("plugin") or params.get("name") or "").strip()
    if not name:
        return "A plugin name is required."
    installer = _get_installer()
    success, msg = installer.enable_plugin(name)
    if success:
        _refresh_registry()
    return msg


def _disable(params: dict) -> str:
    """Disable a plugin without uninstalling it."""
    name = str(params.get("plugin") or params.get("name") or "").strip()
    if not name:
        return "A plugin name is required."
    installer = _get_installer()
    success, msg = installer.disable_plugin(name)
    if success:
        _refresh_registry()
    return msg


def _list_installed(params: dict) -> str:
    """List installed plugins."""
    registry = _get_registry()
    plugins = registry.list_plugins()
    if not plugins:
        return "No plugins are currently installed."
    lines = ["Installed plugins:"]
    for p in plugins:
        status = "enabled" if p.enabled else "disabled"
        lines.append(f"- {p.name} v{p.version} ({status}): {p.title}")
        if p.description:
            lines.append(f"  {p.description}")
    return "\n".join(lines)


def _list_marketplace(params: dict) -> str:
    """List available plugins on the marketplace."""
    tag = str(params.get("tag") or "").strip()
    installer = _get_installer()
    plugins = installer.list_marketplace(tag=tag)
    if not plugins:
        if tag:
            return f"No marketplace plugins found with tag '{tag}'."
        return "Marketplace is empty or unreachable."
    lines = ["Marketplace plugins:"]
    for p in plugins:
        latest_version = p.get("version", "?")
        lines.append(f"- {p.get('name')} v{latest_version}: {p.get('title', p.get('description', 'no description'))}")
        if p.get("tags"):
            lines.append(f"  Tags: {', '.join(p['tags'])}")
    return "\n".join(lines)


def _show_details(params: dict) -> str:
    """Show detailed information about an installed plugin."""
    name = str(params.get("plugin") or params.get("name") or "").strip()
    if not name:
        return "A plugin name is required."
    registry = _get_registry()
    plugin = registry.get_plugin(name)
    if not plugin:
        return f"Plugin '{name}' is not installed."
    m = plugin.manifest
    lines = [
        f"Name: {m.name}",
        f"Title: {m.title}",
        f"Version: {m.version}",
        f"Status: {'enabled' if m.enabled else 'disabled'}",
        f"Author: {m.author}",
        f"License: {m.license}",
        f"Description: {m.description}",
    ]
    if m.homepage:
        lines.append(f"Homepage: {m.homepage}")
    if m.repository:
        lines.append(f"Repository: {m.repository}")
    if m.actions:
        lines.append("Actions:")
        for action in m.actions:
            perms = ", ".join(p.value for p in action.permissions) if action.permissions else "safe"
            lines.append(f"  - {action.name} ({perms})")
            if action.description:
                lines.append(f"    {action.description}")
    if plugin.config:
        lines.append(f"Config: {plugin.config}")
    return "\n".join(lines)


def _show_permissions(params: dict) -> str:
    """Show required permissions for a plugin."""
    name = str(params.get("plugin") or params.get("name") or "").strip()
    if not name:
        return "A plugin name is required."
    registry = _get_registry()
    plugin = registry.get_plugin(name)
    if not plugin:
        return f"Plugin '{name}' is not installed."
    guard = get_permission_guard()
    required = guard.list_required_permissions(plugin.manifest)
    if not required:
        return f"Plugin '{name}' does not require any special permissions (safe mode only)."
    lines = [f"Permissions required by '{name}':"]
    for perm in sorted(required, key=lambda p: p.value):
        lines.append(f"- {perm.value}")
    return "\n".join(lines)


def _set_config(params: dict) -> str:
    """Set a configuration value for a plugin."""
    name = str(params.get("plugin") or params.get("name") or "").strip()
    key = str(params.get("key") or "").strip()
    value = params.get("value")
    if not name or not key or value is None:
        return "plugin, key, and value are all required."
    config_manager = _get_config_manager()
    registry = _get_registry()
    plugin = registry.get_plugin(name)
    manifest = plugin.manifest if plugin else None
    try:
        config_manager.set_config_value(name, key, value, manifest=manifest)
        return f"Set {name}.{key} = {value}"
    except ConfigError as exc:
        return str(exc)


def _get_config(params: dict) -> str:
    """Get a configuration value for a plugin."""
    name = str(params.get("plugin") or params.get("name") or "").strip()
    key = str(params.get("key") or "").strip()
    if not name:
        return "A plugin name is required."
    config_manager = _get_config_manager()
    if key:
        value = config_manager.get_config_value(name, key)
        return f"{name}.{key} = {value}"
    try:
        config = config_manager.load_config(name)
        return f"Config for '{name}':\n{config}"
    except ConfigError as exc:
        return str(exc)


def _reset_config(params: dict) -> str:
    """Reset a plugin's configuration to defaults (delete config.json)."""
    name = str(params.get("plugin") or params.get("name") or "").strip()
    if not name:
        return "A plugin name is required."
    config_manager = _get_config_manager()
    if config_manager.reset_config(name):
        return f"Configuration for '{name}' has been reset to defaults."
    return f"Could not reset config for '{name}'."


def _list_actions(params: dict) -> str:
    """List actions exported by installed plugins."""
    registry = _get_registry()
    actions = registry.list_actions()
    if not actions:
        return "No plugin actions are currently available."
    lines = ["Plugin actions:"]
    for action_name, plugin_name in sorted(actions.items()):
        lines.append(f"- {action_name} (from {plugin_name})")
    return "\n".join(lines)


def _refresh_registry() -> None:
    """Force a refresh of the plugin registry after install/remove/enable/disable."""
    global _registry
    if _registry:
        _registry.discover_all()


def _status() -> str:
    """Show overall plugin system status."""
    registry = _get_registry()
    plugins = registry.list_plugins()
    actions = registry.list_actions()
    enabled = sum(1 for p in plugins if p.enabled)
    return (
        f"Plugin system status:\n"
        f"- Installed: {len(plugins)} plugin(s) ({enabled} enabled)\n"
        f"- Actions: {len(actions)} action(s) available\n"
        f"- Directory: {_get_installer().plugins_dir}"
    )


def skill_manager(parameters: dict = None, response=None, player=None, session_memory=None) -> str:
    """Manage JARVIS skills and plugins."""
    params = parameters or {}
    action = str(params.get("action", "status")).lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {
        "install": "install",
        "add": "install",
        "download": "install",
        "uninstall": "remove",
        "delete": "remove",
        "list": "list_installed",
        "installed": "list_installed",
        "marketplace": "list_marketplace",
        "available": "list_marketplace",
        "info": "show_details",
        "details": "show_details",
        "perms": "show_permissions",
        "on": "enable",
        "off": "disable",
        "conf": "set_config",
        "config": "get_config",
    }
    action = aliases.get(action, action)
    if player:
        player.write_log(f"[SkillManager] {action}")

    try:
        if action == "install":
            return _install(params)
        if action == "remove":
            return _remove(params)
        if action == "upgrade":
            return _upgrade(params)
        if action == "enable":
            return _enable(params)
        if action == "disable":
            return _disable(params)
        if action == "list_installed":
            return _list_installed(params)
        if action == "list_marketplace":
            return _list_marketplace(params)
        if action == "show_details":
            return _show_details(params)
        if action == "show_permissions":
            return _show_permissions(params)
        if action == "set_config":
            return _set_config(params)
        if action == "get_config":
            return _get_config(params)
        if action == "reset_config":
            return _reset_config(params)
        if action == "list_actions":
            return _list_actions(params)
        if action == "status":
            return _status()
        return f"Unknown skill_manager action: {action}"
    except Exception as exc:
        return f"Skill manager error: {exc}"
