"""Plugin registry: discover and load installed plugins from the filesystem."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional
from dataclasses import dataclass, asdict

from core.plugin_manifest import PluginManifest, discover_manifest, validate_manifest


@dataclass
class LoadedPlugin:
    """A plugin that has been discovered and loaded into memory."""
    manifest: PluginManifest
    module: Any  # the loaded Python module
    action_functions: dict[str, Callable]  # action_name -> callable
    installed_at: Path  # where the plugin is on disk
    config: dict = None  # runtime config overrides


class PluginRegistry:
    """Discovers and manages all installed plugins."""

    def __init__(self, plugins_dir: Path, jarvis_version: str = "2.1.0"):
        self.plugins_dir = Path(plugins_dir)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.jarvis_version = jarvis_version
        self._loaded_plugins: dict[str, LoadedPlugin] = {}
        self._all_actions: dict[str, tuple[str, Callable]] = {}  # action_name -> (plugin_name, fn)

    def discover_all(self) -> dict[str, LoadedPlugin]:
        """Scan plugins_dir for all installed plugins, load them, and return a dict."""
        self._loaded_plugins = {}
        self._all_actions = {}

        if not self.plugins_dir.exists():
            return {}

        for item in self.plugins_dir.iterdir():
            if not item.is_dir() or item.name.startswith("_"):
                continue
            try:
                plugin = self._load_plugin(item)
                if plugin:
                    self._loaded_plugins[plugin.manifest.name] = plugin
                    for action_name in plugin.action_functions:
                        if action_name in self._all_actions:
                            first_plugin = self._all_actions[action_name][0]
                            raise ValueError(
                                f"Action '{action_name}' is defined by both "
                                f"{first_plugin} and {plugin.manifest.name}"
                            )
                        self._all_actions[action_name] = (plugin.manifest.name, plugin.action_functions[action_name])
            except Exception as exc:
                # Log but don't crash on bad plugins
                print(f"[PluginRegistry] Failed to load plugin from {item}: {exc}")

        return self._loaded_plugins

    def get_plugin(self, name: str) -> Optional[LoadedPlugin]:
        """Return a loaded plugin by name, or None."""
        return self._loaded_plugins.get(name)

    def get_action(self, name: str) -> Optional[Callable]:
        """Return an action function by name (from any plugin), or None."""
        if name in self._all_actions:
            return self._all_actions[name][1]
        return None

    def list_plugins(self) -> list[PluginManifest]:
        """Return all loaded plugin manifests."""
        return [p.manifest for p in self._loaded_plugins.values()]

    def list_actions(self) -> dict[str, str]:
        """Return a map of action_name -> plugin_name for all loaded actions."""
        return {name: plugin_name for name, (plugin_name, _) in self._all_actions.items()}

    def _load_plugin(self, plugin_dir: Path) -> Optional[LoadedPlugin]:
        """Load a single plugin from a directory. Returns None if manifest is disabled."""
        manifest = discover_manifest(plugin_dir)
        if not manifest:
            raise ValueError(f"No manifest.json found in {plugin_dir}")

        if not manifest.enabled:
            return None  # silently skip disabled plugins

        errors = validate_manifest(manifest, self.jarvis_version)
        if errors:
            raise ValueError(f"Manifest validation failed: {'; '.join(errors)}")

        # Dynamically import the module
        module = self._load_module(manifest.entry_point, plugin_dir)

        # Extract action functions
        actions = {}
        for action_schema in manifest.actions:
            fn = getattr(module, action_schema.name, None)
            if not callable(fn):
                raise AttributeError(
                    f"Plugin {manifest.name} declares action '{action_schema.name}' "
                    f"but module does not export a callable with that name"
                )
            actions[action_schema.name] = fn

        # Load runtime config if present
        config_file = plugin_dir / "config.json"
        config = {}
        if config_file.is_file():
            try:
                config = json.loads(config_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                config = {}

        return LoadedPlugin(
            manifest=manifest,
            module=module,
            action_functions=actions,
            installed_at=plugin_dir,
            config=config,
        )

    def _load_module(self, entry_point: str, plugin_dir: Path) -> Any:
        """
        Load a Python module from the entry_point string.

        Supported formats:
          - "weather_pro.py" → import file as module
          - "myplugin/__init__.py" or "myplugin" → import package
          - "myplugin:helper_fn" → import package, ignore the function part (use module)
        """
        entry_point = entry_point.strip()
        if ":" in entry_point:
            entry_point = entry_point.split(":", 1)[0]

        # Try as a Python file first
        if entry_point.endswith(".py"):
            path = plugin_dir / entry_point
            if path.is_file():
                return self._import_file_as_module(path, plugin_dir.name)

        # Try as a package
        pkg_dir = plugin_dir / entry_point.replace(".", "/")
        init_file = pkg_dir / "__init__.py"
        if init_file.is_file():
            return self._import_file_as_module(init_file, entry_point)

        # Try as __init__.py in the plugin_dir itself
        init_file = plugin_dir / "__init__.py"
        if init_file.is_file():
            return self._import_file_as_module(init_file, plugin_dir.name)

        raise ImportError(f"Could not load module from entry_point '{entry_point}' in {plugin_dir}")

    @staticmethod
    def _import_file_as_module(file_path: Path, module_name: str) -> Any:
        """Dynamically import a Python file as a module."""
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if not spec or not spec.loader:
            raise ImportError(f"Could not create module spec for {file_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def reload_plugin(self, name: str) -> bool:
        """Reload a plugin by name. Return True if successful."""
        plugin = self.get_plugin(name)
        if not plugin:
            return False
        try:
            reloaded = self._load_plugin(plugin.installed_at)
            if reloaded:
                self._loaded_plugins[name] = reloaded
                # Rebuild action map
                for action_name in reloaded.action_functions:
                    self._all_actions[action_name] = (name, reloaded.action_functions[action_name])
            return True
        except Exception:
            return False


def get_default_plugins_dir() -> Path:
    """Return the default directory for user-installed plugins."""
    from pathlib import Path
    home = Path.home()
    return home / ".jarvis" / "plugins"
