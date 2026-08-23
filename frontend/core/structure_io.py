from pathlib import Path

from ase.io import read, write

from frontend.core.structure import Atom, Structure


class StructureIO:
    """
    Universal structure input/output layer for Quantum Studio.

    ASE handles the file-format conversion.
    Quantum Studio internally uses its own Structure object.
    """

    COMMON_FORMATS = {
        ".cif": "cif",
        ".xyz": "xyz",
        ".vasp": "vasp",
        ".xsf": "xsf",
        ".pdb": "proteindatabank",
        ".mol": "mol",
        ".sdf": "sdf",
        ".res": "res",
        ".gen": "gen",
    }

    VASP_FILENAMES = {
        "POSCAR",
        "CONTCAR",
    }

    @classmethod
    def read_structure(
        cls,
        path,
    ):
        """
        Read any ASE-supported structure file and convert it
        into the Quantum Studio Structure representation.
        """

        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(
                f"Structure file does not exist:\n{path}"
            )

        fmt = cls._detect_format(path)

        try:
            atoms = read(
                str(path),
                format=fmt,
            )
        except Exception as error:
            raise RuntimeError(
                f"ASE could not read:\n{path}\n\n"
                f"Detected format: {fmt}\n\n"
                f"ASE error:\n{error}"
            ) from error

        return cls.from_ase(
            atoms,
            name=path.stem,
        )

    @classmethod
    def from_ase(
        cls,
        atoms,
        name="Imported Structure",
    ):
        """
        Convert ASE Atoms → Quantum Studio Structure.
        """

        positions = atoms.get_positions()
        symbols = atoms.get_chemical_symbols()

        qs_atoms = []

        for symbol, position in zip(
            symbols,
            positions,
        ):
            qs_atoms.append(
                Atom(
                    symbol,
                    position[0],
                    position[1],
                    position[2],
                )
            )

        # ASE stores a 3x3 cell.
        cell_array = atoms.cell.array

        cell = [
            [
                float(value)
                for value in vector
            ]
            for vector in cell_array
        ]

        # Molecules/XYZ files may have no cell.
        if not any(
            abs(value) > 1e-10
            for vector in cell
            for value in vector
        ):

            cell = cls._make_default_cell(
                positions
            )

            periodic = [
                False,
                False,
                False,
            ]

        else:

            periodic = [
                bool(value)
                for value in atoms.pbc
            ]

        structure = Structure(
            atoms=qs_atoms,
            cell=cell,
            name=name,
        )

        structure.periodic = periodic

        structure._record(
            "Imported through ASE"
        )

        return structure

    @classmethod
    def write_structure(
        cls,
        structure,
        path,
        fmt=None,
    ):
        """
        Write a Quantum Studio Structure using ASE.
        """

        path = Path(path)

        if fmt is None:
            fmt = cls._detect_format(
                path
            )

        atoms = cls.to_ase(
            structure
        )

        try:
            write(
                str(path),
                atoms,
                format=fmt,
            )
        except Exception as error:
            raise RuntimeError(
                f"ASE could not write:\n{path}\n\n"
                f"Format: {fmt}\n\n"
                f"ASE error:\n{error}"
            ) from error

    @classmethod
    def to_ase(
        cls,
        structure,
    ):
        """
        Convert Quantum Studio Structure → ASE Atoms.
        """

        from ase import Atoms

        symbols = [
            atom.element
            for atom in structure.atoms
        ]

        positions = [
            [
                atom.x,
                atom.y,
                atom.z,
            ]
            for atom in structure.atoms
        ]

        atoms = Atoms(
            symbols=symbols,
            positions=positions,
            cell=structure.cell,
            pbc=structure.periodic,
        )

        return atoms

    @classmethod
    def _detect_format(
        cls,
        path,
    ):
        """
        Detect a structure format.

        POSCAR and CONTCAR have no extension, so they are handled
        explicitly.
        """

        filename = path.name.upper()

        if filename in cls.VASP_FILENAMES:
            return "vasp"

        suffix = path.suffix.lower()

        if suffix in cls.COMMON_FORMATS:
            return cls.COMMON_FORMATS[
                suffix
            ]

        # ASE can infer many formats from filenames.
        # For unknown extensions we first try ASE's normal detection.
        try:
            from ase.io.formats import filetype

            return filetype(
                str(path)
            )

        except Exception:

            raise ValueError(
                f"Quantum Studio could not determine the structure "
                f"format for:\n{path}\n\n"
                f"Use a standard structure format or choose a "
                f"supported ASE format explicitly."
            )

    @staticmethod
    def _make_default_cell(
        positions,
    ):
        """
        Generate a reasonable non-periodic simulation box
        for molecular/XYZ structures.
        """

        if len(positions) == 0:
            return [
                [10.0, 0.0, 0.0],
                [0.0, 10.0, 0.0],
                [0.0, 0.0, 10.0],
            ]

        mins = positions.min(axis=0)
        maxs = positions.max(axis=0)

        lengths = maxs - mins + 10.0

        return [
            [float(lengths[0]), 0.0, 0.0],
            [0.0, float(lengths[1]), 0.0],
            [0.0, 0.0, float(lengths[2])],
        ]

    @classmethod
    def supported_extensions(cls):
        return sorted(
            cls.COMMON_FORMATS.keys()
        )

    @classmethod
    def description(cls):
        return (
            "Quantum Studio uses ASE for structure I/O. "
            "This provides support for CIF, VASP, XYZ, XSF, "
            "PDB, MOL/SDF, and many other formats supported by ASE."
        )
