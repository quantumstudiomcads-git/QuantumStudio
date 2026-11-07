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
    parser.add_argument("--test-data-root", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.test_data_root and not args.test_mode:
        parser.error("--test-data-root requires --test-mode")
    from backend.licensing.configuration import (
        ConfigurationError, Environment, deployment_environment, validate_switches, validate_origin,
    )
    import os
    try:
        environment = deployment_environment()
        validate_switches(os.environ, environment)
        if environment is not Environment.LOCAL:
            if args.test_mode:
                raise ConfigurationError("test-setting-not-allowed")
            validate_origin(os.environ.get("QS_OPERATOR_WEBSITE_URL", ""), environment)
    except ConfigurationError as error:
        parser.error(str(error))
    app = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        window = LicenceManagerWindow(test_mode=args.test_mode, data_root_override=args.test_data_root)
    except StorageError as error:
        # Only the typed, redacted recovery text is shown; never display raw
        # SQLite/DPAPI exceptions or any protected bytes.
        import logging
        logging.getLogger(__name__).warning("Licence Manager storage bootstrap blocked (%s).", type(error).__name__)
        QMessageBox.critical(None, "Licence Manager storage unavailable", str(error))
        return 2
    window.show()
    try:
        return app.exec()
    finally:
        window.close()
