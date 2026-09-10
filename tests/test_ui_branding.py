import os
import unittest
from types import MethodType, SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_GUI_SKIP_REASON = ""
try:
    from PyQt6.QtWidgets import QApplication

    import ui
except Exception as _exc:  # PyQt6 (or its native Qt libs) unavailable
    QApplication = None  # type: ignore
    ui = None  # type: ignore
    _GUI_SKIP_REASON = f"PyQt6/ui unavailable in this environment: {_exc}"


@unittest.skipIf(QApplication is None, _GUI_SKIP_REASON)
class UIBrandingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.app = QApplication.instance() or QApplication([])
        except Exception as exc:
            # The import succeeded but Qt still couldn't initialize a
            # display (e.g. the 'offscreen' platform plugin is missing
            # its own native dependencies). Skip rather than error.
            raise unittest.SkipTest(f"Qt could not initialize a display: {exc}") from exc

    def test_maker_signature_is_present_and_theme_aware(self):
        host = SimpleNamespace()
        host._style_maker_signature = MethodType(
            ui.MainWindow._style_maker_signature, host
        )

        strip = ui.MainWindow._build_maker_signature(host)
        self.addCleanup(strip.deleteLater)

        self.assertEqual(host._maker_signature_lbl.text(), "amd.creationz™")
        self.assertEqual(strip.objectName(), "JarvisMakerSignature")
        self.assertEqual(strip.height(), 20)
        self.assertIn(ui.C.TEXT_DIM, host._maker_signature_lbl.styleSheet())
        self.assertIn(ui.C.BG, strip.styleSheet())
        self.assertEqual(
            host._maker_signature_lbl.accessibleName(), "amd.creationz trademark"
        )


if __name__ == "__main__":
    unittest.main()
