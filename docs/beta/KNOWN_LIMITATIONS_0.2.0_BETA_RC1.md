# Known Limitations — Quantum Studio 0.2.0 Beta RC1

- EPC, Eliashberg and superconducting Tc remain `VALIDATED_UNCONVERGED`; final mesh/band validation is deferred.
- Silicon optical spectral convergence remains `VALIDATED_UNCONVERGED`; corrected-grid evidence is preserved but not promoted to READY.
- Optical Conductivity is `IMPLEMENTED_UNVALIDATED`; derived optical observables inherit the parent dielectric validation status.
- Metallic, spin-polarized, SOC/noncollinear optical routes require further numerical validation.
- Some of the 147 catalogue entries remain planned, partial, unsupported, or unvalidated.
- This independent-particle optical workflow does not include excitonic, quasiparticle, or other many-body corrections unless explicitly stated by a future engine.
- Windows/WSL packaging is deferred.
- Final Quantum Studio licensing and Engine Pack redistribution terms remain `LEGAL_TEXT_PENDING_REVIEW`.
- The RC was built from a dirty development worktree and is marked `DIRTY_BUILD`; a release build must be regenerated from a committed clean source tree.
