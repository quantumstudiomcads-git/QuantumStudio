# Quantum Studio v0.21 — VolumetricResult contract (E4)

`VolumetricResult` is a Qt-free `ScientificResult` with `values[nx, ny, nz]`, `grid_shape`, row-vector `cell`, Cartesian `origin`, PBC, quantity identity, units, parser diagnostics, and source-hash provenance. Arrays persist in ResultStore compressed NPZ payloads, not project files.

Gaussian cube is the canonical QE artifact. Cube axis increments are read in bohr and converted only for geometry metadata to Å; field values retain QE source units. Values are read in Gaussian cube order and reshaped C-order: z is fastest, then y, then x. Grid points use fractional `(i/nx,j/ny,k/nz)`; the periodic endpoint is omitted. Cartesian coordinates are `origin + fractional @ cell`.

Parser safety: finite values, positive shape, exact voxel count, finite nonzero cell, 16,777,216 voxel and 512 MiB artifact limits. Malformed data is parse failure, never padded or silently reshaped.

Slices are axis-aligned XY/XZ/YZ nearest grid planes; fractional 1 maps to periodic 0. Profiles are arithmetic planar averages on the uniform fractional grid and retain both fractional coordinate and lattice-vector distance in Å. Macroscopic averaging is deferred to E5. NPZ exports exact values/metadata; CSV exports slices/profiles only.

Signed spin density stays signed. Color scaling, clipping, colormap, and view position are Analyze state only. Noncollinear/SOC vector magnetization fields are intentionally not represented by this scalar contract.

