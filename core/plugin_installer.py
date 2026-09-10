"""Plugin installer: install, remove, upgrade, and manage plugin lifecycle."""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
from urllib.request import urlopen
from urllib.error import URLError

from core.plugin_manifest import PluginManifest, discover_manifest, validate_manifest, ManifestError


class PluginInstaller:
    """Manages plugin installation, removal, and upgrades."""

    def __init__(self, plugins_dir: Path, marketplace_urls: Optional[list[str]] = None):
        self.plugins_dir = Path(plugins_dir)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.marketplace_urls = marketplace_urls or [
            "https://jarvis-marketplace.local/plugins/index.json",  # local/self-hosted example
        ]

    def install_from_path(self, source_path: str | Path, allow_replace: bool = False) -> tuple[bool, str]:
        """
        Install a plugin from a local .zip file or directory.

        Returns (success, message).
        """
        source = Path(source_path)
        if not source.exists():
            return False, f"Plugin source not found: {source}"

        try:
            if source.is_file() and source.suffix == ".zip":
                return self._install_from_zip(source, allow_replace)
            elif source.is_dir():
                return self._install_from_directory(source, allow_replace)
            else:
                return False, f"Plugin source must be a .zip file or directory, got: {source}"
        except Exception as exc:
            return False, f"Installation failed: {exc}"

    def install_from_marketplace(self, plugin_name: str, version: Optional[str] = None) -> tuple[bool, str]:
        """
        Install a plugin from the marketplace (remote registry).

        Returns (success, message).
        """
        plugin_info = self.search_marketplace(plugin_name, version)
        if not plugin_info:
            return False, f"Plugin '{plugin_name}' not found in marketplace"

        download_url = plugin_info.get("download_url")
        if not download_url:
            return False, f"Marketplace entry for '{plugin_name}' has no download_url"

        try:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_path = Path(tmp.name)
                with urlopen(download_url, timeout=30) as response:
                    tmp_path.write_bytes(response.read())
            success, msg = self._install_from_zip(tmp_path, allow_replace=True)
            tmp_path.unlink(missing_ok=True)
            return success, msg
        except URLError as exc:
            return False, f"Could not download from marketplace: {exc}"

    def uninstall(self, plugin_name: str, keep_config: bool = False) -> tuple[bool, str]:
        """
        Remove an installed plugin.

        If keep_config is True, preserve config.json so re-installation keeps settings.
        Returns (success, message).
        """
        plugin_dir = self.plugins_dir / plugin_name
        if not plugin_dir.is_dir():
            return False, f"Plugin '{plugin_name}' is not installed"

        try:
            if keep_config:
                config_file = plugin_dir / "config.json"
                config_backup = None
                if config_file.is_file():
                    config_backup = config_file.read_bytes()
                shutil.rmtree(plugin_dir)
                if config_backup and not plugin_dir.exists():
                    plugin_dir.mkdir(parents=True, exist_ok=True)
                    (plugin_dir / "config.json").write_bytes(config_backup)
            else:
                shutil.rmtree(plugin_dir)
            return True, f"Plugin '{plugin_name}' uninstalled."
        except Exception as exc:
            return False, f"Could not uninstall plugin: {exc}"

    def upgrade(self, plugin_name: str, version: Optional[str] = None) -> tuple[bool, str]:
        """
        Upgrade an installed plugin to a newer version.

        Preserves config.json by default.
        Returns (success, message).
        """
        current_dir = self.plugins_dir / plugin_name
        if not current_dir.is_dir():
            return False, f"Plugin '{plugin_name}' is not installed"

        # Get current manifest to compare versions
        try:
            current_manifest = discover_manifest(current_dir)
            if not current_manifest:
                return False, f"Cannot read manifest for installed plugin '{plugin_name}'"
        except Exception as exc:
            return False, f"Cannot read current plugin manifest: {exc}"

        # Fetch new version from marketplace
        plugin_info = self.search_marketplace(plugin_name, version)
        if not plugin_info:
            return False, f"Plugin '{plugin_name}' version {version or 'latest'} not found in marketplace"

        new_version = plugin_info.get("version")
        if not new_version:
            return False, "Marketplace entry has no version"

        # Simple version comparison: new_version should be > current_version
        if not self._compare_versions(new_version, current_manifest.version):
            return False, f"Marketplace has version {new_version}, already installed {current_manifest.version}"

        # Backup config
        config_file = current_dir / "config.json"
        config_backup = None
        if config_file.is_file():
            config_backup = config_file.read_bytes()

        # Uninstall old, install new
        success, msg = self.uninstall(plugin_name, keep_config=True)
        if not success:
            return False, f"Could not uninstall old version: {msg}"

        success, msg = self.install_from_marketplace(plugin_name, version)
        if not success:
            # Try to restore backup
            if config_backup:
                plugin_dir = self.plugins_dir / plugin_name
                plugin_dir.mkdir(parents=True, exist_ok=True)
                (plugin_dir / "config.json").write_bytes(config_backup)
            return False, f"Could not install new version: {msg}"

        return True, f"Plugin '{plugin_name}' upgraded to {new_version}."

    def enable_plugin(self, plugin_name: str) -> tuple[bool, str]:
        """Enable a disabled plugin."""
        plugin_dir = self.plugins_dir / plugin_name
        if not plugin_dir.is_dir():
            return False, f"Plugin '{plugin_name}' is not installed"

        try:
            manifest = discover_manifest(plugin_dir)
            if not manifest:
                return False, f"Cannot read manifest for plugin '{plugin_name}'"
            manifest.enabled = True
            manifest_file = plugin_dir / "manifest.json"
            manifest_file.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
            return True, f"Plugin '{plugin_name}' enabled."
        except Exception as exc:
            return False, f"Could not enable plugin: {exc}"

    def disable_plugin(self, plugin_name: str) -> tuple[bool, str]:
        """Disable a plugin without uninstalling it."""
        plugin_dir = self.plugins_dir / plugin_name
        if not plugin_dir.is_dir():
            return False, f"Plugin '{plugin_name}' is not installed"

        try:
            manifest = discover_manifest(plugin_dir)
            if not manifest:
                return False, f"Cannot read manifest for plugin '{plugin_name}'"
            manifest.enabled = False
            manifest_file = plugin_dir / "manifest.json"
            manifest_file.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
            return True, f"Plugin '{plugin_name}' disabled."
        except Exception as exc:
            return False, f"Could not disable plugin: {exc}"

    def search_marketplace(self, query: str = "", version: Optional[str] = None) -> Optional[dict]:
        """Search the marketplace for a plugin. Returns plugin info dict or None."""
        for marketplace_url in self.marketplace_urls:
            try:
                with urlopen(marketplace_url, timeout=10) as response:
                    index = json.loads(response.read().decode("utf-8"))
                    plugins = index.get("plugins", [])
                    for p in plugins:
                        if p.get("name").lower() == query.lower():
                            if version:
                                versions = p.get("versions", {})
                                if version in versions:
                                    return versions[version]
                            else:
                                latest = p.get("latest")
                                return latest or (p.get("versions", {}).get(p.get("version")) if p.get("version") else None)
            except URLError:
                continue  # try next marketplace URL
        return None

    def list_marketplace(self, tag: str = "") -> list[dict]:
        """List available plugins from the marketplace, optionally filtered by tag."""
        results = []
        for marketplace_url in self.marketplace_urls:
            try:
                with urlopen(marketplace_url, timeout=10) as response:
                    index = json.loads(response.read().decode("utf-8"))
                    plugins = index.get("plugins", [])
                    for p in plugins:
                        if tag and tag not in p.get("tags", []):
                            continue
                        results.append(p)
            except URLError:
                continue
        return results

    # --- Private helpers ---

    def _install_from_zip(self, zip_path: Path, allow_replace: bool = False) -> tuple[bool, str]:
        """Extract and install a plugin from a .zip file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            try:
                with zipfile.ZipFile(zip_path, "r") as z:
                    z.extractall(tmpdir)
            except zipfile.BadZipFile as exc:
                return False, f"Invalid .zip file: {exc}"

            # Find the manifest in the extracted contents
            manifest = discover_manifest(tmpdir)
            if not manifest:
                # Try one level deeper (plugin might be in a subdirectory)
                for item in tmpdir.iterdir():
                    if item.is_dir():
                        manifest = discover_manifest(item)
                        if manifest:
                            tmpdir = item
                            break

            if not manifest:
                return False, "No manifest.json found in plugin .zip file"

            errors = validate_manifest(manifest)
            if errors:
                return False, f"Manifest validation failed: {'; '.join(errors)}"

            plugin_dir = self.plugins_dir / manifest.name
            if plugin_dir.exists() and not allow_replace:
                return False, f"Plugin '{manifest.name}' is already installed. Use allow_replace=True to overwrite."

            try:
                if plugin_dir.exists():
                    shutil.rmtree(plugin_dir)
                shutil.copytree(tmpdir, plugin_dir)
                return True, f"Plugin '{manifest.name}' v{manifest.version} installed successfully."
            except Exception as exc:
                return False, f"Failed to copy plugin files: {exc}"

    def _install_from_directory(self, dir_path: Path, allow_replace: bool = False) -> tuple[bool, str]:
        """Install a plugin from a local directory (copy it to plugins_dir)."""
        manifest = discover_manifest(dir_path)
        if not manifest:
            return False, f"No manifest.json found in {dir_path}"

        errors = validate_manifest(manifest)
        if errors:
            return False, f"Manifest validation failed: {'; '.join(errors)}"

        plugin_dir = self.plugins_dir / manifest.name
        if plugin_dir.exists() and not allow_replace:
            return False, f"Plugin '{manifest.name}' is already installed. Use allow_replace=True to overwrite."

        try:
            if plugin_dir.exists():
                shutil.rmtree(plugin_dir)
            shutil.copytree(dir_path, plugin_dir)
            return True, f"Plugin '{manifest.name}' v{manifest.version} installed successfully."
        except Exception as exc:
            return False, f"Failed to copy plugin files: {exc}"

    @staticmethod
    def _compare_versions(v1: str, v2: str) -> bool:
        """Return True if v1 > v2 (simple semantic version comparison)."""
        try:
            v1_parts = [int(p) for p in v1.split(".")[:3]]
            v2_parts = [int(p) for p in v2.split(".")[:3]]
            v1_parts += [0] * (3 - len(v1_parts))
            v2_parts += [0] * (3 - len(v2_parts))
            return tuple(v1_parts) > tuple(v2_parts)
        except (ValueError, AttributeError):
            return False
