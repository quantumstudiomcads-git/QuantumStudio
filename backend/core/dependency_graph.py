class DependencyGraph:
    """
    Resolves execution order for workflow tasks.
    """

    def __init__(self, tasks):
        self.tasks = {
            task.id: task
            for task in tasks
        }

    def resolve(self):
        resolved = []
        visited = set()
        visiting = set()

        def visit(task_id):

            if task_id in visited:
                return

            if task_id in visiting:
                raise RuntimeError(
                    f"Circular dependency detected at '{task_id}'."
                )

            if task_id not in self.tasks:
                raise RuntimeError(
                    f"Unknown dependency '{task_id}'."
                )

            visiting.add(task_id)

            task = self.tasks[task_id]

            for dependency in task.dependencies:
                visit(dependency)

            visiting.remove(task_id)

            visited.add(task_id)

            resolved.append(task)

        for task_id in self.tasks:
            visit(task_id)

        return resolved
