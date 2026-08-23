from backend.calculations.registry import registry

from backend.calculations.definitions.basic import (
    SCF,
    RELAX,
    BANDS,
    DOS,
    PHONONS,
)


def register_builtin_calculations():

    definitions = [
        SCF,
        RELAX,
        BANDS,
        DOS,
        PHONONS,
    ]

    for definition in definitions:

        if not registry.exists(definition.id):
            registry.register(definition)
