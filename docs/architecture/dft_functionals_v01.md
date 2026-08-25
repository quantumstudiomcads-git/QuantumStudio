# DFT functionals v0.1

Functional families are distinct from QE identifiers: PZ, PBE, PW91, BLYP, HSE06 (QE HSE, 25% EXX, 0.106 bohr^-1 screening), and B3LYP (20% EXX) are registry-controlled. GGA is never emitted as input_dft. Hybrid phonon/EPW and current NSCF-dependent workflows are blocked; no PBE fallback occurs.

## C9Y pseudopotential compatibility

Functional choice and pseudopotential identity are separate scientific inputs. QE generation retains legacy element-to-filename assignments and accepts optional library, XC, relativity and SHA-256 metadata. Local UPF metadata is validated before generation when a source path is supplied; generated manifests retain available per-species provenance, and execution preflight rejects a source whose SHA-256 changed. Accuracy presets never replace a selected pseudo set.
