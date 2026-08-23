import json
from pathlib import Path

from frontend.core.structure import Structure


class Project:

    FORMAT = "qstudio"
    VERSION = "0.2"

    def __init__(
        self,
        name,
        file_path=None,
    ):

        self.name = name

        self.file_path = (
            Path(file_path)
            if file_path
            else None
        )

        self.structure = {}

        self.calculator = {}
        self.workflows = {}
        self.results = {}
        self.analysis = {}

        self.modified = False

    # ============================================================
    # Save
    # ============================================================

    def to_dict(self):

        return {
            "format": self.FORMAT,
            "version": self.VERSION,

            "project": {
                "name": self.name,
            },

            "structure": self.structure,

            "calculator": self.calculator,
            "workflows": self.workflows,
            "results": self.results,
            "analysis": self.analysis,
        }

    def save(
        self,
        file_path=None,
    ):

        if file_path is not None:

            self.file_path = Path(
                file_path
            )

        if self.file_path is None:

            raise ValueError(
                "No project file path specified."
            )

        self.file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.file_path.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                self.to_dict(),
                file,
                indent=4,
            )

        self.modified = False

    # ============================================================
    # Load
    # ============================================================

    @classmethod
    def load(
        cls,
        file_path,
    ):

        path = Path(file_path)

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        if data.get("format") != cls.FORMAT:

            raise ValueError(
                "Not a Quantum Studio project."
            )

        project_data = data.get(
            "project",
            {},
        )

        project = cls(
            project_data.get(
                "name",
                "Untitled Project",
            ),
            path,
        )

        project.structure = data.get(
            "structure",
            {},
        )

        project.calculator = data.get(
            "calculator",
            {},
        )

        project.workflows = data.get(
            "workflows",
            {},
        )

        project.results = data.get(
            "results",
            {},
        )

        project.analysis = data.get(
            "analysis",
            {},
        )

        project.modified = False

        return project

    # ============================================================
    # Structure model
    # ============================================================

    def get_structure(self):

        if not self.structure:

            return Structure(
                name=self.name
            )

        # New structure format
        if "atoms" in self.structure:

            return Structure.from_dict(
                self.structure
            )

        # Backward compatibility with our old format
        atoms = self.structure.get(
            "atoms",
            [],
        )

        cell = self.structure.get(
            "cell",
            None,
        )

        return Structure(
            atoms=[
                __import__(
                    "frontend.structure",
                    fromlist=["Atom"],
                ).Atom(
                    item["element"],
                    item["x"],
                    item["y"],
                    item["z"],
                )
                for item in atoms
            ],
            cell=cell,
            name=self.name,
        )

    def set_structure(
        self,
        structure,
    ):

        self.structure = (
            structure.to_dict()
        )

        self.modified = True
