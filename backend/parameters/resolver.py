from backend.parameters.accuracy import (
    get_accuracy_preset,
)

from backend.parameters.defaults import (
    CALCULATION_DEFAULTS,
)


class ParameterResolver:

    def __init__(
        self,
        calculation_id: str,
        accuracy: str = "balanced",
        overrides: dict | None = None,
    ):

        self.calculation_id = calculation_id

        self.accuracy = accuracy

        self.overrides = overrides or {}


    def resolve(self) -> dict:

        parameters = self._get_defaults()

        parameters = self._apply_accuracy(
            parameters
        )

        parameters = self._apply_overrides(
            parameters
        )

        return parameters


    def _get_defaults(self) -> dict:

        return dict(
            CALCULATION_DEFAULTS.get(
                self.calculation_id,
                {},
            )
        )


    def _apply_accuracy(
        self,
        parameters: dict,
    ) -> dict:

        preset = get_accuracy_preset(
            self.accuracy
        )

        parameters["conv_thr"] = (
            preset.conv_thr
        )

        parameters["accuracy"] = (
            preset.name
        )

        parameters["kpoint_density"] = (
            preset.kpoint_density
        )

        if "ecutwfc" in parameters:

            parameters["ecutwfc"] = (
                parameters["ecutwfc"]
                * preset.ecutwfc_factor
            )

        if "force_threshold" in parameters:

            parameters["force_threshold"] = (
                preset.force_threshold
            )

        return parameters


    def _apply_overrides(
        self,
        parameters: dict,
    ) -> dict:

        parameters.update(
            self.overrides
        )

        return parameters
