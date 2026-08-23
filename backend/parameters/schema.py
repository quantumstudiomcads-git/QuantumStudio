from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Parameter:

    id: str

    name: str

    default: Any = None

    description: str = ""

    advanced: bool = False

    options: tuple = ()
