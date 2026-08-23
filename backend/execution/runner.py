from backend.core.dependency_graph import DependencyGraph


class WorkflowRunner:
    """
    Executes a workflow in dependency order.

    This is deliberately engine-independent.

    The same workflow can eventually be executed through:

        LocalRunner
        RemoteRunner
        HPCRunner
    """

    def __init__(self, workflow):
        self.workflow = workflow

    def run(self):

        print()
        print("=" * 60)
        print(" QUANTUM STUDIO — WORKFLOW EXECUTION")
        print("=" * 60)

        print()
        print(
            f"Workflow: "
            f"{self.workflow.workflow_id}"
        )

        print()
        print("VALIDATING WORKFLOW")

        self.workflow.validate()

        print("✓ Validation successful")

        print()
        print("BUILDING TASK GRAPH")

        tasks = self.workflow.build_tasks()

        graph = DependencyGraph(tasks)

        execution_order = graph.resolve()

        print(
            f"✓ {len(execution_order)} task(s) resolved"
        )

        results = {}

        print()
        print("EXECUTING")

        for index, task in enumerate(
            execution_order,
            start=1
        ):

            print()
            print(
                f"[{index}/{len(execution_order)}] "
                f"{task.name}"
            )

            result = task.run()

            results[task.id] = result

            print("✓ Completed")

        print()
        print("=" * 60)
        print(" WORKFLOW COMPLETED")
        print("=" * 60)

        return results
