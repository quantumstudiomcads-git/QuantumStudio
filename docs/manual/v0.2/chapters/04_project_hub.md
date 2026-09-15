# 4. Project Hub

Project Hub is the start/open window for Quantum Studio projects. Its visible actions are **New Project**, **Open Project**, a recent-project list, and **Clear**.

## Create a project

Choose **New Project**, enter a Project name and location, and confirm. Quantum Studio creates a file named project-name.qs.

> **Screenshot planned for B5.3:** New Project dialog with Project name, Location, Browse, and the .qs outcome visible.

## Open a project

Choose **Open Project** and select a file using the filter **Quantum Studio Projects (*.qs)**. The file opens into a Project Window with Builder, Calculate, Analyze, and entitlement-dependent Device Builder.

## Recent projects and recovery

Recent projects are local references, not embedded copies. Project Hub maintains up to ten existing, well-formed .qs paths and ignores malformed, missing, or duplicate records. **Clear** removes the recent-project list; it does not delete projects.

If a selected project is corrupt, Quantum Studio presents a user-actionable load error. A stale recent entry is removed rather than presented as valid.
