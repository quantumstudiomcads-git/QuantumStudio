"""Temporary compatibility exports for the renamed Builder workspace.

The active implementation lives in :mod:`frontend.builder`.  This module is
kept for external callers that still import the v0.1 Visualizer path.
"""

from frontend.builder import *  # noqa: F401,F403
from frontend.builder import Builder, StructureViewport
from frontend.builder_view import BuilderViewMixin
from frontend.builder_build import BuilderBuildMixin
from frontend.builder_measure import BuilderMeasureMixin

Visualizer = Builder
ViewMixin = BuilderViewMixin
BuildMixin = BuilderBuildMixin
MeasureMixin = BuilderMeasureMixin
