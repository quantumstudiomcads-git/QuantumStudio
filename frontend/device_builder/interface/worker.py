"""Qt worker for bounded interface matching; it never mutates Device state."""

from PySide6.QtCore import QObject, Signal, Slot

from .integration import prepare_interface_match


class InterfaceMatchWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, region_a, region_b, parameters):
        super().__init__()
        self._region_a = region_a.duplicate(name=region_a.name)
        self._region_b = region_b.duplicate(name=region_b.name)
        # duplicate() creates new Region IDs; retain semantic IDs for the result.
        self._region_a.id = region_a.id
        self._region_b.id = region_b.id
        self._parameters = dict(parameters)

    @Slot()
    def run(self):
        try:
            self.finished.emit(prepare_interface_match(self._region_a, self._region_b, **self._parameters))
        except Exception as error:
            self.failed.emit(str(error))
