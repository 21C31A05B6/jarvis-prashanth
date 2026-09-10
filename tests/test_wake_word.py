import os
import unittest
from unittest.mock import patch

import numpy as np

import main


class _WakeWordStream:
    """Simulates ~0.4s of speech-like energy followed by ~0.5s of silence,
    which is exactly what main.wait_for_wake_word needs to finalize one
    utterance and hand it to the (injected, network-free) transcriber."""

    def __init__(self, callback, speak=False, **_kwargs):
        self.callback = callback
        self.speak = speak

    def __enter__(self):
        if self.speak:
            speech = np.full((6400, 1), 0.15, dtype=np.float32)   # 0.4s @ 16kHz
            silence = np.zeros((8100, 1), dtype=np.float32)        # ~0.51s @ 16kHz
            self.callback(speech, len(speech), None, None)
            self.callback(silence, len(silence), None, None)
        return self

    def __exit__(self, *_args):
        return False


class WakeWordTests(unittest.TestCase):
    def test_hearing_the_wake_phrase_unlocks_startup(self):
        factory = lambda **kwargs: _WakeWordStream(speak=True, **kwargs)
        result = main.wait_for_wake_word(
            timeout=1, stream_factory=factory, transcribe_fn=lambda pcm, rate: "hey jarvis, are you there"
        )
        self.assertTrue(result)

    def test_unrelated_speech_does_not_unlock_startup(self):
        factory = lambda **kwargs: _WakeWordStream(speak=True, **kwargs)
        result = main.wait_for_wake_word(
            timeout=0.2, stream_factory=factory, transcribe_fn=lambda pcm, rate: "what's the weather today"
        )
        self.assertFalse(result)

    def test_gate_can_be_bypassed_for_missing_microphone_access(self):
        with patch.dict(os.environ, {"JARVIS_SKIP_WAKE_WORD": "1"}):
            self.assertTrue(main.wait_for_wake_word(stream_factory=lambda **_: self.fail("opened mic")))

    def test_gate_times_out_without_speech(self):
        factory = lambda **kwargs: _WakeWordStream(speak=False, **kwargs)
        result = main.wait_for_wake_word(timeout=0.15, stream_factory=factory, transcribe_fn=lambda pcm, rate: "")
        self.assertFalse(result)

    def test_transcription_failure_does_not_crash_and_keeps_waiting_then_times_out(self):
        factory = lambda **kwargs: _WakeWordStream(speak=True, **kwargs)

        def failing_transcribe(pcm, rate):
            raise RuntimeError("simulated network failure")

        result = main.wait_for_wake_word(timeout=0.2, stream_factory=factory, transcribe_fn=failing_transcribe)
        self.assertFalse(result)


class WakePhraseMatchingTests(unittest.TestCase):
    def test_matches_case_and_punctuation_insensitively(self):
        self.assertTrue(main._looks_like_wake_phrase("Hey, JARVIS! Wake up."))
        self.assertTrue(main._looks_like_wake_phrase("jarvis"))

    def test_does_not_match_unrelated_text(self):
        self.assertFalse(main._looks_like_wake_phrase("what time is it"))
        self.assertFalse(main._looks_like_wake_phrase(""))


if __name__ == "__main__":
    unittest.main()
