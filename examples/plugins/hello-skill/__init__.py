"""Hello Skill: A simple demonstration plugin."""

def greet(parameters=None, response=None, player=None, session_memory=None) -> str:
    """Greet the user."""
    params = parameters or {}
    name = str(params.get("name") or "there").strip()
    if player:
        player.write_log(f"[HelloSkill] Greeting {name}")
    return f"Hello, {name}! Welcome to JARVIS."


def farewell(parameters=None, response=None, player=None, session_memory=None) -> str:
    """Say goodbye."""
    if player:
        player.write_log("[HelloSkill] Farewell")
    return "Goodbye! Thank you for using JARVIS. Have a great day!"
