from backend.calculations.definition import CalculationDefinition


SCF = CalculationDefinition(
    id="scf",

    name="Self-Consistent Field",

    category="Electronic Properties",

    tags=[
        "electronic",
        "ground_state",
        "qe",
    ],

    requires=[
        "structure",
    ],

    parameters=[
        "accuracy",
        "functional",
        "pseudopotential",
        "kpoints",
        "spin",
        "soc",
    ],

    produces=[
        "scf_result",
        "charge_density",
        "wavefunctions",
        "electronic_state",
    ],

    workflow="scf",
)


RELAX = CalculationDefinition(
    id="relax",

    name="Structural Relaxation",

    category="Structure Optimization",

    tags=[
        "structural",
        "relaxation",
        "qe",
    ],

    requires=[
        "structure",
    ],

    parameters=[
        "accuracy",
        "functional",
        "pseudopotential",
        "force_threshold",
        "stress_threshold",
        "spin",
        "soc",
    ],

    produces=[
        "relaxed_structure",
    ],

    workflow="relax",
)


BANDS = CalculationDefinition(
    id="bands",

    name="Band Structure",

    category="Electronic Properties",

    tags=[
        "electronic",
        "band_structure",
        "qe",
    ],

    requires=[
        "scf_result",
    ],

    parameters=[
        "accuracy",
        "functional",
        "kpath",
        "spin",
        "soc",
    ],

    produces=[
        "band_structure",
        "eigenvalues",
    ],

    workflow="bands",
)


DOS = CalculationDefinition(
    id="dos",

    name="Density of States",

    category="Electronic Properties",

    tags=[
        "electronic",
        "dos",
        "qe",
    ],

    requires=[
        "scf_result",
    ],

    parameters=[
        "accuracy",
        "functional",
        "dense_kpoints",
        "energy_window",
        "spin",
        "soc",
    ],

    produces=[
        "density_of_states",
    ],

    workflow="dos",
)


PHONONS = CalculationDefinition(
    id="phonons",

    name="Phonons",

    category="Vibrational Properties",

    tags=[
        "vibrational",
        "phonons",
        "qe",
    ],

    requires=[
        "scf_result",
    ],

    parameters=[
        "accuracy",
        "qmesh",
        "phonon_convergence",
        "lo_to_splitting",
    ],

    produces=[
        "force_constants",
        "phonon_frequencies",
        "phonon_dispersion",
        "phonon_dos",
    ],

    workflow="phonons",
)
