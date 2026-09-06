"""
Quantum Studio API

The API layer is the public interface between the GUI and
the Quantum Studio backend.

The GUI never directly calls the compiler, workflow system,
or execution engines.
"""

from fastapi import FastAPI
from backend.runtime import PRODUCT_NAME, VERSION

from backend.api.routes.calculations import router as calculations_router
from backend.api.routes.compile import router as compile_router


app = FastAPI(
    title=PRODUCT_NAME,
    description=(
        "Backend API for Quantum Studio computational "
        "materials workflows."
    ),
    version=VERSION,
)


@app.get("/")
def root():

    return {
        "application": "Quantum Studio",
        "status": "running",
    }


@app.get("/health")
def health():

    return {
        "status": "healthy",
    }


app.include_router(
    calculations_router,
    prefix="/calculations",
    tags=["Calculations"],
)


app.include_router(
    compile_router,
    prefix="/compile",
    tags=["Compiler"],
)
