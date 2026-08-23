from backend.core.workflow import Workflow
from backend.core.task import Task


class SCFWorkflow(Workflow):

    workflow_id = "scf"

    def validate(self):
        calculation = self.calculation

        if calculation is None:
            raise RuntimeError(
                "No calculation was provided."
            )

        required = [
            "structure",
            "parameters",
            "execution_target",
        ]

        for attribute in required:
            if not hasattr(calculation, attribute):
                raise RuntimeError(
                    f"Calculation is missing '{attribute}'."
                )

        if calculation.structure is None:
            raise RuntimeError(
                "Calculation structure is empty."
            )

        if calculation.parameters is None:
            raise RuntimeError(
                "Calculation parameters are empty."
            )

        if not calculation.execution_target:
            raise RuntimeError(
                "No execution target was specified."
            )

        return True


    def build_tasks(self):

        def prepare():

            print(
                "Preparing SCF calculation..."
            )

            return {
                "status": "prepared"
            }

        def generate_input():

            print(
                "Generating Quantum ESPRESSO input..."
            )

            return {
                "input": "pw.in"
            }

        def execute():

            print(
                "QE execution placeholder..."
            )

            return {
                "output": "pw.out"
            }

        def parse():

            print(
                "Parsing QE results..."
            )

            return {
                "energy": None
            }

        return [

            Task(
                id="prepare",
                name="Prepare Calculation",
                action=prepare
            ),

            Task(
                id="generate_input",
                name="Generate QE Input",
                action=generate_input,
                dependencies=[
                    "prepare"
                ]
            ),

            Task(
                id="execute",
                name="Run Quantum ESPRESSO",
                action=execute,
                dependencies=[
                    "generate_input"
                ]
            ),

            Task(
                id="parse",
                name="Parse Results",
                action=parse,
                dependencies=[
                    "execute"
                ]
            )
        ]
