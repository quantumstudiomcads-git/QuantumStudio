from backend.core.calculation import Calculation
from backend.workflows.electronic.scf import SCFWorkflow
from backend.execution.runner import WorkflowRunner


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


workflow = SCFWorkflow(calculation)

runner = WorkflowRunner(workflow)

results = runner.run()


print()
print("RESULTS")
print("-" * 60)

for task_id, result in results.items():
    print(f"{task_id}: {result}")
