"""Qt wrapper for machine-local Quantum ESPRESSO discovery."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from backend.execution import discover_quantum_espresso


class QuantumEspressoDiscoveryWorker(QThread):
    progress = Signal(str)

    def __init__(self, configuration, *, deep=False, parent=None):
        super().__init__(parent)
        self.configuration = configuration
        self.deep = deep
        self.result = None
        self.error = None

    def run(self):
        try:
            self.progress.emit("Searching for Quantum ESPRESSO…")
            self.result = discover_quantum_espresso(
                existing_directory=self.configuration.qe_bin_directory or None,
                environment=self.configuration.environment,
                deep=self.deep,
            )
        except Exception as error:
            self.error = (str(error) or type(error).__name__, traceback.format_exc())
