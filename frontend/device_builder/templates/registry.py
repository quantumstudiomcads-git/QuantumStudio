"""Deterministic registry for Qt-free Device templates."""

from __future__ import annotations

from collections import OrderedDict


class TemplateRegistry:
    """Small explicit registry; UI code never needs template-specific conditionals."""

    def __init__(self, templates=()):
        self._templates = OrderedDict()
        for template in templates:
            self.register(template)

    def register(self, template):
        template_id = str(getattr(template, "id", "")).strip()
        if not template_id:
            raise ValueError("Device templates require a non-empty id.")
        if template_id in self._templates:
            raise ValueError(f"Duplicate Device template id: {template_id}")
        self._templates[template_id] = template
        return template

    def get(self, template_id):
        try:
            return self._templates[str(template_id)]
        except KeyError as error:
            raise KeyError(f"Unknown Device template: {template_id}") from error

    def list_templates(self):
        return tuple(self._templates.values())

    def __contains__(self, template_id):
        return str(template_id) in self._templates
