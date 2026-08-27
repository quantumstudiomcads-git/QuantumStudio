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

        "qmesh": [4, 4, 4],

        "lo_to_splitting": False,
    },
}
