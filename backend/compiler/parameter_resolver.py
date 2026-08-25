"""Deterministic parameter resolution for the engine-agnostic plan layer."""

from __future__ import annotations

from typing import Any

from backend.calculations.registry import CalculationRegistry, registry
from backend.parameters.defaults import CALCULATION_DEFAULTS


class ParameterResolver:
    """Resolve each calculation exactly once with explicit precedence.

    Precedence: schema defaults -> accuracy preset -> workflow prerequisite
    defaults -> structure-derived defaults -> explicit request parameters.
    No structure-derived values are introduced yet; the dedicated hook keeps
    that future policy out of Qt widgets and preserves reproducibility.
    """

    def __init__(self, user_parameters: dict[str, Any] | None, registry_instance: CalculationRegistry | None = None):
        if user_parameters is not None and not isinstance(user_parameters, dict):
            raise TypeError("Calculation request parameters must be a mapping.")
        self.user_parameters = dict(user_parameters or {})
        self.registry = registry if registry_instance is None else registry_instance

    def resolve(
        self,
        calculations: list[str],
        workflow_parameters: dict[str, dict[str, Any]] | None = None,
        structure: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        overrides = workflow_parameters or {}
        return {
            calculation_id: self._resolve_calculation(
                calculation_id, dict(overrides.get(calculation_id, {})), structure,
            )
            for calculation_id in calculations
        }

    def _resolve_calculation(
        self, calculation_id: str, workflow_defaults: dict[str, Any], structure: dict[str, Any] | None,
    ) -> dict[str, Any]:
        definition = self.registry.get(calculation_id)
        parameters = dict(CALCULATION_DEFAULTS.get(calculation_id, {}))
        accuracy = str(self.user_parameters.get("accuracy", "standard")).lower()
        parameters.update(self._accuracy_defaults(calculation_id, accuracy))
        parameters.update(workflow_defaults)
        parameters.update(self._structure_defaults(calculation_id, structure))
        for parameter in definition.parameters:
            if parameter in self.user_parameters:
                parameters[parameter] = self.user_parameters[parameter]
        return parameters

    @staticmethod
    def _structure_defaults(calculation_id: str, structure: dict[str, Any] | None) -> dict[str, Any]:
        # C3 deliberately derives no scientific numeric defaults from geometry.
        # The hook documents the layer and prevents future GUI-side derivation.
        return {}

    @staticmethod
    def _accuracy_defaults(calculation_id: str, accuracy: str) -> dict[str, Any]:
        presets = {
            "low": {
                "scf": {"ecutwfc": 40, "ecutrho": 320, "conv_thr": 1e-6, "kpoints": [4, 4, 4]},
                "bands": {"kpoint_density": "low"},
                "dos": {"dense_kpoints": [6, 6, 6]},
                "pdos": {"dense_kpoints": [6, 6, 6]},
                "phonons": {"qmesh": [2, 2, 2], "tr2_ph": 1e-10},
            },
            "standard": {
                "scf": {"ecutwfc": 60, "ecutrho": 480, "conv_thr": 1e-8, "kpoints": [6, 6, 6]},
                "bands": {"kpoint_density": "standard"},
                "dos": {"dense_kpoints": [10, 10, 10]},
                "pdos": {"dense_kpoints": [10, 10, 10]},
                "phonons": {"qmesh": [4, 4, 4], "tr2_ph": 1e-12},
            },
            "high": {
                "scf": {"ecutwfc": 100, "ecutrho": 800, "conv_thr": 1e-10, "kpoints": [8, 8, 8]},
                "bands": {"kpoint_density": "high"},
                "dos": {"dense_kpoints": [16, 16, 16]},
                "pdos": {"dense_kpoints": [16, 16, 16]},
                "phonons": {"qmesh": [6, 6, 6], "tr2_ph": 1e-14},
            },
        }
        aliases = {"balanced": "standard", "fast": "low"}
        return dict(presets.get(aliases.get(accuracy, accuracy), presets["standard"]).get(calculation_id, {}))
