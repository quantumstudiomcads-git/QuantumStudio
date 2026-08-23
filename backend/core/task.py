from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Task:
    """
    Smallest executable unit in a Quantum Studio workflow.

    A task may represent:
        - input generation
        - execution of an external program
        - parsing
        - post-processing
    """

    id: str
    name: str

    action: Callable | None = None

    dependencies: list[str] = field(default_factory=list)

    status: str = "created"

    metadata: dict[str, Any] = field(default_factory=dict)

    result: Any = None

    def run(self):
        self.status = "running"

        try:
            if self.action is not None:
                self.result = self.action()

            self.status = "completed"

        except Exception as exc:
            self.status = "failed"

            raise RuntimeError(
                f"Task '{self.name}' failed."
            ) from exc

        return self.result
