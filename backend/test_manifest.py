from backend.core.calculation import Calculation
from backend.core.manifest import save_manifest


diamond = {
    "lattice": [
        [3.567, 0.000, 0.000],
        [0.000, 3.567, 0.000],
        [0.000, 0.000, 3.567],
    ],

    "species": [
        "C",
        "C",
    ],

    "positions": [
        [0.000, 0.000, 0.000],
        [0.250, 0.250, 0.250],
    ],

    "coordinate_system": "crystal",
}


calculation = Calculation(
    workflow="scf",

    structure=diamond,

    parameters={
        "functional": "PBE",
        "ecutwfc": 60,
        "ecutrho": 480,
        "kpoints": [6, 6, 6],
    },

    execution_target="local",
)


path = save_manifest(
    calculation.manifest,
    f"backend/artifacts/{calculation.id}/manifest.json",
)


print("==============================================")
print(" QUANTUM STUDIO MANIFEST TEST")
print("==============================================")
print()
print(f"Calculation ID : {calculation.id}")
print(f"Workflow       : {calculation.workflow}")
print(f"Status         : {calculation.status}")
print(f"Target         : {calculation.execution_target}")
print()
print(f"Manifest saved:")
print(path)
