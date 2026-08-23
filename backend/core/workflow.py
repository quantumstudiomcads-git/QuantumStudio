from abc import ABC, abstractmethod


class Workflow(ABC):
    """
    Base class for every Quantum Studio workflow.

    Examples:

        SCFWorkflow
        RelaxWorkflow
        BandStructureWorkflow
        PhononWorkflow
        WannierWorkflow
        BoltzmannWorkflow
        NEGFWorkflow
    """

    workflow_id = "base"

    def __init__(self, calculation):
        self.calculation = calculation

    @abstractmethod
    def validate(self):
        """
        Validate whether the calculation contains
        everything required by this workflow.
        """
        pass

    @abstractmethod
    def build_tasks(self):
        """
        Return a list of Task objects.
        """
        pass
