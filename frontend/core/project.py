import json
from pathlib import Path

from frontend.core.structure import Structure


class Project:

    FORMAT = "qstudio"
    VERSION = "0.4"

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
        self.device = None
        self.device_load_error = None
        self.calculations = []
        self.calculation_load_errors = []

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
            # Optional from v0.3. It is source Device state only; assembled
            # previews and UI/history state are intentionally excluded.
            "device": (
                None
                if self.device is None
                else self.device.to_dict()
            ),
            # Optional from v0.4. Only configured request source state persists;
            # derived execution plans and compiler caches are intentionally excluded.
            "calculations": {
                "schema_version": "0.1",
                "requests": [request.to_persistence_dict() for request in self.calculations],
            },

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

        # Device data is optional for pre-Device Builder .qs projects. A
        # malformed optional device does not prevent the rest of the Project
        # from opening; the recoverable failure is exposed to Device Builder.
        device_data = data.get("device", None)
        if device_data is not None:
            try:
                from frontend.device_builder.assembly import validate_device
                from frontend.device_builder.model import Device
                device = Device.from_dict(device_data)
                validate_device(device, allow_empty=True).require_valid()
                project.device = device
            except Exception as error:
                project.device = None
                project.device_load_error = f"Device data was not loaded: {error}"

        # Calculation requests are optional and independently recoverable. A
        # malformed request never prevents the Project, Builder, or Device from loading.
        calculation_data = data.get("calculations", None)
        if calculation_data is not None:
            try:
                from backend.core.calculation_request import CalculationRequest
                from frontend.core.structure import Structure
                records = calculation_data.get("requests", []) if isinstance(calculation_data, dict) else calculation_data
                if not isinstance(records, list):
                    raise ValueError("Calculation section requests must be a list.")
                seen_ids = set()
                for index, record in enumerate(records, start=1):
                    try:
                        request = CalculationRequest.from_persistence_dict(record)
                        if request.id in seen_ids:
                            raise ValueError(f"Duplicate calculation request id: {request.id}")
                        Structure.from_dict(request.structure)
                        seen_ids.add(request.id)
                        project.calculations.append(request)
                    except Exception as error:
                        project.calculation_load_errors.append(f"Calculation {index} was not loaded: {error}")
            except Exception as error:
                project.calculation_load_errors.append(f"Calculation data was not loaded: {error}")

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

    # ============================================================
    # Device model
    # ============================================================

    def get_device(self):
        """Return the optional persistent Device domain object, if present."""
        return self.device

    def set_device(self, device):
        """Set the active Device through the Project ownership boundary."""
        if device is not None:
            from frontend.device_builder.model import Device
            if not isinstance(device, Device):
                raise TypeError("Project device must be a Device or None.")
        self.device = device
        self.device_load_error = None
        self.modified = True

    def clear_device(self):
        self.set_device(None)

    # ============================================================
    # Persistent calculation requests
    # ============================================================

    def get_calculations(self):
        """Return an immutable view of configured requests owned by this Project."""
        return tuple(self.calculations)

    def get_calculation(self, request_id):
        return next((request for request in self.calculations if request.id == request_id), None)

    def add_calculation(self, request):
        from backend.core.calculation_request import CalculationRequest
        if not isinstance(request, CalculationRequest):
            raise TypeError("Project calculations must be CalculationRequest instances.")
        if self.get_calculation(request.id) is not None:
            raise ValueError(f"Duplicate calculation request id: {request.id}")
        if not request.name:
            base = request.calculation_id.replace("_", " ").title()
            used = {item.name for item in self.calculations}
            index = 1
            candidate = f"{base} {index}"
            while candidate in used:
                index += 1
                candidate = f"{base} {index}"
            request.name = candidate
        self.calculations.append(request)
        self.modified = True
        return request

    def update_calculation(self, request):
        from backend.core.calculation_request import CalculationRequest
        if not isinstance(request, CalculationRequest):
            raise TypeError("Project calculations must be CalculationRequest instances.")
        for index, existing in enumerate(self.calculations):
            if existing.id == request.id:
                self.calculations[index] = request
                self.modified = True
                return request
        raise KeyError(f"Unknown calculation request id: {request.id}")

    def remove_calculation(self, request_id):
        request = self.get_calculation(request_id)
        if request is None:
            return False
        self.calculations.remove(request)
        self.modified = True
        return True
