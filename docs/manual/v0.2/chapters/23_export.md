# 23. Export

Export is available in context rather than as a single promise of every format.
Use the action shown by the active workspace and confirm the selected format in
the current dialog.

| Context | Current export/saving scope |
| --- | --- |
| Project Hub / Project | Create, open, and save .qs project state. |
| Builder | Structure import/export where the current Builder control presents a supported format. |
| Calculate | Generated QE inputs, available execution/output inspection, and parsed-result access. |
| Analyze | Data export and figure export for supported parsed result views. |
| Help | Metadata-only diagnostics ZIP through **Export Diagnostics…**. |

Avoid overwriting an external workflow directory or assuming an engine-native
format is supported without a visible dialog option. Paths with spaces and
Unicode are supported by the validated standalone startup matrix, but a target
directory can still be unwritable.

> **Screenshot planned for B5.3:** Current data/figure export dialog using a
> non-sensitive destination and visible format controls.

See [Diagnostics](26_diagnostics.md) for the intentionally limited support
archive.
