# 21. Results

A **Result** is parsed scientific output with provenance, not simply a completed
engine process or raw output file. Result provenance records the source request,
execution/task, engine/tool, source paths/hashes, parser context, and relevant
fingerprints.

## Result status

| Status | Meaning |
| --- | --- |
| VALID | Parsed result passed the product's available validity checks. |
| PARTIAL | Some usable result data exists, but scope is incomplete. |
| NOT_CONVERGED | The calculation completed or produced output without satisfying its convergence condition. |
| UNVERIFIED | Result data exists but available verification is incomplete. |
| PARSE_FAILED | Output could not be parsed into the expected Result. |
| STALE | Stored result provenance no longer matches current source fingerprints. |

Engine state and Result status are separate. A COMPLETED task can produce a
NOT_CONVERGED, UNVERIFIED, PARTIAL, PARSE_FAILED, or STALE Result. Conversely,
Analyze is intended to operate on parsed Results, not generic raw engine
directories.

## Interpreting a result

Before trusting a plot or table, review the structure snapshot, calculation
parameters, pseudopotentials, engine/workflow, convergence evidence, parser
status, and Result status. Use provenance when comparing two Results or when
exporting data for external analysis.

> **Screenshot pending:** No non-private, genuinely parsed r28 result was available in the B5.3 environment; no result was fabricated.
