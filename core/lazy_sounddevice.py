"""A drop-in stand-in for the `sounddevice` module that defers the real
import (and its native PortAudio binding) until something actually touches
an attribute on it.

Several modules (`main.py`, `actions/tts_engine.py`,
`actions/screen_processor.py`) reference `sounddevice` for desktop
microphone/speaker access, but are also imported by the headless hosted API
and by tests that never touch audio. Importing the real `sounddevice`
eagerly meant those code paths failed wherever PortAudio isn't installed
(minimal containers, CI), even when audio was never used
(`external_audio=True` in hosted mode). Use `sd = get_lazy_sounddevice()`
in place of `import sounddevice as sd`.
"""

from __future__ import annotations


class _LazySoundDevice:
    def __getattr__(self, name):
        import sounddevice as _sd

        return getattr(_sd, name)


def get_lazy_sounddevice() -> _LazySoundDevice:
    return _LazySoundDevice()
