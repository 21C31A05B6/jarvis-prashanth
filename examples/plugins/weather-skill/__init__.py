"""Weather Skill: Fetch weather using a configured API key."""


def get_weather(parameters=None, response=None, player=None, session_memory=None) -> str:
    """Fetch current weather for a location.
    
    Note: This is a stub implementation. In production, you'd:
    1. Load the API key from config via core.plugin_config.PluginConfigManager
    2. Make an actual HTTP request to OpenWeatherMap or similar
    3. Parse and format the response
    """
    params = parameters or {}
    location = str(params.get("location") or "").strip()
    if not location:
        return "A location is required."
    units = str(params.get("units") or "metric").strip()
    if player:
        player.write_log(f"[WeatherSkill] Fetching weather for {location}")
    # In a real plugin, this would call the weather API
    return f"Weather for {location} (units: {units}): Sunny, 22°C. [DEMO - Configure with real API key]"


def set_default_location(parameters=None, response=None, player=None, session_memory=None) -> str:
    """Set the default location for weather queries.
    
    Note: This is a stub. In production:
    1. Load current config via PluginConfigManager
    2. Update the 'default_location' key
    3. Save the config back
    """
    params = parameters or {}
    location = str(params.get("location") or "").strip()
    if not location:
        return "A location is required."
    if player:
        player.write_log(f"[WeatherSkill] Setting default location to {location}")
    return f"Default weather location set to {location}. [DEMO]"
