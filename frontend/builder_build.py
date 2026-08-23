"""Compatibility shim; use frontend.builder.build.controller for new code."""
from frontend.builder.build.controller import BuilderBuildMixin

__all__ = ["BuilderBuildMixin"]
