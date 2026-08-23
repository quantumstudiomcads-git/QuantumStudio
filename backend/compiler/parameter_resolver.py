"""
Quantum Studio Parameter Resolver

Converts high-level user parameters into calculation-specific
parameter sets.

Example:

User request:

    accuracy = high
    functional = HSE
    soc = True

Resolved:

    scf:
        functional = HSE
        ecutwfc = 100
        ecutrho = 800
        conv_thr = 1e-10
        soc = True

    bands:
        functional = HSE
        soc = True

    phonons:
        qmesh = [4, 4, 4]
        tr2_ph = 1e-14
"""

from typing import Any

from backend.calculations.registry import registry


class ParameterResolver:

    def __init__(
        self,
        user_parameters: dict[str, Any],
    ):

        self.user_parameters = user_parameters


    def resolve(
        self,
        calculations: list[str],
    ) -> dict[str, dict[str, Any]]:

        resolved = {}

        for calculation_id in calculations:

            resolved[calculation_id] = (
                self._resolve_calculation(
                    calculation_id
                )
            )

        return resolved


    def _resolve_calculation(
        self,
        calculation_id: str,
    ) -> dict[str, Any]:

        calculation = registry.get(
            calculation_id
        )

        parameters = {}


        # -----------------------------------------------------
        # Accuracy preset
        # -----------------------------------------------------

        accuracy = self.user_parameters.get(
            "accuracy",
            "standard",
        )

        parameters.update(
            self._accuracy_defaults(
                calculation_id,
                accuracy,
            )
        )


        # -----------------------------------------------------
        # Copy user parameters relevant to this calculation
        # -----------------------------------------------------

        for parameter in calculation.parameters:

            if parameter in self.user_parameters:

                parameters[parameter] = (
                    self.user_parameters[
                        parameter
                    ]
                )


        return parameters


    def _accuracy_defaults(
        self,
        calculation_id: str,
        accuracy: str,
    ) -> dict[str, Any]:

        presets = {

            "low": {

                "scf": {
                    "ecutwfc": 40,
                    "ecutrho": 320,
                    "conv_thr": 1e-6,
                    "kpoints": [4, 4, 4],
                },

                "bands": {
                    "kpoint_density": "low",
                },

                "dos": {
                    "dense_kpoints": [6, 6, 6],
                },

                "phonons": {
                    "qmesh": [2, 2, 2],
                    "tr2_ph": 1e-10,
                },
            },


            "standard": {

                "scf": {
                    "ecutwfc": 60,
                    "ecutrho": 480,
                    "conv_thr": 1e-8,
                    "kpoints": [6, 6, 6],
                },

                "bands": {
                    "kpoint_density": "standard",
                },

                "dos": {
                    "dense_kpoints": [10, 10, 10],
                },

                "phonons": {
                    "qmesh": [4, 4, 4],
                    "tr2_ph": 1e-12,
                },
            },


            "high": {

                "scf": {
                    "ecutwfc": 100,
                    "ecutrho": 800,
                    "conv_thr": 1e-10,
                    "kpoints": [8, 8, 8],
                },

                "bands": {
                    "kpoint_density": "high",
                },

                "dos": {
                    "dense_kpoints": [16, 16, 16],
                },

                "phonons": {
                    "qmesh": [6, 6, 6],
                    "tr2_ph": 1e-14,
                },
            },
        }


        return dict(
            presets
            .get(
                accuracy,
                presets["standard"],
            )
            .get(
                calculation_id,
                {},
            )
        )
