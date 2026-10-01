"""Dedicated operator application entry point."""
from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from .main_window import LicenceManagerWindow


def main(argv=None):
    parser = argparse.ArgumentParser(prog="Quantum Studio Licence Manager")
    parser.add_argument("--test-mode", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = LicenceManagerWindow(test_mode=args.test_mode)
    window.show()
    return app.exec()
