"""Legacy compatibility entry point for built-in executable definitions."""


def register_builtin_calculations():
    """Ensure the single active backend registry is imported and validated.

    Definitions now live only in the executable calculation-family modules;
    this compatibility function no longer registers a second basic definition set.
    """
    import backend.calculations
    from backend.calculations import registry

    registry.validate()
    return registry.all()
