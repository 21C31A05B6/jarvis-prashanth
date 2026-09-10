
from __future__ import annotations

import asyncio
import concurrent.futures
import os
import platform
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional, Any

from playwright.async_api import (
    async_playwright,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeout,
)
from agent.tool_result import ToolResult, ErrorCategory, coerce_tool_result
from core.permission_manager import classify_error
_OS = platform.system()   # "Windows" | "Darwin" | "Linux"

def _normalize_url(url: str) -> str:
    """
    Bare words like "instagram" → "https://instagram.com"
    Domains like "instagram.com" → "https://instagram.com"
    Full URLs pass through unchanged.
    """
    url = url.strip()
    if not url:
        return "about:blank"
    if "://" in url:
        return url
    # No dot at all → assume .com  (e.g. "instagram" → "instagram.com")
    if "." not in url:
        url = url + ".com"
    return "https://" + url


def _user_agent() -> str:
    if _OS == "Windows":
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    if _OS == "Darwin":
        return (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    return (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )


def _real_profile_dir(browser: str) -> str:
    home  = Path.home()
    local = os.environ.get("LOCALAPPDATA", "")
    roam  = os.environ.get("APPDATA", "")

    candidates: list[Path] = []

    if _OS == "Windows":
        m = {
            "chrome":   [Path(local) / "Google"          / "Chrome"          / "User Data"],
            "edge":     [Path(local) / "Microsoft"        / "Edge"            / "User Data"],
            "brave":    [Path(local) / "BraveSoftware"    / "Brave-Browser"   / "User Data"],
            "vivaldi":  [Path(local) / "Vivaldi"          / "User Data"],
            "opera":    [Path(roam)  / "Opera Software"   / "Opera Stable",
                         Path(local) / "Opera Software"   / "Opera Stable"],
            "operagx":  [Path(roam)  / "Opera Software"   / "Opera GX Stable",
                         Path(local) / "Opera Software"   / "Opera GX Stable"],
        }
        candidates = m.get(browser, [])

    elif _OS == "Darwin":
        lib = home / "Library" / "Application Support"
        m = {
            "chrome":   [lib / "Google"             / "Chrome"],
            "edge":     [lib / "Microsoft Edge"],
            "brave":    [lib / "BraveSoftware"       / "Brave-Browser"],
            "vivaldi":  [lib / "Vivaldi"],
            "opera":    [lib / "com.operasoftware.Opera"],
            "operagx":  [lib / "com.operasoftware.OperaGX"],
        }
        candidates = m.get(browser, [])

    elif _OS == "Linux":
        cfg = home / ".config"
        m = {
            "chrome":   [cfg / "google-chrome", cfg / "chromium"],
            "edge":     [cfg / "microsoft-edge"],
            "brave":    [cfg / "BraveSoftware" / "Brave-Browser"],
            "vivaldi":  [cfg / "vivaldi"],
            "opera":    [cfg / "opera"],
            "operagx":  [cfg / "opera-gx"],
        }
        candidates = m.get(browser, [])

    for p in candidates:
        if p.exists():
            print(f"[Browser] ✅ Real profile found for {browser}: {p}")
            return str(p)

    fallback = home / ".jarvis_profiles" / browser
    fallback.mkdir(parents=True, exist_ok=True)
    print(f"[Browser] ⚠️  Real profile not found for {browser}, using: {fallback}")
    return str(fallback)

def _firefox_profile_dir() -> Optional[str]:
    home = Path.home()

    if _OS == "Windows":
        base = Path(os.environ.get("APPDATA", "")) / "Mozilla" / "Firefox"
    elif _OS == "Darwin":
        base = home / "Library" / "Application Support" / "Firefox"
    else:
        base = home / ".mozilla" / "firefox"

    ini = base / "profiles.ini"
    if not ini.exists():
        return None

    current: dict[str, str] = {}
    default_path: Optional[str] = None

    for line in ini.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("["):
            p = current.get("Path", "")
            if p and current.get("Default") == "1":
                is_rel = current.get("IsRelative", "1") == "1"
                default_path = str(base / p) if is_rel else p
            current = {}
        elif "=" in line:
            k, _, v = line.partition("=")
            current[k.strip()] = v.strip()

    p = current.get("Path", "")
    if p and current.get("Default") == "1":
        is_rel = current.get("IsRelative", "1") == "1"
        default_path = str(base / p) if is_rel else p

    if default_path and Path(default_path).exists():
        print(f"[Browser] Firefox real profile: {default_path}")
        return default_path
    return None

def _find_opera_windows() -> Optional[str]:
    local  = os.environ.get("LOCALAPPDATA", "")
    prog   = os.environ.get("PROGRAMFILES", "")
    prog86 = os.environ.get("PROGRAMFILES(X86)", "")

    candidates = [
        Path(local)  / "Programs" / "Opera"    / "opera.exe",
        Path(local)  / "Programs" / "Opera GX" / "opera.exe",
        Path(prog)   / "Opera"    / "opera.exe",
        Path(prog86) / "Opera"    / "opera.exe",
    ]
    for p in candidates:
        if p.exists():
            print(f"[Browser] Opera found at: {p}")
            return str(p)

    try:
        import winreg
        keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\opera.exe",
            r"SOFTWARE\Clients\StartMenuInternet\OperaStable\shell\open\command",
            r"SOFTWARE\Clients\StartMenuInternet\OperaGXStable\shell\open\command",
            r"SOFTWARE\Clients\StartMenuInternet\opera\shell\open\command",
        ]
        for key_path in keys:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    k   = winreg.OpenKey(hive, key_path)
                    val = winreg.QueryValue(k, None)
                    winreg.CloseKey(k)
                    exe = val.strip().strip('"').split('"')[0].split(" --")[0].strip()
                    if exe and Path(exe).exists():
                        print(f"[Browser] Opera found via registry: {exe}")
                        return exe
                except Exception:
                    continue
    except Exception:
        pass

    return shutil.which("opera") or None

def _find_exe_windows(prog_name: str) -> Optional[str]:
    try:
        import winreg
        paths_to_try = [
            rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{prog_name}.exe",
            rf"SOFTWARE\Clients\StartMenuInternet\{prog_name}\shell\open\command",
        ]
        for key_path in paths_to_try:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    k   = winreg.OpenKey(hive, key_path)
                    val = winreg.QueryValue(k, None)
                    winreg.CloseKey(k)
                    exe = val.strip().strip('"').split('"')[0].split(" --")[0].strip()
                    if exe and Path(exe).exists():
                        return exe
                except Exception:
                    continue
    except Exception:
        pass
    return None

_BROWSER_SPECS: dict[str, dict] = {
    "Windows": {
        "chrome":   {"engine": "chromium", "channel": "chrome",  "bins": []},
        "edge":     {"engine": "chromium", "channel": "msedge",  "bins": []},
        "firefox":  {"engine": "firefox",  "channel": None,      "bins": ["firefox.exe"]},
        "opera":    {"engine": "chromium", "channel": None,      "bins": ["opera.exe"],  "special": "opera_windows"},
        "operagx":  {"engine": "chromium", "channel": None,      "bins": [],             "special": "opera_windows"},
        "brave":    {"engine": "chromium", "channel": None,      "bins": ["brave.exe"]},
        "vivaldi":  {"engine": "chromium", "channel": None,      "bins": ["vivaldi.exe"]},
        "safari":   None,
    },
    "Darwin": {
        "chrome":   {"engine": "chromium", "channel": "chrome",  "bins": []},
        "edge":     {"engine": "chromium", "channel": "msedge",  "bins": ["microsoft-edge"]},
        "firefox":  {"engine": "firefox",  "channel": None,      "bins": ["firefox"]},
        "opera":    {"engine": "chromium", "channel": None,      "bins": ["opera"]},
        "operagx":  {"engine": "chromium", "channel": None,      "bins": ["opera"]},
        "brave":    {"engine": "chromium", "channel": None,      "bins": ["brave browser", "brave"]},
        "vivaldi":  {"engine": "chromium", "channel": None,      "bins": ["vivaldi"]},
        "safari":   {"engine": "webkit",   "channel": None,      "bins": []},
    },
    "Linux": {
        "chrome":   {"engine": "chromium", "channel": None,
                     "bins": ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"]},
        "edge":     {"engine": "chromium", "channel": None,
                     "bins": ["microsoft-edge", "microsoft-edge-stable"]},
        "firefox":  {"engine": "firefox",  "channel": None, "bins": ["firefox"]},
        "opera":    {"engine": "chromium", "channel": None, "bins": ["opera", "opera-stable"]},
        "operagx":  {"engine": "chromium", "channel": None, "bins": ["opera", "opera-stable"]},
        "brave":    {"engine": "chromium", "channel": None, "bins": ["brave-browser", "brave"]},
        "vivaldi":  {"engine": "chromium", "channel": None, "bins": ["vivaldi-stable", "vivaldi"]},
        "safari":   None,
    },
}

_ALIASES: dict[str, str] = {
    "google chrome":   "chrome",
    "google-chrome":   "chrome",
    "microsoft edge":  "edge",
    "ms edge":         "edge",
    "msedge":          "edge",
    "mozilla firefox": "firefox",
    "opera gx":        "operagx",
    "opera_gx":        "operagx",
}


def _resolve_browser(name: str) -> dict | None:
    name   = _ALIASES.get(name.lower().strip(), name.lower().strip())
    os_map = _BROWSER_SPECS.get(_OS, {})
    spec   = os_map.get(name)
    if spec is None:
        return None

    engine  = spec["engine"]
    channel = spec.get("channel")
    bins    = spec.get("bins", [])
    exe     = None

    if spec.get("special") == "opera_windows":
        exe = _find_opera_windows()
        if not exe:
            print(f"[Browser] ⚠️  Opera executable not found on Windows.")
        return {"engine": engine, "exe": exe, "channel": channel}

    for b in bins:
        found = shutil.which(b)
        if found:
            exe = found
            break

    if not exe and _OS == "Darwin":
        app_names = {
            "chrome":  ["Google Chrome.app"],
            "edge":    ["Microsoft Edge.app"],
            "firefox": ["Firefox.app"],
            "opera":   ["Opera.app", "Opera GX.app"],
            "brave":   ["Brave Browser.app"],
            "vivaldi": ["Vivaldi.app"],
        }
        for app in app_names.get(name, []):
            app_dir = Path("/Applications") / app / "Contents" / "MacOS"
            if app_dir.exists():
                found_bins = list(app_dir.iterdir())
                if found_bins:
                    exe = str(found_bins[0])
                    break

    if not exe and _OS == "Windows" and not channel:
        exe = _find_exe_windows(name)

    return {"engine": engine, "exe": exe, "channel": channel}


def _detect_default_browser() -> str:
    try:
        if _OS == "Windows":
            import winreg
            k = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations"
                r"\UrlAssociations\http\UserChoice",
            )
            prog_id = winreg.QueryValueEx(k, "ProgId")[0].lower()
            winreg.CloseKey(k)
            for kw in ("edge", "firefox", "opera", "brave", "vivaldi", "chrome"):
                if kw in prog_id:
                    return kw
        elif _OS == "Darwin":
            out = subprocess.run(
                ["defaults", "read",
                 "com.apple.LaunchServices/com.apple.launchservices.secure",
                 "LSHandlers"],
                capture_output=True, text=True, timeout=5,
            ).stdout.lower()
            for kw in ("firefox", "opera", "brave", "vivaldi", "safari", "chrome", "edge"):
                if kw in out:
                    return kw
        elif _OS == "Linux":
            out = subprocess.run(
                ["xdg-settings", "get", "default-web-browser"],
                capture_output=True, text=True, timeout=5,
            ).stdout.lower()
            for kw in ("firefox", "opera", "brave", "vivaldi", "chrome", "edge"):
                if kw in out:
                    return kw
    except Exception:
        pass
    return "chrome"


class _BrowserSession:
    """
    Bir tarayıcı örneği için tam oturum.
    Tüm tarayıcılar launch_persistent_context ile gerçek profil üzerinde açılır.
    """

    def __init__(self, browser_name: str):
        self.browser_name = browser_name
        self._spec        = _resolve_browser(browser_name)

        self._loop:    asyncio.AbstractEventLoop | None = None
        self._thread:  threading.Thread | None          = None
        self._ready    = threading.Event()

        self._pw:      Playwright     | None = None
        self._context: BrowserContext | None = None
        self._page:    Page           | None = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name=f"BrowserThread-{self.browser_name}",
        )
        self._thread.start()
        self._ready.wait(timeout=20)

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._async_init())
        self._ready.set()
        self._loop.run_forever()

    async def _async_init(self):
        self._pw = await async_playwright().start()

    def run(self, coro, timeout: int = 60) -> Any:
        if not self._loop:
            raise RuntimeError(f"Session for '{self.browser_name}' not started.")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def close(self):
        if self._loop:
            try:
                asyncio.run_coroutine_threadsafe(self._async_close(), self._loop).result(10)
            except Exception:
                pass

    async def _async_close(self):
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self._context = self._page = None

    async def _launch(self):
        """
        Tarayıcıyı gerçek kullanıcı profiliyle başlatır.
        Context zaten açıksa hiçbir şey yapmaz.
        """
        if self._context is not None:
            return

        if self._spec is None:
            raise RuntimeError(
                f"'{self.browser_name}' bu platformda ({_OS}) desteklenmiyor."
            )

        engine_name = self._spec["engine"]
        exe         = self._spec["exe"]
        channel     = self._spec["channel"]
        engine_obj  = getattr(self._pw, engine_name)

        if engine_name == "firefox":
            profile = _firefox_profile_dir() or str(
                Path.home() / ".jarvis_profiles" / "firefox"
            )
            kwargs: dict = {
                "headless":    False,
                "slow_mo":     0,
                "viewport":    None,
                "no_viewport": True,
            }
            if exe:
                kwargs["executable_path"] = exe
            try:
                self._context = await engine_obj.launch_persistent_context(profile, **kwargs)
            except Exception as e:
                print(f"[Browser] Firefox real profile failed ({e}), using JARVIS profile")
                jarvis = str(Path.home() / ".jarvis_profiles" / "firefox_jarvis")
                Path(jarvis).mkdir(parents=True, exist_ok=True)
                self._context = await engine_obj.launch_persistent_context(jarvis, **kwargs)

            await asyncio.sleep(0.3)
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
            print(f"[Browser] ✅ Firefox launched")
            return

        if engine_name == "webkit":
            safari_profile = str(Path.home() / ".jarvis_profiles" / "safari")
            Path(safari_profile).mkdir(parents=True, exist_ok=True)
            kwargs = {
                "headless":    False,
                "slow_mo":     0,
                "viewport":    None,
                "no_viewport": True,
            }
            self._context = await engine_obj.launch_persistent_context(safari_profile, **kwargs)
            await asyncio.sleep(0.3)
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
            print(f"[Browser] ✅ Safari launched")
            return

        profile = _real_profile_dir(self.browser_name)

        kwargs = {
            "headless":    False,
            "slow_mo":     0,
            "viewport":    None,
            "no_viewport": True,
            "args": [
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--disable-default-apps",
                "--no-default-browser-check",
            ],
        }

        if exe:
            kwargs["executable_path"] = exe
        elif channel:
            kwargs["channel"] = channel

        label = (
            f"{self.browser_name}"
            + (f"/{channel}" if channel else "")
            + (f" @ {exe}" if exe else "")
        )

        try:
            self._context = await engine_obj.launch_persistent_context(profile, **kwargs)
            await asyncio.sleep(0.3)
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
            print(f"[Browser] ✅ Launched [{label}] profile={profile}")
            return
        except Exception as e:
            print(f"[Browser] ⚠️  Real profile failed for {label}: {e}")

        jarvis_profile = str(Path.home() / ".jarvis_profiles" / self.browser_name)
        Path(jarvis_profile).mkdir(parents=True, exist_ok=True)
        print(f"[Browser] Retrying with JARVIS profile: {jarvis_profile}")

        try:
            self._context = await engine_obj.launch_persistent_context(jarvis_profile, **kwargs)
            await asyncio.sleep(0.3)
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
            print(f"[Browser] ✅ Launched [{label}] with JARVIS profile")
        except Exception as e2:
            raise RuntimeError(f"Could not launch {self.browser_name}: {e2}") from e2

    async def _get_page(self) -> Page:
        await self._launch()
        if self._page is None or self._page.is_closed():
            pages = self._context.pages if self._context else []
            self._page = pages[0] if pages and not pages[0].is_closed() else await self._context.new_page()
            await asyncio.sleep(0.2)
        return self._page

    async def go_to(self, url: str) -> ToolResult:
        url      = _normalize_url(url)
        page     = await self._get_page()
        prev_url = page.url

        async def _do_goto(p: Page) -> str:
            """Attempt navigation and return the resulting URL (may still be blank)."""
            try:
                await p.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await asyncio.sleep(0.3)
            except PlaywrightTimeout:
                pass
            except Exception as e:
                print(f"[Browser] goto exception (non-fatal): {e}")
            return p.url

        result_url = await _do_goto(page)

        if result_url in ("about:blank", "", None, prev_url) and prev_url in ("about:blank", "", None):
            print(f"[Browser] Still blank after goto — retrying on new tab: {url}")
            try:
                new_page   = await self._context.new_page()
                self._page = new_page
                result_url = await _do_goto(new_page)
            except Exception as e:
                print(f"[Browser] New-tab retry failed: {e}")

        if result_url and result_url not in ("about:blank", "", None):
            title = ""
            try:
                title = await self._page.title()
            except Exception:
                pass
            return ToolResult.ok(
                f"Opened: {result_url}" + (f" ({title})" if title else ""),
                data={"url": result_url, "title": title},
                verification={"url": result_url, "title": title, "verified": True},
            )
        return ToolResult.fail(f"Could not open: {url}", ErrorCategory.TOOL_EXECUTION_FAILED)

    async def search(self, query: str, engine: str = "google") -> ToolResult:
        _engines = {
            "google":     "https://www.google.com/search?q=",
            "bing":       "https://www.bing.com/search?q=",
            "duckduckgo": "https://duckduckgo.com/?q=",
            "yandex":     "https://yandex.com/search/?text=",
        }
        base = _engines.get(engine.lower(), _engines["google"])
        target = base + query.replace(" ", "+")
        res = await self.go_to(target)
        if res.success:
            res.result = f"Searched {engine} for '{query}': {res.data.get('url', target) if res.data else target}"
        return res

    async def click(self, selector: str = None, text: str = None) -> ToolResult:
        page = await self._get_page()
        try:
            if text:
                await page.get_by_text(text, exact=False).first.click(timeout=8_000)
                return ToolResult.ok(f"Clicked text: '{text}'", data={"text": text}, verification={"clicked": True})
            if selector:
                await page.click(selector, timeout=8_000)
                return ToolResult.ok(f"Clicked selector: {selector}", data={"selector": selector}, verification={"clicked": True})
            return ToolResult.fail("No selector or text provided.", ErrorCategory.TOOL_EXECUTION_FAILED)
        except PlaywrightTimeout:
            return ToolResult.fail(f"Element not found (timeout): '{selector or text}'", ErrorCategory.TOOL_EXECUTION_FAILED)
        except Exception as e:
            return ToolResult.fail(f"Click error: {e}", ErrorCategory.TOOL_EXECUTION_FAILED)

    async def smart_click(self, description: str) -> ToolResult:
        page = await self._get_page()
        for role in ("button", "link", "searchbox", "textbox", "menuitem", "tab"):
            try:
                loc = page.get_by_role(role, name=description)
                if await loc.count() > 0:
                    await loc.first.click(timeout=5_000)
                    return ToolResult.ok(f"Clicked ({role}): '{description}'", data={"role": role, "target": description}, verification={"clicked": True})
            except Exception:
                pass
        for attempt in (
            lambda: page.get_by_text(description, exact=False).first.click(timeout=5_000),
            lambda: page.get_by_placeholder(description, exact=False).first.click(timeout=5_000),
            lambda: page.locator(
                f'[alt*="{description}" i],[title*="{description}" i],'
                f'[aria-label*="{description}" i]'
            ).first.click(timeout=5_000),
        ):
            try:
                await attempt()
                return ToolResult.ok(f"Clicked: '{description}'", data={"target": description}, verification={"clicked": True})
            except Exception:
                pass
        return ToolResult.fail(f"Could not find element to click: '{description}'", ErrorCategory.TOOL_EXECUTION_FAILED)

    async def download(
        self,
        url: str = None,
        selector: str = None,
        text: str = None,
        destination: str = None,
    ) -> ToolResult:
        """Download file and verify it exists on disk with non-zero size."""
        page = await self._get_page()
        dl_dir = Path(destination) if destination else (Path.home() / "Downloads")
        dl_dir.mkdir(parents=True, exist_ok=True)

        try:
            async with page.expect_download(timeout=30_000) as download_info:
                if selector:
                    await page.locator(selector).first.click()
                elif text:
                    await page.get_by_text(text, exact=False).first.click()
                elif url:
                    await page.goto(url)
                else:
                    return ToolResult.fail("No download target or URL specified.", ErrorCategory.TOOL_EXECUTION_FAILED)

            download = await download_info.value
            suggested_name = download.suggested_filename
            target_path = dl_dir / suggested_name
            await download.save_as(str(target_path))

            if target_path.exists() and target_path.stat().st_size > 0:
                size = target_path.stat().st_size
                return ToolResult.ok(
                    f"Successfully downloaded {suggested_name} ({size} bytes) to {target_path}",
                    data={"path": str(target_path), "size": size, "filename": suggested_name},
                    artifacts=[str(target_path)],
                    verification={"exists": True, "size": size, "path": str(target_path)},
                )
            return ToolResult.fail(f"Download finished but file missing or empty: {target_path}", ErrorCategory.TOOL_EXECUTION_FAILED)

        except PlaywrightTimeout:
            if url:
                try:
                    import urllib.request
                    filename = url.rstrip("/").split("/")[-1].split("?")[0] or "downloaded_file"
                    target_path = dl_dir / filename
                    urllib.request.urlretrieve(url, str(target_path))
                    if target_path.exists() and target_path.stat().st_size > 0:
                        size = target_path.stat().st_size
                        return ToolResult.ok(
                            f"Downloaded {filename} ({size} bytes) to {target_path}",
                            data={"path": str(target_path), "size": size, "filename": filename},
                            artifacts=[str(target_path)],
                            verification={"exists": True, "size": size, "path": str(target_path)},
                        )
                except Exception as ex:
                    return ToolResult.fail(f"Download failed: {ex}", ErrorCategory.NETWORK_FAILURE)
            return ToolResult.fail("Download timed out or no download event captured.", ErrorCategory.TOOL_TIMEOUT)
        except Exception as e:
            return ToolResult.fail(f"Download error: {e}", ErrorCategory.TOOL_EXECUTION_FAILED)

    async def type_text(self, selector: str = None, text: str = "",
                        clear_first: bool = True) -> ToolResult:
        page = await self._get_page()
        try:
            el = page.locator(selector).first if selector else page.locator(":focus")
            if clear_first:
                await el.clear()
            await el.type(text, delay=50)
            return ToolResult.ok("Text typed.", data={"selector": selector, "text": text}, verification={"typed": True})
        except Exception as e:
            return ToolResult.fail(f"Type error: {e}", ErrorCategory.TOOL_EXECUTION_FAILED)

    async def smart_type(self, description: str, text: str) -> ToolResult:
        page = await self._get_page()
        candidates = [
            ("placeholder", page.get_by_placeholder(description, exact=False)),
            ("label",       page.get_by_label(description, exact=False)),
            ("role",        page.get_by_role("textbox", name=description)),
            ("searchbox",   page.get_by_role("searchbox")),
            ("combobox",    page.get_by_role("combobox", name=description)),
        ]
        for method, loc in candidates:
            try:
                el = loc.first
                if await el.count() == 0:
                    continue
                await el.clear()
                await el.type(text, delay=50)
                return ToolResult.ok(f"Typed into ({method}): '{description}'", data={"target": description, "method": method}, verification={"typed": True})
            except Exception:
                continue
        return ToolResult.fail(f"Could not find input: '{description}'", ErrorCategory.TOOL_EXECUTION_FAILED)

    async def scroll(self, direction: str = "down", amount: int = 500) -> ToolResult:
        page = await self._get_page()
        try:
            y = amount if direction == "down" else -amount
            await page.mouse.wheel(0, y)
            return ToolResult.ok(f"Scrolled {direction}.", data={"direction": direction, "amount": amount})
        except Exception as e:
            return ToolResult.fail(f"Scroll error: {e}", ErrorCategory.TOOL_EXECUTION_FAILED)

    async def press(self, key: str) -> ToolResult:
        page = await self._get_page()
        try:
            await page.keyboard.press(key)
            return ToolResult.ok(f"Pressed: {key}", data={"key": key})
        except Exception as e:
            return ToolResult.fail(f"Key error: {e}", ErrorCategory.TOOL_EXECUTION_FAILED)

    async def get_text(self) -> ToolResult:
        page = await self._get_page()
        try:
            text = await page.inner_text("body")
            return ToolResult.ok(text[:4_000], data={"text": text})
        except Exception as e:
            return ToolResult.fail(f"Could not get page text: {e}", ErrorCategory.TOOL_EXECUTION_FAILED)

    async def get_url(self) -> ToolResult:
        page = await self._get_page()
        return ToolResult.ok(page.url, data={"url": page.url})

    async def fill_form(self, fields: dict) -> ToolResult:
        page    = await self._get_page()
        results = []
        errors  = []
        for selector, value in fields.items():
            try:
                el = page.locator(selector).first
                await el.clear()
                await el.type(str(value), delay=40)
                results.append(f"✓ {selector}")
            except Exception as e:
                errors.append(f"✗ {selector}: {e}")
        if errors and not results:
            return ToolResult.fail("Form fill failed: " + ", ".join(errors), ErrorCategory.TOOL_EXECUTION_FAILED)
        msg = "Form filled: " + ", ".join(results)
        if errors:
            msg += f" (Errors: {', '.join(errors)})"
        return ToolResult.ok(msg, data={"results": results, "errors": errors})

    async def new_tab(self, url: str = "") -> ToolResult:
        page = await self._get_page()
        ctx  = page.context
        new  = await ctx.new_page()
        self._page = new
        if url:
            return await self.go_to(url)
        return ToolResult.ok("New tab opened.")

    async def close_tab(self) -> ToolResult:
        page = self._page
        if page and not page.is_closed():
            ctx   = page.context
            await page.close()
            pages = ctx.pages
            self._page = pages[-1] if pages else None
            return ToolResult.ok("Tab closed.")
        return ToolResult.fail("No active tab to close.", ErrorCategory.TOOL_EXECUTION_FAILED)

    async def screenshot(self, path: str = None) -> ToolResult:
        page = await self._get_page()
        try:
            save_path = path or str(Path.home() / "Desktop" / "jarvis_screenshot.png")
            await page.screenshot(path=save_path, full_page=False)
            p = Path(save_path)
            if p.exists() and p.stat().st_size > 0:
                return ToolResult.ok(
                    f"Screenshot saved: {save_path}",
                    artifacts=[save_path],
                    verification={"exists": True, "size": p.stat().st_size},
                )
            return ToolResult.fail(f"Screenshot failed to write to {save_path}", ErrorCategory.TOOL_EXECUTION_FAILED)
        except Exception as e:
            return ToolResult.fail(f"Screenshot error: {e}", ErrorCategory.TOOL_EXECUTION_FAILED)

    async def back(self) -> ToolResult:
        page = await self._get_page()
        try:
            await page.go_back(timeout=10_000)
            return ToolResult.ok(f"Navigated back: {page.url}", data={"url": page.url})
        except Exception as e:
            return ToolResult.fail(f"Back error: {e}", ErrorCategory.TOOL_EXECUTION_FAILED)

    async def forward(self) -> ToolResult:
        page = await self._get_page()
        try:
            await page.go_forward(timeout=10_000)
            return ToolResult.ok(f"Navigated forward: {page.url}", data={"url": page.url})
        except Exception as e:
            return ToolResult.fail(f"Forward error: {e}", ErrorCategory.TOOL_EXECUTION_FAILED)

    async def reload(self) -> ToolResult:
        page = await self._get_page()
        try:
            await page.reload(timeout=15_000)
            return ToolResult.ok(f"Page reloaded: {page.url}", data={"url": page.url})
        except Exception as e:
            return ToolResult.fail(f"Reload error: {e}", ErrorCategory.TOOL_EXECUTION_FAILED)

    async def close_browser(self) -> ToolResult:
        await self._async_close()
        return ToolResult.ok(f"{self.browser_name} closed.")

class _SessionRegistry:
    """Tüm aktif tarayıcı oturumlarını yönetir."""

    def __init__(self):
        self._sessions:       dict[str, _BrowserSession] = {}
        self._active_browser: str                        = ""
        self._lock            = threading.Lock()

    def _get_or_create(self, browser_name: str) -> _BrowserSession:
        with self._lock:
            if browser_name not in self._sessions:
                sess = _BrowserSession(browser_name)
                sess.start()
                self._sessions[browser_name] = sess
                print(f"[Registry] New session: {browser_name}")
            return self._sessions[browser_name]

    def get(self, browser_name: str | None = None) -> _BrowserSession:
        if not browser_name:
            browser_name = self._active_browser or _detect_default_browser()
        browser_name = _ALIASES.get(browser_name.lower().strip(), browser_name.lower().strip())
        sess = self._get_or_create(browser_name)
        self._active_browser = browser_name
        return sess

    def switch(self, browser_name: str) -> str:
        browser_name = _ALIASES.get(browser_name.lower().strip(), browser_name.lower().strip())
        self._get_or_create(browser_name)
        self._active_browser = browser_name
        return f"Active browser → {browser_name}"

    def close_one(self, browser_name: str) -> str:
        with self._lock:
            sess = self._sessions.pop(browser_name, None)
        if sess:
            sess.close()
            if self._active_browser == browser_name:
                self._active_browser = ""
            return f"{browser_name} closed."
        return f"No active session for: {browser_name}"

    def close_all(self) -> str:
        with self._lock:
            names    = list(self._sessions.keys())
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._active_browser = ""
        for s in sessions:
            try:
                s.close()
            except Exception:
                pass
        return "All browsers closed: " + (", ".join(names) if names else "none")

    def list_sessions(self) -> str:
        with self._lock:
            if not self._sessions:
                return "No active browser sessions."
            lines = []
            for name in self._sessions:
                marker = " ◀ active" if name == self._active_browser else ""
                lines.append(f"  • {name}{marker}")
            return "Open browsers:\n" + "\n".join(lines)


_registry = _SessionRegistry()

def browser_control(
    parameters:    dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> ToolResult:
    params  = parameters or {}
    action  = params.get("action", "").lower().strip()
    browser = params.get("browser", "").lower().strip() or None
    result: ToolResult | str = "Unknown action."

    if action == "switch":
        target = browser or params.get("target", "").lower().strip()
        if target:
            msg = _registry.switch(target)
            res = ToolResult.ok(msg, data={"active_browser": target})
        else:
            res = ToolResult.fail("Please specify a browser to switch to.", ErrorCategory.TOOL_EXECUTION_FAILED)
        _log(player, str(res))
        return res

    if action == "list_browsers":
        msg = _registry.list_sessions()
        res = ToolResult.ok(msg, data={"sessions": list(_registry._sessions.keys())})
        _log(player, str(res))
        return res

    if action == "close_all":
        msg = _registry.close_all()
        res = ToolResult.ok(msg)
        _log(player, str(res))
        return res

    try:
        sess = _registry.get(browser)
    except Exception as e:
        cat = classify_error(e)
        res = ToolResult.fail(f"Could not start browser session: {e}", cat)
        _log(player, str(res))
        return res

    try:
        if action in ("open", "launch", "start"):
            url = params.get("url")
            if url:
                result = sess.run(sess.go_to(url))
            else:
                sess.run(sess._get_page())
                result = ToolResult.ok(
                    f"Browser {sess.browser_name} opened.",
                    data={"browser": sess.browser_name},
                    verification={"running": True},
                )
        elif action in ("go_to", "navigate"):
            result = sess.run(sess.go_to(params.get("url", "")))
        elif action == "search":
            result = sess.run(sess.search(params.get("query", ""), params.get("engine", "google")))
        elif action == "click":
            result = sess.run(sess.click(params.get("selector"), params.get("text")))
        elif action == "download":
            result = sess.run(sess.download(
                url=params.get("url"),
                selector=params.get("selector"),
                text=params.get("text"),
                destination=params.get("destination") or params.get("path"),
            ))
        elif action == "type":
            result = sess.run(sess.type_text(
                params.get("selector"), params.get("text", ""), params.get("clear_first", True)))
        elif action == "scroll":
            result = sess.run(sess.scroll(params.get("direction", "down"), int(params.get("amount", 500))))
        elif action == "fill_form":
            result = sess.run(sess.fill_form(params.get("fields", {})))
        elif action == "smart_click":
            result = sess.run(sess.smart_click(params.get("description", "")))
        elif action == "smart_type":
            result = sess.run(sess.smart_type(params.get("description", ""), params.get("text", "")))
        elif action == "get_text":
            result = sess.run(sess.get_text())
        elif action == "get_url":
            result = sess.run(sess.get_url())
        elif action == "press":
            result = sess.run(sess.press(params.get("key", "Enter")))
        elif action == "new_tab":
            result = sess.run(sess.new_tab(params.get("url", "")))
        elif action == "close_tab":
            result = sess.run(sess.close_tab())
        elif action == "screenshot":
            result = sess.run(sess.screenshot(params.get("path")))
        elif action == "back":
            result = sess.run(sess.back())
        elif action == "forward":
            result = sess.run(sess.forward())
        elif action == "reload":
            result = sess.run(sess.reload())
        elif action == "close":
            target = browser or _registry._active_browser
            if target:
                msg = _registry.close_one(target)
                result = ToolResult.ok(msg)
            else:
                result = ToolResult.fail("No browser specified to close.", ErrorCategory.TOOL_EXECUTION_FAILED)
        else:
            result = ToolResult.fail(f"Unknown browser action: '{action}'", ErrorCategory.COMMAND_UNDERSTOOD_TOOL_UNAVAILABLE)

    except concurrent.futures.TimeoutError:
        result = ToolResult.fail(f"Browser action '{action}' timed out (60s).", ErrorCategory.TOOL_TIMEOUT)
    except Exception as e:
        cat = classify_error(e)
        result = ToolResult.fail(f"Browser error ({action}): {e}", cat)

    final_res = coerce_tool_result(result)
    _log(player, str(final_res))
    return final_res


def _log(player, text: str):
    short = str(text)[:80]
    print(f"[Browser] {short}")
    if player:
        player.write_log(f"[browser] {short[:60]}")