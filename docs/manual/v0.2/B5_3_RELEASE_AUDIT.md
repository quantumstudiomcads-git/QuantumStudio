# B5.3 release audit

## A. Baseline

- Product: Quantum Studio 0.2.0 Beta User Manual.
- Manual source baseline: B5.2 documentation commit
  `76304a0b415defcfb3439f4a2766f8274378d6c6`.
- Accepted application: r28, built from
  `42bd7e1ebc7e01e3149b830da67de0fc1638214d`.
- r28 executable SHA-256:
  `1122712B403A6BC885EAC4CA402BEBB384F4A2F6F6D75D1A28CF8092516E1749`.

## B. r28 verification

The executable exists at the recorded r28 location and its SHA-256 matched the
accepted value before this documentation work. B5.3 did not rebuild, alter, or
otherwise replace r28.

## C–E. Screenshot inventory, captures, and unresolved items

B5.2 contained 19 planned B5.3 screenshot markers. The count reconciled
to 19. Captured and inserted screenshots: **0**. No current-product image was
fabricated.

The following manual states remain pending:

1. First launch / Project Hub — no native r28 capture surface.
2. Project creation — no native r28 capture surface.
3. Builder overview — no native r28 capture surface.
4. Structure operations — no native r28 capture surface.
5. Measurements — no native r28 capture surface.
6. Heterostructure construction — no native r28 capture surface.
7. Moiré construction — no native r28 capture surface.
8. Device Builder — no native capture surface and no legitimate paid
   entitlement was available.
9. Calculate overview — no native r28 capture surface.
10. Electronic settings — no native r28 capture surface.
11. Vibrational selection — no native r28 capture surface.
12. Pseudopotential selection — no native r28 capture surface.
13. Runtime/tool detection — no native r28 capture surface.
14. Results — no non-private parsed r28 result was available.
15. Analyze result browser — no non-private parsed r28 result was available.
16. Analyze comparison — no non-private parsed r28 result was available.
17. Export — no native r28 capture surface.
18. Licensing status — no native r28 capture surface.
19. Help / diagnostics — no native r28 capture surface.

Each original marker is now an explicit `Screenshot pending` notice. The
per-section status is in [B5_3_VISUAL_QA.md](B5_3_VISUAL_QA.md).

## F–G. UI/manual discrepancies and corrections

No visual UI claim was made without an r28 inspection. Documentation changes
made during B5.3 are limited to accurate pending-image notices, verified
references, and scientific-notation corrections. In particular, the
heterostructure matching relation now follows the documented row-vector form;
the moiré heuristic is written explicitly; and the Kohn–Sham/DOS notation was
corrected for clarity.

## H–I. References

Twelve primary-paper or official-project reference entries were reviewed:
Kohn–Sham; three Quantum ESPRESSO papers; Quantum ESPRESSO documentation;
Baroni *et al.* DFPT; Wannier90; two EPW papers; EPW documentation; Wannier90
documentation; and BoltzTraP2. The B5.2 bibliographic verification placeholders
were removed. No unverified DOI was added.

## J–K. Equation, notation, and unit QA

The Kohn–Sham, density, DOS, dynamical-matrix, dielectric, heterostructure,
and moiré expressions were reviewed against the manual notation convention.
The B5.3 corrections described above remove an ambiguity; no calculation,
unit conversion, or scientific implementation changed.

## L. Catalogue reconciliation

The release validation rechecks the source catalogue against the calculation
index and reference files. Required accounting remains 29 READY, 17 PARTIAL,
101 PLANNED, 1 EXTERNAL BACKEND REQUIRED, and 148 public intents.
`extinction_coefficient` remains backend-only and is not a public intent.

## M–O. PDF and website package

The print-ready HTML was generated from the versioned Markdown with Python
Markdown 3.7. Chromium headless could not initialize its GPU process in this
sandbox, and WeasyPrint could not load its Windows GObject dependency; the
validated fallback renderer was ReportLab 4.5.1. The PDF has 166 pages, embeds
the manual fonts, has title/author/subject metadata, and was visually inspected
on representative cover, electronic, job/state, and calculation-reference
pages.

The website package preserves 109 public documentation files with an explicit
site-navigation manifest. Source and copied-package internal Markdown link
checks passed. The external release artefacts and their checksums are recorded
in `E:\QuantumStudio-W8\validation\b5_3\reports\B5_3_RELEASE_MANIFEST.md`.
They are deliberately not committed: the repository stores the maintainable
Markdown, styles, and release QA rather than generated binary outputs.

## P–R. Code-change checks and remaining limitation

Only `docs/manual/v0.2/` is changed by B5.3. Production and scientific source
are unchanged. The remaining release blocker is genuine r28 visual verification
and capture from a permitted native application surface.

## S–T. Final release status

**B5.3 PARTIAL — actual r28 native-window screenshots and visual verification
remain unavailable in this execution environment.**
