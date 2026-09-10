"""Plugin configuration management: load, validate, update, and persist config per plugin."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass

from core.plugin_manifest import PluginManifest


@dataclass
class ConfigError(Exception):
    """Raised when plugin config is invalid."""
    plugin_name: str
    message: str

    def __str__(self) -> str:
        return f"Config error for {self.plugin_name}: {self.message}"


class PluginConfigManager:
    """Load, validate, and persist configuration for installed plugins."""

    def __init__(self, plugins_dir: Path):
        self.plugins_dir = Path(plugins_dir)

    def _config_file(self, plugin_name: str) -> Path:
        """Return the path to a plugin's config.json file."""
        return self.plugins_dir / plugin_name / "config.json"

    def load_config(self, plugin_name: str, manifest: Optional[PluginManifest] = None) -> dict:
        """Load and validate a plugin's config.json. Returns empty dict if not present."""
        config_file = self._config_file(plugin_name)
        if not config_file.is_file():
            return {}

        try:
            config = json.loads(config_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ConfigError(plugin_name, f"Could not parse config.json: {exc}")

        if manifest and manifest.config_schema:
            errors = self._validate_schema(config, manifest.config_schema)
            if errors:
                raise ConfigError(plugin_name, f"Config does not match schema: {'; '.join(errors)}")

        return config

    def save_config(self, plugin_name: str, config: dict, manifest: Optional[PluginManifest] = None) -> bool:
        """Validate and save a plugin's config. Return True if successful."""
        if manifest and manifest.config_schema:
            errors = self._validate_schema(config, manifest.config_schema)
            if errors:
                raise ConfigError(plugin_name, f"Config does not match schema: {'; '.join(errors)}")

        config_file = self._config_file(plugin_name)
        try:
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config_file.write_text(json.dumps(config, indent=2, ensure_ascii=False))
            return True
        except OSError as exc:
            raise ConfigError(plugin_name, f"Could not write config.json: {exc}")

    def update_config(
        self, plugin_name: str, updates: dict, manifest: Optional[PluginManifest] = None
    ) -> dict:
        """Load the current config, apply updates, validate, and save."""
        current = self.load_config(plugin_name, manifest)
        current.update(updates)
        self.save_config(plugin_name, current, manifest)
        return current

    def get_config_value(self, plugin_name: str, key: str, default: Any = None) -> Any:
        """Get a single config value by dot-separated key (e.g., 'api.timeout')."""
        config = self.load_config(plugin_name)
        keys = key.split(".")
        value = config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def set_config_value(self, plugin_name: str, key: str, value: Any, manifest: Optional[PluginManifest] = None) -> None:
        """Set a single config value by dot-separated key."""
        config = self.load_config(plugin_name, manifest)
        keys = key.split(".")
        target = config
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value
        self.save_config(plugin_name, config, manifest)

    def reset_config(self, plugin_name: str) -> bool:
        """Delete a plugin's config.json, reverting to defaults."""
        config_file = self._config_file(plugin_name)
        try:
            if config_file.is_file():
                config_file.unlink()
            return True
        except OSError:
            return False

    def _validate_schema(self, config: dict, schema: dict) -> list[str]:
        """
        Simple JSON schema validation (subset of JSON Schema Draft 7).
        Validates type, required fields, min/max values, enums, etc.
        """
        errors = []

        # Check 'type' constraint
        if "type" in schema:
            expected_type = schema["type"]
            if expected_type == "object":
                if not isinstance(config, dict):
                    errors.append(f"Expected object, got {type(config).__name__}")
            elif expected_type == "array":
                if not isinstance(config, list):
                    errors.append(f"Expected array, got {type(config).__name__}")
            elif expected_type == "string":
                if not isinstance(config, str):
                    errors.append(f"Expected string, got {type(config).__name__}")
            elif expected_type == "number":
                if not isinstance(config, (int, float)):
                    errors.append(f"Expected number, got {type(config).__name__}")
            elif expected_type == "boolean":
                if not isinstance(config, bool):
                    errors.append(f"Expected boolean, got {type(config).__name__}")

        # Check 'enum' constraint
        if "enum" in schema and config not in schema["enum"]:
            errors.append(f"Value {config} not in allowed enum: {schema['enum']}")

        # Check object properties
        if isinstance(config, dict) and "properties" in schema and isinstance(schema["properties"], dict):
            for prop_name, prop_schema in schema["properties"].items():
                if prop_name in config:
                    prop_errors = self._validate_schema(config[prop_name], prop_schema)
                    errors.extend([f"{prop_name}: {e}" for e in prop_errors])

        # Check 'required' fields
        if isinstance(config, dict) and "required" in schema and isinstance(schema["required"], list):
            for required_key in schema["required"]:
                if required_key not in config:
                    errors.append(f"Required property '{required_key}' is missing")

        # Check string minLength/maxLength
        if isinstance(config, str):
            if "minLength" in schema and len(config) < schema["minLength"]:
                errors.append(f"String length {len(config)} < minLength {schema['minLength']}")
            if "maxLength" in schema and len(config) > schema["maxLength"]:
                errors.append(f"String length {len(config)} > maxLength {schema['maxLength']}")

        # Check number minimum/maximum
        if isinstance(config, (int, float)):
            if "minimum" in schema and config < schema["minimum"]:
                errors.append(f"Value {config} < minimum {schema['minimum']}")
            if "maximum" in schema and config > schema["maximum"]:
                errors.append(f"Value {config} > maximum {schema['maximum']}")

        return errors
