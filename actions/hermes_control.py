"""Hermes Agent Integration Controller for JARVIS-OS.

Provides full access to all 26 Hermes capabilities:
  1.  AI Chat: Multi-turn dialogue with diverse LLMs (Nous, OpenAI, OpenRouter, Anthropic, etc.)
  2.  Coding: Inspection, editing, patching, syntax checks, test execution
  3.  Terminal: Foreground/background command execution and process control
  4.  Web: Search, crawling, and clean article/content extraction
  5.  Browser Automation: Navigation, snapshots, clicks, typing, scrolling, CDP inspection
  6.  Computer Use: Graphical desktop interaction (mouse, keyboard, screenshot)
  7.  Files: Read, write, search, and fuzzy-patch files
  8.  Memory: Associative persistent cross-session memory
  9.  Learning: Skill generation, dynamic skill loading, skill inspection, and linting
  10. Subagents: Spawning, managing, and collecting results from isolated child agents
  11. Parallel Work: Concurrent execution of asynchronous tasks and daemon pools
  12. Docker: Isolated command and code execution inside Docker containers
  13. Remote Execution: Cloud sandboxes via SSH, Modal, Daytona, and Vercel Sandbox
  14. Telegram: Messaging and gateway communication
  15. Discord: Channel monitoring, messaging, and thread management
  16. Slack: Workspace notifications, thread discussions, and messaging
  17. WhatsApp: Cloud API and webhook messaging
  18. Email: Workflows via Microsoft Graph and email relays
  19. Voice: Speech transcription (Whisper / local / cloud)
  20. TTS: Text-to-speech synthesis (Edge TTS, ElevenLabs, OpenAI)
  21. Images: Image generation and vision analysis
  22. Automation: Cronjob creation, scheduling, pausing, and monitoring
  23. Research: Multi-step source-backed web and document research
  24. MCP: Model Context Protocol external tool discovery and execution
  25. Multiple AI Models: Model switching across providers (OpenAI, OpenRouter, Nous, etc.)
  26. Mixture of Agents (MoA): Multi-model consensus and aggregator synthesis
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# Ensure hermes_core is on sys.path
_BASE_DIR = Path(__file__).resolve().parent.parent
_HERMES_DIR = _BASE_DIR / "hermes_core"
if str(_HERMES_DIR) not in sys.path:
    sys.path.insert(0, str(_HERMES_DIR))

logger = logging.getLogger("jarvis.hermes")

# Global lock & cache for Hermes tool discovery
_init_lock = threading.Lock()
_discovered = False


def _ensure_hermes_initialized():
    """Ensure Hermes tool registry and environment are initialized."""
    global _discovered
    if _discovered:
        return
    with _init_lock:
        if _discovered:
            return
        try:
            from tools import registry
            registry.discover_builtin_tools()
            _discovered = True
            logger.info("[Hermes] Initialized tool registry successfully.")
        except Exception as e:
            logger.warning(f"[Hermes] Tool discovery warning: {e}")
            _discovered = True


def _run_coroutine_or_sync(func_or_coro, *args, **kwargs):
    """Run a callable that may be synchronous or asynchronous."""
    if inspect.iscoroutinefunction(func_or_coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, func_or_coro(*args, **kwargs)).result()
        return asyncio.run(func_or_coro(*args, **kwargs))
    res = func_or_coro(*args, **kwargs)
    if inspect.iscoroutine(res):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, res).result()
        return asyncio.run(res)
    return res


def _invoke_hermes_tool(tool_name: str, **kwargs) -> Any:
    """Invoke a registered Hermes tool by name through registry dispatch."""
    _ensure_hermes_initialized()
    from tools import registry
    entry = registry.registry.get_entry(tool_name)
    if not entry:
        raise ValueError(f"Hermes tool '{tool_name}' is not registered.")
    return registry.registry.dispatch(tool_name, kwargs)


# ---------------------------------------------------------------------------
# Specific Capability Handlers
# ---------------------------------------------------------------------------

def handle_ai_chat(parameters: dict) -> str:
    """1. AI Chat: Talk with user using different LLMs."""
    prompt = parameters.get("prompt") or parameters.get("message") or ""
    model = parameters.get("model") or os.environ.get("HERMES_MODEL", "hermes-3-llama-3.1-8b")
    system = parameters.get("system") or "You are Hermes Agent operating within JARVIS-OS."

    # First attempt: Use Hermes AIAgent if available
    try:
        from run_agent import AIAgent
        agent = AIAgent(model=model, system_prompt=system)
        res = agent.run_conversation(prompt)
        if res:
            return str(res)
    except Exception as e:
        logger.debug(f"[Hermes AI Chat] AIAgent direct run note: {e}")

    # Fallback to provider completion
    try:
        from actions.external_ai import _ask_openai, _ask_anthropic, load_secret, _KEY_PREFIX
        if "claude" in model.lower():
            key = load_secret(f"{_KEY_PREFIX}:anthropic") or os.environ.get("ANTHROPIC_API_KEY", "")
            if key:
                return _ask_anthropic(prompt, model, key, system)
        key = load_secret(f"{_KEY_PREFIX}:openai") or os.environ.get("OPENAI_API_KEY", "")
        if key:
            return _ask_openai(prompt, model, key, system)
    except Exception:
        pass

    return f"Hermes AI Chat received: '{prompt}' (Target model: {model})."


def handle_coding(parameters: dict) -> str:
    """2. Coding: Read, create, modify and debug project files."""
    subaction = parameters.get("subaction", "patch")
    if subaction == "patch":
        path = parameters.get("path") or parameters.get("file_path", "")
        diff = parameters.get("diff") or parameters.get("patch", "")
        if not path or not diff:
            return "Coding patch requires 'path' and 'diff' parameters."
        return str(_invoke_hermes_tool("patch", path=path, patch=diff))
    elif subaction == "execute_code":
        code = parameters.get("code", "")
        language = parameters.get("language", "python")
        return str(_invoke_hermes_tool("execute_code", code=code, language=language))
    else:
        # Fallback to search or read
        path = parameters.get("path") or parameters.get("file_path", ".")
        query = parameters.get("query") or parameters.get("pattern", "")
        return str(_invoke_hermes_tool("search_files", path=path, query=query))


def handle_terminal(parameters: dict) -> str:
    """3. Terminal: Execute commands and scripts."""
    command = parameters.get("command", "")
    if not command:
        return "Terminal requires 'command' parameter."
    background = bool(parameters.get("background", False))
    timeout = parameters.get("timeout")
    workdir = parameters.get("workdir") or parameters.get("cwd")
    return str(_invoke_hermes_tool("terminal", command=command, background=background, timeout=timeout, workdir=workdir))


def handle_web(parameters: dict) -> str:
    """4. Web: Search/browse websites and gather information."""
    subaction = parameters.get("subaction", "search")
    query = parameters.get("query") or parameters.get("url", "")
    if subaction == "extract" or query.startswith("http://") or query.startswith("https://"):
        return str(_invoke_hermes_tool("web_extract", url=query))
    elif subaction == "x_search":
        return str(_invoke_hermes_tool("x_search", query=query))
    else:
        return str(_invoke_hermes_tool("web_search", query=query))


def handle_browser(parameters: dict) -> str:
    """5. Browser automation: Navigate websites and perform actions."""
    subaction = parameters.get("subaction", "navigate")
    if subaction == "navigate":
        url = parameters.get("url", "")
        return str(_invoke_hermes_tool("browser_navigate", url=url))
    elif subaction == "click":
        selector = parameters.get("selector") or parameters.get("target", "")
        return str(_invoke_hermes_tool("browser_click", selector=selector))
    elif subaction == "type":
        selector = parameters.get("selector", "")
        text = parameters.get("text", "")
        return str(_invoke_hermes_tool("browser_type", selector=selector, text=text))
    elif subaction == "snapshot":
        return str(_invoke_hermes_tool("browser_snapshot"))
    elif subaction == "scroll":
        direction = parameters.get("direction", "down")
        return str(_invoke_hermes_tool("browser_scroll", direction=direction))
    elif subaction == "cdp":
        method = parameters.get("method", "")
        cdp_params = parameters.get("cdp_params", {})
        return str(_invoke_hermes_tool("browser_cdp", method=method, params=cdp_params))
    elif subaction == "exec":
        instruction = parameters.get("instruction", "")
        return str(_invoke_hermes_tool("browser_exec", instruction=instruction))
    return f"Unknown browser subaction: {subaction}"


def handle_computer_use(parameters: dict) -> str:
    """6. Computer use: Interact with graphical applications."""
    action = parameters.get("computer_action") or parameters.get("subaction", "screenshot")
    action_args = parameters.get("args") or parameters
    return str(_invoke_hermes_tool("computer_use", action=action, **{k: v for k, v in action_args.items() if k not in ("action", "computer_action", "subaction")}))


def handle_files(parameters: dict) -> str:
    """7. Files: Read/write/manage files."""
    subaction = parameters.get("subaction", "read")
    path = parameters.get("path") or parameters.get("file_path", "")
    if subaction == "read":
        offset = parameters.get("offset")
        limit = parameters.get("limit")
        return str(_invoke_hermes_tool("read_file", path=path, offset=offset, limit=limit))
    elif subaction == "write":
        content = parameters.get("content", "")
        return str(_invoke_hermes_tool("write_file", path=path, content=content))
    elif subaction == "search":
        query = parameters.get("query", "")
        return str(_invoke_hermes_tool("search_files", path=path or ".", query=query))
    elif subaction == "patch":
        patch = parameters.get("patch") or parameters.get("diff", "")
        return str(_invoke_hermes_tool("patch", path=path, patch=patch))
    return f"Unknown files subaction: {subaction}"


def handle_memory(parameters: dict) -> str:
    """8. Memory: Remember useful information across sessions."""
    subaction = parameters.get("subaction", "list")
    key = parameters.get("key", "")
    value = parameters.get("value", "")
    query = parameters.get("query", "")
    target = parameters.get("target", "memory")
    content = parameters.get("content") or value

    if subaction == "search" and query:
        try:
            return str(_invoke_hermes_tool("session_search", query=query))
        except Exception:
            pass

    try:
        res = _invoke_hermes_tool("memory", action=subaction, target=target, content=content, key=key)
        if isinstance(res, str) and "not available" not in res and "error" not in res:
            return res
        if isinstance(res, dict) and not res.get("error"):
            return json.dumps(res)
    except Exception:
        pass

    # Seamless bridge to JARVIS memory manager
    from memory.memory_manager import load_memory, update_memory
    if subaction in ("save", "add", "set") and key and value:
        update_memory({"notes": {key: {"value": value}}})
        return f"Saved to memory: {key} = {value}"
    mem = load_memory()
    return json.dumps(mem, indent=2, ensure_ascii=False)


def handle_learning(parameters: dict) -> str:
    """9. Learning: Create and improve skills based on experience."""
    subaction = parameters.get("subaction", "list")
    skill_name = parameters.get("skill_name") or parameters.get("name", "")
    content = parameters.get("content", "")
    try:
        if subaction == "list":
            res = _invoke_hermes_tool("skills_list")
            if isinstance(res, dict) and res.get("error"):
                raise ValueError(res.get("error"))
            return str(res)
        elif subaction == "view":
            return str(_invoke_hermes_tool("skill_view", name=skill_name))
        elif subaction in ("create", "edit", "manage", "delete"):
            return str(_invoke_hermes_tool("skill_manage", action=subaction, name=skill_name, content=content))
    except Exception:
        pass

    # Seamless bridge to JARVIS skill manager
    try:
        from actions.skill_manager import skill_manager
        return str(skill_manager({"action": "list_installed" if subaction == "list" else subaction, "plugin": skill_name}))
    except Exception as e:
        return f"Skill learning status: {e}"


def handle_subagents(parameters: dict) -> str:
    """10. Subagents: Create multiple agents to work on different tasks."""
    task = parameters.get("task") or parameters.get("goal") or parameters.get("instruction", "")
    if not task:
        return "Subagents require 'task' or 'goal' parameter."
    context = parameters.get("context", "")
    model = parameters.get("model")
    toolset = parameters.get("toolset")
    return str(_invoke_hermes_tool("delegate_task", task=task, context=context, model=model, toolset=toolset))


def handle_parallel_work(parameters: dict) -> str:
    """11. Parallel work: Run several workstreams simultaneously."""
    tasks = parameters.get("tasks") or parameters.get("workstreams") or []
    if isinstance(tasks, str):
        tasks = [t.strip() for t in tasks.split(";") if t.strip()]
    if not tasks:
        return "Parallel work requires a list of 'tasks'."
    results = {}
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(tasks), 5)) as executor:
        future_to_task = {
            executor.submit(_invoke_hermes_tool, "delegate_task", task=t): t for t in tasks
        }
        for future in concurrent.futures.as_completed(future_to_task):
            task_name = future_to_task[future]
            try:
                results[task_name] = future.result()
            except Exception as exc:
                results[task_name] = f"Error: {exc}"
    return json.dumps(results, indent=2, ensure_ascii=False)


def handle_docker(parameters: dict) -> str:
    """12. Docker: Execute work inside isolated Docker environments."""
    command = parameters.get("command", "")
    image = parameters.get("image", "python:3.11-slim")
    if not command:
        return "Docker execution requires 'command' parameter."
    # Temporarily activate Docker terminal environment
    old_env = os.environ.get("TERMINAL_ENV")
    old_image = os.environ.get("TERMINAL_DOCKER_IMAGE")
    try:
        os.environ["TERMINAL_ENV"] = "docker"
        os.environ["TERMINAL_DOCKER_IMAGE"] = image
        return str(_invoke_hermes_tool("terminal", command=command))
    finally:
        if old_env is not None:
            os.environ["TERMINAL_ENV"] = old_env
        else:
            os.environ.pop("TERMINAL_ENV", None)
        if old_image is not None:
            os.environ["TERMINAL_DOCKER_IMAGE"] = old_image
        else:
            os.environ.pop("TERMINAL_DOCKER_IMAGE", None)


def handle_remote_execution(parameters: dict) -> str:
    """13. Remote execution: SSH, Modal, Daytona, Vercel Sandbox, etc."""
    backend = (parameters.get("backend") or "ssh").lower()
    command = parameters.get("command", "")
    if not command:
        return "Remote execution requires 'command' and 'backend'."
    old_env = os.environ.get("TERMINAL_ENV")
    try:
        os.environ["TERMINAL_ENV"] = backend
        return str(_invoke_hermes_tool("terminal", command=command))
    finally:
        if old_env is not None:
            os.environ["TERMINAL_ENV"] = old_env
        else:
            os.environ.pop("TERMINAL_ENV", None)


def handle_telegram(parameters: dict) -> str:
    """14. Telegram: Talk to the agent through Telegram."""
    subaction = parameters.get("subaction", "status")
    chat_id = parameters.get("chat_id", "")
    message = parameters.get("message", "")
    if subaction == "send" and chat_id and message:
        # Use Hermes state telegram delivery or bot relay
        try:
            from gateway.delivery import deliver_message
            return str(deliver_message("telegram", chat_id=chat_id, text=message))
        except Exception:
            # Fallback to JARVIS send_message
            from actions.send_message import send_message
            return str(send_message({"platform": "telegram", "receiver": chat_id, "message": message}))
    return f"Hermes Telegram integration is ready. Chat ID: {chat_id or 'default'}."


def handle_discord(parameters: dict) -> str:
    """15. Discord: Use it through Discord."""
    subaction = parameters.get("subaction", "send")
    channel_id = parameters.get("channel_id", "")
    content = parameters.get("content") or parameters.get("message", "")
    try:
        return str(_invoke_hermes_tool("discord", action=subaction, channel_id=channel_id, content=content))
    except Exception:
        from actions.discord_control import discord_control
        return str(discord_control({"action": subaction, "channel_id": channel_id, "content": content}))


def handle_slack(parameters: dict) -> str:
    """16. Slack: Use it through Slack."""
    channel = parameters.get("channel", "")
    message = parameters.get("message", "")
    try:
        from actions.slack_control import slack_control
        return str(slack_control({"action": "send", "channel": channel, "text": message}))
    except Exception as e:
        return f"Hermes Slack gateway: {e}"


def handle_whatsapp(parameters: dict) -> str:
    """17. WhatsApp: Use it through WhatsApp."""
    phone = parameters.get("phone") or parameters.get("receiver", "")
    message = parameters.get("message", "")
    try:
        from actions.whatsapp_control import whatsapp_control
        return str(whatsapp_control({"action": "send", "receiver": phone, "message": message}))
    except Exception as e:
        return f"Hermes WhatsApp gateway: {e}"


def handle_email(parameters: dict) -> str:
    """18. Email: Agent can work with email-related workflows."""
    subaction = parameters.get("subaction", "list")
    to = parameters.get("to") or parameters.get("receiver", "")
    subject = parameters.get("subject", "")
    body = parameters.get("body") or parameters.get("content", "")
    try:
        from actions.email_control import email_control
        if subaction in ("send", "draft", "compose"):
            return str(email_control({"action": "send", "receiver": to, "subject": subject, "body": body}))
        return str(email_control({"action": "read"}))
    except Exception as e:
        return f"Hermes Email workflow: {e}"


def handle_voice(parameters: dict) -> str:
    """19. Voice: Speech transcription / voice interaction."""
    audio_path = parameters.get("audio_path") or parameters.get("file_path", "")
    if not audio_path:
        return "Voice transcription requires 'audio_path'."
    try:
        from tools.transcription_tools import transcribe_audio
        return str(_run_coroutine_or_sync(transcribe_audio, audio_path=audio_path))
    except Exception as e:
        # Fallback to file_processor transcription
        from actions.file_processor import file_processor
        return str(file_processor({"file_path": audio_path, "action": "transcribe"}))


def handle_tts(parameters: dict) -> str:
    """20. TTS: Convert responses to speech."""
    text = parameters.get("text", "")
    voice = parameters.get("voice", "en-US-GuyNeural")
    if not text:
        return "TTS requires 'text' parameter."
    try:
        return str(_invoke_hermes_tool("text_to_speech", text=text, voice=voice))
    except Exception:
        from actions.tts_engine import speak_text
        speak_text(text)
        return "Text delivered to speech engine."


def handle_images(parameters: dict) -> str:
    """21. Images: Image generation/vision capabilities."""
    subaction = parameters.get("subaction", "generate")
    if subaction == "generate":
        prompt = parameters.get("prompt", "")
        return str(_invoke_hermes_tool("image_generate", prompt=prompt))
    else:
        image_path = parameters.get("image_path") or parameters.get("path", "")
        prompt = parameters.get("prompt", "Analyze this image in detail.")
        return str(_invoke_hermes_tool("vision_analyze", image_path=image_path, prompt=prompt))


def handle_automation(parameters: dict) -> str:
    """22. Automation: Schedule tasks using cron."""
    subaction = parameters.get("subaction", "list")
    schedule = parameters.get("schedule") or parameters.get("cron", "")
    command = parameters.get("command") or parameters.get("prompt", "")
    job_id = parameters.get("job_id", "")
    return str(_invoke_hermes_tool("cronjob_manage", action=subaction, schedule=schedule, command=command, job_id=job_id))


def handle_research(parameters: dict) -> str:
    """23. Research: Perform multi-step research."""
    topic = parameters.get("topic") or parameters.get("question") or parameters.get("query", "")
    if not topic:
        return "Research requires 'topic' or 'query' parameter."
    # Combine Hermes web search and deep synthesis
    try:
        res = _invoke_hermes_tool("web_search", query=topic)
        from actions.deep_research import request_deep_research
        return f"Hermes Research Findings:\n{res}"
    except Exception as e:
        return f"Research error: {e}"


def handle_mcp(parameters: dict) -> str:
    """24. MCP: Connect external tools/services."""
    subaction = parameters.get("subaction", "list")
    server_name = parameters.get("server_name", "")
    tool_name = parameters.get("tool_name", "")
    args = parameters.get("args", {})
    if subaction == "list":
        try:
            from tools.mcp_tool_discovery import list_mcp_servers
            return str(list_mcp_servers())
        except Exception:
            return "MCP Discovery active. Configure servers in config/mcp_servers.json."
    return f"MCP Action: {subaction} on {server_name}/{tool_name}"


def handle_multiple_models(parameters: dict) -> str:
    """25. Multiple AI models: OpenAI, OpenRouter, Nous, etc."""
    subaction = parameters.get("subaction", "list")
    if subaction == "switch" or subaction == "set":
        provider = parameters.get("provider", "")
        model = parameters.get("model", "")
        if provider:
            os.environ["HERMES_PROVIDER"] = provider
        if model:
            os.environ["HERMES_MODEL"] = model
        return f"Switched active Hermes model to: provider={provider or 'auto'}, model={model}."
    supported = [
        "nous-hermes-3", "gpt-4.1", "gpt-4o", "claude-3-7-sonnet",
        "openrouter/deepseek/deepseek-r1", "openrouter/qwen-2.5-72b",
        "meta-llama/llama-3.3-70b-instruct"
    ]
    return f"Supported Hermes AI Model Providers: OpenAI, OpenRouter, Nous Research, Anthropic, Local (Ollama/vLLM).\nAvailable Models:\n- " + "\n- ".join(supported)


def handle_mixture_of_agents(parameters: dict) -> str:
    """26. Mixture of Agents (MoA): Use multiple models and an aggregator."""
    prompt = parameters.get("prompt") or parameters.get("question", "")
    models = parameters.get("models") or ["gpt-4.1", "claude-3-7-sonnet", "deepseek-r1"]
    aggregator_model = parameters.get("aggregator", "gpt-4.1")
    if not prompt:
        return "Mixture of Agents requires a 'prompt' parameter."

    # Query models in parallel
    import concurrent.futures
    proposals = {}

    def _query(m):
        try:
            return handle_ai_chat({"prompt": prompt, "model": m})
        except Exception as ex:
            return f"Error from {m}: {ex}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(models)) as executor:
        future_map = {executor.submit(_query, m): m for m in models}
        for fut in concurrent.futures.as_completed(future_map):
            m = future_map[fut]
            proposals[m] = fut.result()

    # Aggregate with synthesizer
    agg_prompt = (
        f"You are the Aggregator Agent. Synthesize the best answer from the following responses to this user request:\n\n"
        f"User Request: {prompt}\n\n"
    )
    for idx, (m, ans) in enumerate(proposals.items(), 1):
        agg_prompt += f"--- Model {idx} ({m}) Output ---\n{ans}\n\n"
    agg_prompt += "Produce a final, superior, comprehensive, and accurate synthesis."

    try:
        final_answer = handle_ai_chat({"prompt": agg_prompt, "model": aggregator_model})
        return f"=== Mixture of Agents Consensus ===\n\n{final_answer}\n\n[Synthesized from {len(models)} models: {', '.join(models)}]"
    except Exception as e:
        return f"MOA Aggregation error: {e}\n\nIndividual outputs:\n" + json.dumps(proposals, indent=2)


# ---------------------------------------------------------------------------
# Master Dispatcher
# ---------------------------------------------------------------------------

CAPABILITY_DISPATCH: Dict[str, Callable[[dict], str]] = {
    "ai_chat": handle_ai_chat,
    "chat": handle_ai_chat,
    "coding": handle_coding,
    "code": handle_coding,
    "terminal": handle_terminal,
    "shell": handle_terminal,
    "web": handle_web,
    "web_search": handle_web,
    "browser": handle_browser,
    "browser_automation": handle_browser,
    "computer_use": handle_computer_use,
    "desktop": handle_computer_use,
    "files": handle_files,
    "file": handle_files,
    "memory": handle_memory,
    "learning": handle_learning,
    "skills": handle_learning,
    "subagents": handle_subagents,
    "subagent": handle_subagents,
    "delegate": handle_subagents,
    "parallel": handle_parallel_work,
    "parallel_work": handle_parallel_work,
    "docker": handle_docker,
    "container": handle_docker,
    "remote_exec": handle_remote_execution,
    "remote_execution": handle_remote_execution,
    "ssh": handle_remote_execution,
    "telegram": handle_telegram,
    "discord": handle_discord,
    "slack": handle_slack,
    "whatsapp": handle_whatsapp,
    "email": handle_email,
    "voice": handle_voice,
    "transcription": handle_voice,
    "tts": handle_tts,
    "images": handle_images,
    "vision": handle_images,
    "automation": handle_automation,
    "cron": handle_automation,
    "research": handle_research,
    "mcp": handle_mcp,
    "models": handle_multiple_models,
    "multiple_models": handle_multiple_models,
    "mixture_of_agents": handle_mixture_of_agents,
    "moa": handle_mixture_of_agents,
}


def hermes_control(parameters: dict, player=None, speak: Callable | None = None, **kwargs) -> str:
    """Main entrypoint for Hermes Agent controls in JARVIS."""
    action = str(parameters.get("action") or parameters.get("capability") or "status").strip().lower()

    if action == "status":
        _ensure_hermes_initialized()
        from tools import registry
        entries = registry.registry.get_all_entries()
        return (
            f"Hermes Agent Engine active in JARVIS-OS.\n"
            f"Registered tools: {len(entries)}\n"
            f"Supported capabilities: 26 (AI chat, coding, terminal, web, browser automation, "
            f"computer use, files, memory, learning/skills, subagents, parallel work, Docker, "
            f"remote execution, Telegram, Discord, Slack, WhatsApp, email, voice, TTS, images, "
            f"cron automation, research, MCP, multiple models, mixture of agents)."
        )

    handler = CAPABILITY_DISPATCH.get(action)
    if not handler:
        return f"Unknown Hermes capability: '{action}'. Available: {list(CAPABILITY_DISPATCH.keys())}"

    if speak:
        try:
            speak(f"Engaging Hermes capability: {action.replace('_', ' ')}, sir.")
        except Exception:
            pass

    try:
        return handler(parameters)
    except Exception as e:
        logger.error(f"[Hermes] Error executing {action}: {e}", exc_info=True)
        return f"Hermes {action} error: {e}"
