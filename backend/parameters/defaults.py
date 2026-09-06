CALCULATION_DEFAULTS = {

    "scf": {

        "functional": "PBE",

        "ecutwfc": 60,

        "ecutrho": 480,

        "conv_thr": 1e-8,

        "kpoints": [6, 6, 6],

        "spin": False,

        "soc": False,

        "spin_treatment": "SCALAR_NONSPIN",

        "starting_magnetization": {},

        "tot_magnetization": None,

        "hubbard_terms": [],

        "hubbard_projector": "ortho-atomic",
    },


    "relax": {

        "functional": "PBE",

        "ecutwfc": 60,

        "ecutrho": 480,

        "conv_thr": 1e-8,

        "force_threshold": 1e-4,

        "stress_threshold": 0.5,

        "spin": False,

        "soc": False,

        "spin_treatment": "SCALAR_NONSPIN",

        "starting_magnetization": {},

        "tot_magnetization": None,

        "hubbard_terms": [],

        "hubbard_projector": "ortho-atomic",
    },


    "bands": {

        "functional": "PBE",

        "ecutwfc": 60,

        "ecutrho": 480,

        "spin": False,

        "soc": False,

        "spin_treatment": "SCALAR_NONSPIN",

        "starting_magnetization": {},

        "tot_magnetization": None,

        "hubbard_terms": [],

        "hubbard_projector": "ortho-atomic",

        "kpath_density": "medium",
    },


    "dos": {

        "functional": "PBE",

        "ecutwfc": 60,

        "ecutrho": 480,

        "dense_kpoints": [12, 12, 12],

        "energy_window": [-10, 10],

        "delta_e": 0.01,

        "spin": False,

        "soc": False,

        "spin_treatment": "SCALAR_NONSPIN",

        "starting_magnetization": {},

        "tot_magnetization": None,

        "hubbard_terms": [],

        "hubbard_projector": "ortho-atomic",
    },


    "pdos": {

        "functional": "PBE",

        "ecutwfc": 60,

        "ecutrho": 480,

        "dense_kpoints": [12, 12, 12],

        "energy_window": [-10, 10],

        "delta_e": 0.01,

        "spin": False,

        "soc": False,

        "spin_treatment": "SCALAR_NONSPIN",

        "starting_magnetization": {},

        "tot_magnetization": None,

        "hubbard_terms": [],

        "hubbard_projector": "ortho-atomic",
    },


    "phonons": {

        "conv_thr": 1e-10,

        "tr2_ph": 1e-14,

        "q_point": [0.0, 0.0, 0.0],

        "lo_to_splitting": False,
    },

    "born_charges": {
        "conv_thr": 1e-10,
        "tr2_ph": 1e-12,
        "q_point": [0.0, 0.0, 0.0],
        "spin_treatment": "SCALAR_NONSPIN",
    },

    "lo_to_splitting": {
        "direction": [1.0, 0.0, 0.0],
        "asr": "crystal",
    },

    "infrared": {
        "direction": [1.0, 0.0, 0.0],
        "asr": "crystal",
    },
}

# QE epsilon.x source contract: ENERGY_GRID quantities are all expressed in eV.
CALCULATION_DEFAULTS["dielectric"] = {
    "energy_min_eV": 0.0,
    "energy_max_eV": 15.0,
    "number_of_points": 601,
    "interband_broadening_eV": 0.10,
    "intraband_broadening_eV": None,
    "optical_k_mesh": [12, 12, 12],
    "optical_nbnd": 16,
    "smeartype": "gauss",
    "polarization_directions": ["xx", "yy", "zz"],
}
CALCULATION_DEFAULTS["absorption"] = dict(CALCULATION_DEFAULTS["dielectric"])
