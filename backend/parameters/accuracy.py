from dataclasses import dataclass


@dataclass(frozen=True)
class AccuracyPreset:

    name: str

    conv_thr: float

    ecutwfc_factor: float

    kpoint_density: str

    force_threshold: float


ACCURACY_PRESETS = {

    "fast": AccuracyPreset(
        name="fast",

        conv_thr=1e-6,

        ecutwfc_factor=0.8,

        kpoint_density="low",

        force_threshold=1e-3,
    ),

    "balanced": AccuracyPreset(
        name="balanced",

        conv_thr=1e-8,

        ecutwfc_factor=1.0,

        kpoint_density="medium",

        force_threshold=1e-4,
    ),

    "high": AccuracyPreset(
        name="high",

        conv_thr=1e-10,

        ecutwfc_factor=1.25,

        kpoint_density="high",

        force_threshold=5e-5,
    ),

    "extreme": AccuracyPreset(
        name="extreme",

        conv_thr=1e-12,

        ecutwfc_factor=1.5,

        kpoint_density="very_high",

        force_threshold=1e-5,
    ),
}


def get_accuracy_preset(
    name: str,
) -> AccuracyPreset:

    key = name.lower()

    if key not in ACCURACY_PRESETS:

        raise ValueError(
            f"Unknown accuracy preset: {name}"
        )

    return ACCURACY_PRESETS[key]
