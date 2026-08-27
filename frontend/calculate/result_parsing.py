"""Background parsing of completed execution artifacts."""
from __future__ import annotations

import traceback
from PySide6.QtCore import QThread, Signal


class ResultParsingWorker(QThread):
    finished_result = Signal(object)

    def __init__(self, service, workflow_root, execution_id, parent=None):
        super().__init__(parent)
        self.service = service
        self.workflow_root = str(workflow_root)
        self.execution_id = str(execution_id)
        self.outcome = None
        self.error = None

    def run(self):
        try:
            self.outcome = self.service.parse(self.workflow_root, self.execution_id)
        except Exception as error:
            self.error = (str(error) or type(error).__name__, traceback.format_exc())
        self.finished_result.emit(self)
