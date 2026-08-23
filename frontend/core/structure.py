import copy
import math
from pathlib import Path


class Atom:
    def __init__(
        self,
        element,
        x,
        y,
        z,
    ):
        self.element = str(element)
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    def copy(self):
        return Atom(
            self.element,
            self.x,
            self.y,
            self.z,
        )

    def as_dict(self):
        return {
            "element": self.element,
            "x": self.x,
            "y": self.y,
            "z": self.z,
        }


class Structure:
    """
    Core Quantum Studio structure model.

    Coordinates are Cartesian and expressed in Angstrom.
    """

    def __init__(
        self,
        atoms=None,
        cell=None,
        name="Untitled Structure",
    ):

        self.name = name

        self.atoms = atoms or []

        self.cell = cell or [
            [10.0, 0.0, 0.0],
            [0.0, 10.0, 0.0],
            [0.0, 0.0, 10.0],
        ]

        self.periodic = [
            True,
            True,
            True,
        ]

        self.history = []

    # ============================================================
    # Serialization
    # ============================================================

    def to_dict(self):

        return {
            "name": self.name,

            "atoms": [
                atom.as_dict()
                for atom in self.atoms
            ],

            "cell": copy.deepcopy(
                self.cell
            ),

            "periodic": list(
                self.periodic
            ),

            "history": list(
                self.history
            ),
        }

    @classmethod
    def from_dict(
        cls,
        data,
    ):

        atoms = [
            Atom(
                item["element"],
                item["x"],
                item["y"],
                item["z"],
            )
            for item in data.get(
                "atoms",
                [],
            )
        ]

        structure = cls(
            atoms=atoms,
            cell=data.get(
                "cell"
            ),
            name=data.get(
                "name",
                "Structure",
            ),
        )

        structure.periodic = data.get(
            "periodic",
            [True, True, True],
        )

        structure.history = data.get(
            "history",
            [],
        )

        return structure

    def copy(self):

        return Structure.from_dict(
            self.to_dict()
        )

    # ============================================================
    # Utilities
    # ============================================================

    @staticmethod
    def vector_length(
        vector,
    ):

        return math.sqrt(
            sum(
                component * component
                for component in vector
            )
        )

    @staticmethod
    def vector_add(
        a,
        b,
    ):

        return [
            a[0] + b[0],
            a[1] + b[1],
            a[2] + b[2],
        ]

    @staticmethod
    def vector_scale(
        vector,
        scale,
    ):

        return [
            component * scale
            for component in vector
        ]

    def _record(
        self,
        operation,
    ):

        self.history.append(
            operation
        )

    # ============================================================
    # Supercell
    # ============================================================

    def make_supercell(
        self,
        nx=1,
        ny=1,
        nz=1,
    ):

        nx = int(nx)
        ny = int(ny)
        nz = int(nz)

        if nx < 1 or ny < 1 or nz < 1:
            raise ValueError(
                "Supercell dimensions must be >= 1."
            )

        old_cell = copy.deepcopy(
            self.cell
        )

        new_atoms = []

        a = old_cell[0]
        b = old_cell[1]
        c = old_cell[2]

        for ix in range(nx):

            for iy in range(ny):

                for iz in range(nz):

                    translation = [
                        ix * a[0]
                        + iy * b[0]
                        + iz * c[0],

                        ix * a[1]
                        + iy * b[1]
                        + iz * c[1],

                        ix * a[2]
                        + iy * b[2]
                        + iz * c[2],
                    ]

                    for atom in self.atoms:

                        new_atoms.append(
                            Atom(
                                atom.element,

                                atom.x
                                + translation[0],

                                atom.y
                                + translation[1],

                                atom.z
                                + translation[2],
                            )
                        )

        self.atoms = new_atoms

        self.cell = [
            self.vector_scale(
                a,
                nx,
            ),
            self.vector_scale(
                b,
                ny,
            ),
            self.vector_scale(
                c,
                nz,
            ),
        ]

        self._record(
            f"Supercell {nx}×{ny}×{nz}"
        )

    # ============================================================
    # Vacuum
    # ============================================================

    def add_vacuum(
        self,
        vacuum,
        direction="z",
    ):

        vacuum = float(vacuum)

        index = {
            "x": 0,
            "y": 1,
            "z": 2,
        }[direction.lower()]

        vector = self.cell[index]

        length = self.vector_length(
            vector
        )

        if length == 0:
            raise ValueError(
                "Selected lattice vector has zero length."
            )

        factor = (
            length + vacuum
        ) / length

        self.cell[index] = (
            self.vector_scale(
                vector,
                factor,
            )
        )

        self._record(
            f"Added {vacuum:.3f} Å vacuum "
            f"along {direction}"
        )

    # ============================================================
    # Strain
    # ============================================================

    def apply_strain(
        self,
        percentage,
        direction="biaxial",
    ):

        factor = (
            1.0
            + float(percentage) / 100.0
        )

        direction = direction.lower()

        if direction == "biaxial":

            for i in range(2):

                self.cell[i] = (
                    self.vector_scale(
                        self.cell[i],
                        factor,
                    )
                )

                for atom in self.atoms:

                    if i == 0:
                        atom.x *= factor
                    elif i == 1:
                        atom.y *= factor

        elif direction == "uniaxial-x":

            self.cell[0] = (
                self.vector_scale(
                    self.cell[0],
                    factor,
                )
            )

            for atom in self.atoms:
                atom.x *= factor

        elif direction == "uniaxial-y":

            self.cell[1] = (
                self.vector_scale(
                    self.cell[1],
                    factor,
                )
            )

            for atom in self.atoms:
                atom.y *= factor

        elif direction == "uniaxial-z":

            self.cell[2] = (
                self.vector_scale(
                    self.cell[2],
                    factor,
                )
            )

            for atom in self.atoms:
                atom.z *= factor

        else:

            raise ValueError(
                "Unknown strain direction."
            )

        self._record(
            f"{percentage:+.2f}% "
            f"{direction} strain"
        )

    # ============================================================
    # Slab
    # ============================================================

    def make_slab(
        self,
        layers=1,
        direction="z",
        vacuum=15.0,
    ):

        direction = direction.lower()

        if direction not in (
            "x",
            "y",
            "z",
        ):

            raise ValueError(
                "Slab direction must be x, y or z."
            )

        axis = {
            "x": 0,
            "y": 1,
            "z": 2,
        }[direction]

        layers = int(layers)

        if layers < 1:
            raise ValueError(
                "Number of layers must be >= 1."
            )

        # Simple slab construction:
        # repeat along the chosen axis.
        if layers > 1:

            dims = [1, 1, 1]

            dims[axis] = layers

            self.make_supercell(
                *dims
            )

        self.add_vacuum(
            vacuum,
            direction,
        )

        self._record(
            f"Slab: {layers} layers "
            f"along {direction}"
        )

    # ============================================================
    # Translate
    # ============================================================

    def translate(
        self,
        dx,
        dy,
        dz,
    ):

        for atom in self.atoms:

            atom.x += float(dx)
            atom.y += float(dy)
            atom.z += float(dz)

        self._record(
            f"Translated by "
            f"({dx}, {dy}, {dz}) Å"
        )

    # ============================================================
    # Duplicate
    # ============================================================

    def duplicate(
        self,
        other,
        translation=(0, 0, 0),
    ):

        dx, dy, dz = translation

        for atom in other.atoms:

            self.atoms.append(
                Atom(
                    atom.element,
                    atom.x + dx,
                    atom.y + dy,
                    atom.z + dz,
                )
            )

        self._record(
            f"Duplicated structure "
            f"'{other.name}'"
        )

    # ============================================================
    # Heterostructure
    # ============================================================

    def stack(
        self,
        other,
        gap=3.0,
        axis="z",
        other_repetitions=(1, 1, 1),
    ):

        other = other.copy()

        other.make_supercell(
            *other_repetitions
        )

        axis = axis.lower()

        axis_index = {
            "x": 0,
            "y": 1,
            "z": 2,
        }[axis]

        self_max = max(
            getattr(
                atom,
                axis,
            )
            for atom in self.atoms
        )

        other_min = min(
            getattr(
                atom,
                axis,
            )
            for atom in other.atoms
        )

        translation = (
            self_max
            + float(gap)
            - other_min
        )

        if axis == "x":

            other.translate(
                translation,
                0,
                0,
            )

        elif axis == "y":

            other.translate(
                0,
                translation,
                0,
            )

        else:

            other.translate(
                0,
                0,
                translation,
            )

        self.duplicate(
            other
        )

        # Increase cell dimension along stacking direction.
        other_cell_vector = other.cell[
            axis_index
        ]

        self.cell[axis_index] = (
            self.vector_add(
                self.cell[axis_index],
                other_cell_vector,
            )
        )

        self._record(
            f"Stacked '{other.name}' "
            f"with {gap:.2f} Å gap "
            f"along {axis}"
        )

    # ============================================================
    # Nanotube
    # ============================================================

    def make_nanotube(
        self,
        n,
        m,
    ):

        """
        Roll a 2D sheet into a nanotube.

        The first two lattice vectors are assumed to define
        the 2D sheet plane.

        n,m are the chiral indices.
        """

        n = int(n)
        m = int(m)

        if n < 0 or m < 0:
            raise ValueError(
                "Nanotube indices must be non-negative."
            )

        if n == 0 and m == 0:
            raise ValueError(
                "Nanotube indices cannot both be zero."
            )

        a = self.cell[0]
        b = self.cell[1]

        # Chiral vector
        cvec = [
            n * a[0] + m * b[0],
            n * a[1] + m * b[1],
            n * a[2] + m * b[2],
        ]

        circumference = (
            self.vector_length(cvec)
        )

        radius = (
            circumference
            / (2.0 * math.pi)
        )

        e_c = [
            component / circumference
            for component in cvec
        ]

        # Find a lattice translation approximately
        # perpendicular to the chiral vector.
        best = None

        for p in range(
            -20,
            21,
        ):

            for q in range(
                -20,
                21,
            ):

                if p == 0 and q == 0:
                    continue

                tvec = [
                    p * a[0] + q * b[0],
                    p * a[1] + q * b[1],
                    p * a[2] + q * b[2],
                ]

                dot = sum(
                    cvec[i] * tvec[i]
                    for i in range(3)
                )

                tlen = self.vector_length(
                    tvec
                )

                score = (
                    abs(dot)
                    / (
                        circumference
                        * tlen
                    )
                    if tlen
                    else 999
                )

                if best is None or score < best[0]:

                    best = (
                        score,
                        tvec,
                    )

        if best is None:
            raise ValueError(
                "Could not construct nanotube translation."
            )

        tvec = best[1]

        tlength = self.vector_length(
            tvec
        )

        e_t = [
            component / tlength
            for component in tvec
        ]

        # Build enough translations to cover
        # one nanotube unit.
        max_rep = (
            abs(n)
            + abs(m)
            + 3
        )

        generated = []

        for p in range(
            -max_rep,
            max_rep + 1,
        ):

            for q in range(
                -max_rep,
                max_rep + 1,
            ):

                translation = [
                    p * a[0] + q * b[0],
                    p * a[1] + q * b[1],
                    p * a[2] + q * b[2],
                ]

                for atom in self.atoms:

                    r = [
                        atom.x + translation[0],
                        atom.y + translation[1],
                        atom.z + translation[2],
                    ]

                    u = sum(
                        r[i] * e_c[i]
                        for i in range(3)
                    )

                    v = sum(
                        r[i] * e_t[i]
                        for i in range(3)
                    )

                    u %= circumference

                    if (
                        -0.001
                        <= v
                        <= tlength + 0.001
                    ):

                        theta = (
                            2.0
                            * math.pi
                            * u
                            / circumference
                        )

                        generated.append(
                            Atom(
                                atom.element,

                                radius
                                * math.cos(theta),

                                radius
                                * math.sin(theta),

                                v,
                            )
                        )

        if not generated:

            raise ValueError(
                "Nanotube generation produced no atoms."
            )

        self.atoms = generated

        self.cell = [
            [
                2 * math.pi * radius,
                0,
                0,
            ],
            [
                0,
                tlength,
                0,
            ],
            [
                0,
                0,
                20.0,
            ],
        ]

        self.periodic = [
            True,
            True,
            False,
        ]

        self._record(
            f"Nanotube ({n},{m})"
        )

    # ============================================================
    # File import
    # ============================================================

    @classmethod
    def from_xyz(
        cls,
        path,
    ):

        path = Path(path)

        lines = path.read_text().splitlines()

        if not lines:
            raise ValueError(
                "Empty XYZ file."
            )

        count = int(
            lines[0].strip()
        )

        atoms = []

        for line in lines[2:2 + count]:

            parts = line.split()

            if len(parts) < 4:
                continue

            atoms.append(
                Atom(
                    parts[0],
                    parts[1],
                    parts[2],
                    parts[3],
                )
            )

        return cls(
            atoms=atoms,
            name=path.stem,
        )

    @classmethod
    def from_poscar(
        cls,
        path,
    ):

        path = Path(path)

        lines = [
            line.strip()
            for line in path.read_text().splitlines()
            if line.strip()
        ]

        if len(lines) < 8:
            raise ValueError(
                "Invalid POSCAR."
            )

        scale = float(
            lines[1]
        )

        cell = []

        for i in range(2, 5):

            vector = [
                float(x)
                for x in lines[i].split()
            ]

            cell.append(
                [
                    component * scale
                    for component in vector
                ]
            )

        elements = lines[5].split()

        counts = [
            int(x)
            for x in lines[6].split()
        ]

        index = 7

        if lines[index].lower().startswith(
            "s"
        ):

            index += 1

        coordinate_mode = (
            lines[index].lower()
        )

        index += 1

        atoms = []

        for element, count in zip(
            elements,
            counts,
        ):

            for _ in range(count):

                coords = [
                    float(x)
                    for x in lines[index].split()[:3]
                ]

                index += 1

                if coordinate_mode.startswith(
                    "d"
                ):

                    x = (
                        coords[0] * cell[0][0]
                        + coords[1] * cell[1][0]
                        + coords[2] * cell[2][0]
                    )

                    y = (
                        coords[0] * cell[0][1]
                        + coords[1] * cell[1][1]
                        + coords[2] * cell[2][1]
                    )

                    z = (
                        coords[0] * cell[0][2]
                        + coords[1] * cell[1][2]
                        + coords[2] * cell[2][2]
                    )

                else:

                    x, y, z = coords

                atoms.append(
                    Atom(
                        element,
                        x,
                        y,
                        z,
                    )
                )

        return cls(
            atoms=atoms,
            cell=cell,
            name=path.stem,
        )
