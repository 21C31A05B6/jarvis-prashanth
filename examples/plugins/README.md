# JARVIS Plugin System

This directory contains example plugins that demonstrate the JARVIS plugin/skill system.

## What is a Plugin?

A JARVIS plugin is a self-contained module that extends JARVIS with new actions. Each plugin:

- **Has a manifest** (`manifest.json`) declaring metadata, actions, permissions, and configuration schema
- **Exports Python functions** that implement actions (following the JARVIS action signature)
- **Can have runtime configuration** (`config.json`) stored separately from code
- **Declares permissions** it needs (safe, network, local_read, local_write, local_exec, sensitive)
- **Supports versioning** using semantic versioning (X.Y.Z)
- **Can depend on packages** listed in `dependencies` or assumed to be already installed

## Example Plugins

### 1. hello-skill

A minimal "hello world" plugin demonstrating:
- Simple manifest structure
- Two basic actions (`greet`, `farewell`)
- Safe-mode-only permissions

**Usage:**
```
install skill_manager action=install source=hello-skill
list actions from hello-skill
call greet with name="Alice"
```

### 2. weather-skill

A realistic plugin demonstrating:
- Configuration schema (`config_schema` in manifest)
- External API calls (requires `network` permission)
- Multiple related actions
- Configuration management (default location, units, caching)

**Setup:**
1. Get an OpenWeatherMap API key from https://openweathermap.org/api
2. Configure the plugin: `skill_manager set_config plugin=weather-skill key=api_key value=YOUR_KEY`
3. Use it: `weather-skill get_weather location="New York"`

**Key features:**
- Declarative config schema enforced at save time
- Actions can read/write config via `core.plugin_config.PluginConfigManager`
- Dependency on `requests` is declared in manifest

### 3. file-analyzer

A plugin demonstrating:
- File system permissions (`local_read`, `local_write`)
- Actions with different permission levels
- Recursive directory traversal
- Multiple related analyses in one plugin

**Usage:**
```
skill_manager action=show_permissions plugin=file-analyzer
skill_manager action=show_details plugin=file-analyzer
file-analyzer analyze_file path=/home/user/myfile.py
file-analyzer count_lines directory=/home/user/myproject extensions=py,js
```

## Plugin Directory Structure

```
my-plugin/
├── manifest.json          # Plugin metadata (required)
├── __init__.py            # Main plugin module (required)
├── config.json            # Runtime config (created after first save)
├── config.example.json    # Example config (optional, for docs)
├── README.md              # Plugin documentation (optional)
└── submodule.py           # Additional Python files (optional)
```

## Writing Your Own Plugin

### Step 1: Create manifest.json

```json
{
  "name": "my-skill",
  "title": "My Skill",
  "version": "1.0.0",
  "description": "A plugin that does something useful.",
  "author": "Your Name",
  "license": "MIT",
  "entry_point": "__init__.py",
  "actions": [
    {
      "name": "my_action",
      "description": "Does something useful.",
      "permissions": ["safe"],
      "parameters": {
        "type": "object",
        "properties": {
          "input": {"type": "string", "description": "User input"}
        }
      }
    }
  ],
  "min_jarvis_version": "2.0.0",
  "permissions": ["safe"],
  "config_schema": {
    "type": "object",
    "properties": {
      "setting1": {"type": "string"}
    }
  }
}
```

### Step 2: Implement __init__.py

```python
def my_action(parameters=None, response=None, player=None, session_memory=None) -> str:
    """Implement your action."""
    params = parameters or {}
    
    # Load configuration
    from core.plugin_config import PluginConfigManager
    config_mgr = PluginConfigManager(...)
    config = config_mgr.load_config("my-skill")
    
    # Your logic here
    result = "Result: ..."
    
    if player:
        player.write_log("[MySkill] Action completed")
    
    return result
```

### Step 3: Test Locally

```bash
# Install from local directory
jarvis> skill_manager action=install source=/path/to/my-plugin

# Check it's loaded
jarvis> skill_manager action=list_installed

# View details
jarvis> skill_manager action=show_details plugin=my-skill

# Configure it
jarvis> skill_manager action=set_config plugin=my-skill key=setting1 value=myvalue

# Use it
jarvis> skill_manager action=list_actions
jarvis> (my_action will now be available)
```

## Permission Levels

Plugins declare the minimum permissions they need:

- **safe**: Read-only, no external calls or file access
- **network**: Can make external API calls (HTTP, etc.)
- **local_read**: Can read files on the local system
- **local_write**: Can write/modify files on the local system
- **local_exec**: Can execute local commands or scripts
- **sensitive**: Access to passwords, keychain, or private memory

Actions within a plugin can declare more specific permissions than the plugin overall.

## Marketplace

Plugins can be distributed via an online marketplace. The default marketplace URL is:
- `https://jarvis-marketplace.local/plugins/index.json` (local/self-hosted example)

To publish a plugin to a marketplace, contact the marketplace maintainer. Marketplace entries must include:

```json
{
  "name": "my-skill",
  "title": "My Skill",
  "version": "1.0.0",
  "description": "...",
  "download_url": "https://example.com/plugins/my-skill-1.0.0.zip",
  "homepage": "...",
  "tags": ["category1", "category2"]
}
```

## API Reference

### core.plugin_manifest

- `PluginManifest`: Dataclass representing plugin metadata
- `ActionSchema`: Dataclass for action definitions
- `discover_manifest(path)`: Find and parse manifest.json
- `validate_manifest(manifest)`: Validate a manifest against schema

### core.plugin_registry

- `PluginRegistry`: Load and manage plugins
- `registry.discover_all()`: Scan for all installed plugins
- `registry.get_plugin(name)`: Get a loaded plugin
- `registry.get_action(name)`: Call an action by name

### core.plugin_config

- `PluginConfigManager`: Load/save/validate plugin configuration
- `config_mgr.load_config(plugin_name)`: Load config.json
- `config_mgr.save_config(plugin_name, config)`: Save config
- `config_mgr.get_config_value(plugin_name, key)`: Get single value

### core.plugin_permissions

- `PluginPermissionGuard`: Enforce permission policies
- `guard.check_action(plugin, action, manifest)`: Decide if action is allowed
- `guard.set_plugin_permission(plugin, perm, allow)`: Override permission

### actions/skill_manager

User-facing skill management action with commands:
- `install`: Install from local path or marketplace
- `remove`: Uninstall a plugin
- `upgrade`: Upgrade to a newer version
- `enable` / `disable`: Toggle plugin state
- `list_installed`: List all installed plugins
- `list_marketplace`: Browse available plugins
- `show_details`: View plugin info
- `show_permissions`: See required permissions
- `set_config` / `get_config`: Manage configuration
- `list_actions`: See what actions are available

## Troubleshooting

**Plugin won't load?**
- Check manifest.json is valid JSON
- Ensure entry_point file exists and is readable
- Run `skill_manager action=show_details plugin=my-skill` to see errors

**Action not found?**
- Reload plugins: `skill_manager action=list_installed` (or restart JARVIS)
- Ensure the Python function is exported in __init__.py
- Check that manifest.json lists the action

**Permission denied?**
- View required permissions: `skill_manager action=show_permissions plugin=my-skill`
- QA mode blocks writes: set `JARVIS_QA_ALLOW_PLUGINS=1` in tests
- Sandbox mode blocks non-safe actions: disable sandbox or use a safe-only plugin

**Configuration issues?**
- Validate against schema: `skill_manager action=set_config ...` will reject invalid values
- Reset to defaults: `skill_manager action=reset_config plugin=my-skill`
- View current config: `skill_manager action=get_config plugin=my-skill`
