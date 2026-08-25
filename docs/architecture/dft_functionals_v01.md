# DFT functionals v0.1

Functional families are distinct from QE identifiers: PZ, PBE, PW91, BLYP, HSE06 (QE HSE, 25% EXX, 0.106 bohr^-1 screening), and B3LYP (20% EXX) are registry-controlled. GGA is never emitted as input_dft. Hybrid phonon/EPW and current NSCF-dependent workflows are blocked; no PBE fallback occurs.

## C9Y pseudopotential compatibility

Functional choice and pseudopotential identity are separate scientific inputs. QE generation retains legacy element-to-filename assignments and accepts optional library, XC, relativity and SHA-256 metadata. Local UPF metadata is validated before generation when a source path is supplied; generated manifests retain available per-species provenance, and execution preflight rejects a source whose SHA-256 changed. Accuracy presets never replace a selected pseudo set.

## C9Z direct hybrid bands

For HSE06 and B3LYP Bands, Quantum Studio uses one hybrid SCF `pw.x` task plus `bands.x`; it does not generate the ordinary semilocal `calculation=bands` task. The SCF contains `ADDITIONAL_K_POINTS crystal` with the deterministic interpolated visible band path. This follows QE’s `additional_kpoints` implementation: the input card points carry zero weight and QE internally creates the required EXX closure `k + (i/nqx1, j/nqx2, k/nqx3)`. Quantum Studio records both visible and QE-created support points in task provenance, but intentionally does not duplicate support points in the card.

The Calculate functional dialog selects LDA/PZ, GGA/PBE/PW91/BLYP, or Hybrid/HSE06/B3LYP through the Qt-free registry. Hybrid controls persist `xc_functional`, EXX fraction, screening only for HSE06, EXX q mesh, ACE, divergence treatment, and standard/custom status. A compact pseudo table imports local UPFs through the C9Y parser and persists rich per-element identity; no pseudo is silently selected or downloaded.
