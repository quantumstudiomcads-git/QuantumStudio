"""Dedicated operator application entry point."""
from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from .main_window import LicenceManagerWindow
from .storage import StorageError


def main(argv=None):
    parser = argparse.ArgumentParser(prog="Quantum Studio Licence Manager")
    parser.add_argument("--test-mode", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        window = LicenceManagerWindow(test_mode=args.test_mode)
    except StorageError as error:
        # Only the typed, redacted recovery text is shown; never display raw
        # SQLite/DPAPI exceptions or any protected bytes.
        import logging
        logging.getLogger(__name__).warning("Licence Manager storage bootstrap blocked (%s).", type(error).__name__)
        QMessageBox.critical(None, "Licence Manager storage unavailable", str(error))
        return 2
    window.show()
    return app.exec()
