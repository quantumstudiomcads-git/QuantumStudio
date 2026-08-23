"""
Quantum Studio — Crystallography Backend

Optional spglib integration.

The GUI can still operate when spglib is unavailable.
"""

import numpy as np


class Crystallography:

    @staticmethod
    def spglib_available():

        try:
            import spglib
            return True
        except ImportError:
            return False

    @staticmethod
    def _symbols_and_positions(structure):

        symbols = [
            atom.element
            for atom in structure.atoms
        ]

        unique = {}

        for symbol in symbols:
            if symbol not in unique:
                unique[symbol] = len(unique) + 1

        numbers = [
            unique[symbol]
            for symbol in symbols
        ]

        cell = np.asarray(
            structure.cell,
            dtype=float,
        )

        positions = []

        for atom in structure.atoms:

            p = np.array(
                [
                    atom.x,
                    atom.y,
                    atom.z,
                ]
            )

            f = np.linalg.solve(
                cell.T,
                p,
            )

            positions.append(f)

        return (
            cell,
            np.asarray(
                positions,
                dtype=float,
            ),
            np.asarray(
                numbers,
                dtype=int,
            ),
            unique,
        )

    @staticmethod
    def symmetry(structure):

        try:
            import spglib
        except ImportError:

            return {
                "available": False,
                "error": (
                    "spglib is not installed."
                ),
            }

        cell, positions, numbers, unique = (
            Crystallography._symbols_and_positions(
                structure
            )
        )

        dataset = spglib.get_symmetry_dataset(
            (
                cell,
                positions,
                numbers,
            ),
            symprec=1e-5,
            angle_tolerance=-1.0,
        )

        if dataset is None:

            return {
                "available": True,
                "error": (
                    "spglib could not identify "
                    "the symmetry."
                ),
            }

        return {
            "available": True,
            "international": (
                dataset.international
            ),
            "number": int(
                dataset.number
            ),
            "hall": dataset.hall,
            "pointgroup": (
                dataset.pointgroup
            ),
            "wyckoffs": list(
                dataset.wyckoffs
            ),
            "equivalent_atoms": list(
                dataset.equivalent_atoms
            ),
        }

    @staticmethod
    def primitive_structure(structure):

        try:
            import spglib
        except ImportError:
            return None

        cell, positions, numbers, unique = (
            Crystallography._symbols_and_positions(
                structure
            )
        )

        primitive = spglib.standardize_cell(
            (
                cell,
                positions,
                numbers,
            ),
            to_primitive=True,
            no_idealize=False,
            symprec=1e-5,
        )

        return primitive

    @staticmethod
    def conventional_structure(structure):

        try:
            import spglib
        except ImportError:
            return None

        cell, positions, numbers, unique = (
            Crystallography._symbols_and_positions(
                structure
            )
        )

        conventional = spglib.standardize_cell(
            (
                cell,
                positions,
                numbers,
            ),
            to_primitive=False,
            no_idealize=False,
            symprec=1e-5,
        )

        return conventional
