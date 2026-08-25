# Scientific results v0.1

C8B separates process execution state from scientific result status.  Raw artifacts
are parsed by a Qt-free registry into engine-neutral `ScientificResult` records with
`VALID`, `PARTIAL`, `NOT_CONVERGED`, `UNVERIFIED`, `PARSE_FAILED`, or `STALE` status.
Each record carries request/execution/task/engine/tool provenance, parser identity,
source paths, and hashes.  Result IDs are deterministic for unchanged source context.

`ResultStore` persists metadata and compressed NumPy arrays below the C7 execution
history, not in `.qs`.  Changed sources make a stored result stale.  C8B currently
parses conservative QE SCF stdout, bands raw rows, DOS raw rows, and matdyn phonon-DOS
rows.  A readable pw.x output without its convergence marker is `NOT_CONVERGED`, even
if its process exited successfully.  QE total energy is preserved with source Ry and
converted eV values.  No parser shifts energy axes.

PDOS multi-file parsing, pp.x volumetric parsing, relaxation geometry, Wannier `.wout`,
and EPW physics are deliberately deferred pending stable raw contracts/fixtures.  BTP2
and NEGF produce no numerical Results.  Calculate may own parse actions and summaries;
Analyze alone will visualize or interactively interpret Results.

## C8C coverage

C8C adds conservative parsing of final QE relax/vc-relax geometry blocks into immutable native Structure result metadata, bounded projwfc PDOS components, Wannier `.wout` completion/spread summaries, and EPW completion summaries. PDOS channels are never aggregated. pp.x currently writes cube output but has no self-describing cell/grid parser contract in this release, so volumetric Results remain deferred. Results remain backend-side and source-hashed; no plot or Analyze behavior is introduced.
