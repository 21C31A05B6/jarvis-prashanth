"""Qt6 DLL initialization helper for Windows environments."""
import os
import sys


def init_qt() -> None:
    """Ensure PyQt6 Qt6 DLLs are properly found and loaded on Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        import importlib.util

        spec = importlib.util.find_spec("PyQt6")
        if not spec or not spec.origin:
            return

        pyqt_dir = os.path.dirname(spec.origin)
        qt_bin = os.path.join(pyqt_dir, "Qt6", "bin")
        if not os.path.exists(qt_bin):
            return

        try:
            os.add_dll_directory(qt_bin)
        except (AttributeError, OSError):
            pass

        path_env = os.environ.get("PATH", "")
        if qt_bin not in path_env:
            os.environ["PATH"] = qt_bin + os.pathsep + path_env

        k32 = ctypes.windll.kernel32
        LOAD_WITH_ALTERED_SEARCH_PATH = 0x00000008
        qt_dlls = [
            "Qt6Core.dll",
            "Qt6Gui.dll",
            "Qt6Widgets.dll",
            "Qt6Network.dll",
            "Qt6Svg.dll",
            "Qt6OpenGL.dll",
            "Qt6OpenGLWidgets.dll",
        ]
        for dll in qt_dlls:
            dll_path = os.path.join(qt_bin, dll)
            if os.path.exists(dll_path):
                try:
                    k32.LoadLibraryExW(dll_path, None, LOAD_WITH_ALTERED_SEARCH_PATH)
                except Exception:
                    pass
    except Exception:
        pass


init_qt()
