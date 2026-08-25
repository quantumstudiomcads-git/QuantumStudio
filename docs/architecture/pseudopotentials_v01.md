# Pseudopotentials v0.1

C9Y provides Qt-free local UPF indexing, SHA identity, explicit XC/relativity/type metadata, compatibility (including HSE06→PBE and B3LYP→BLYP semilocal-parent policy), SOC warnings, and maximum whole-set cutoff recommendations. Provider IDs are local/index-based; no files are bundled or downloaded.

## C9Y pseudopotential domain

The Qt-free `backend.pseudopotentials` package reads bounded UPF metadata only; it never loads radial tables. `PseudoPotentialRecord` preserves file SHA-256, normalized XC identity, PP type, relativity, valence, cutoffs and library provenance. A `PseudoSet` is assessed against the request structure snapshot, not the mutable Builder structure.

Installed folders are registered explicitly under stable provider IDs: SSSP Efficiency, SSSP Precision, PseudoDojo, PSLibrary, SG15/ONCV, GBRV, and Local. They are indexed locally only: C9Y neither bundles provider files nor downloads/scrapes a provider website.

Compatibility is explicit: PBE/PBE, PZ/PZ, PW91/PW91 and BLYP/BLYP are direct matches; HSE06/PBE and B3LYP/BLYP are compatible semilocal-parent pairings. Other XC pairings are warnings/errors according to validation policy. SOC prefers fully relativistic records; an all-non-FR set is rejected for a requested SOC run.

Cutoff recommendations are maxima across selected species and never silently alter a request. Pseudopotential selection is independent from Fast/Intermediate/Precise numerical presets. Existing element-to-path mappings remain valid; when a local UPF source is known its metadata and SHA are added to deterministic task/manifest provenance. Generic preflight verifies any manifest SHA/source pair before starting a process.
Provider folders may optionally be indexed through a bounded local JSON manifest. Manifest entries are constrained to the registered root; declared checksum values are verified against the installed UPF, and declared cutoff recommendations are retained. This supports locally installed SSSP Efficiency/Precision packs without network access.

## C9Z Calculate configuration

The Calculate parameter dialog includes an Exchange–Correlation and Pseudopotentials action. It derives species from the request snapshot, uses the C9Y UPF parser for explicit import, displays XC/type/relativity compatibility, retains SHA/source metadata, and offers an explicit recommended-cutoff action. Library downloads and broad pseudo-manager polish remain out of scope.


## C9Q automatic provisioning

C9Q adds the Qt-free `PseudoProvisioner`. It resolves a selected request snapshot's species cache-first, then from a trusted provider package only when absent. Managed files live outside projects and source control at `~/.local/share/QuantumStudio/pseudopotentials/` by default (overridable for tests). Every selected UPF is inspected, compatibility-checked, SHA-256 fingerprinted and stored atomically only after archive checksum and UPF validation.

The initial automatic PBE/HSE source is pinned SSSP 1.3.0 PBE Efficiency by default, with SSSP Precision available as an explicit policy. HSE06 deliberately reuses PBE semilocal-parent pseudopotentials. B3LYP, PZ, and PW91 require a configured provider supporting BLYP, PZ, or PW91 respectively; PBE is never silently substituted. SOC selection prefers fully relativistic records. Existing explicit assignments remain Manual and are never replaced by a preset.

Providers are HTTPS allowlisted. Packages are size-bounded, checksum-checked where provider metadata supplies one, extracted only through a safe member filter, and installed through a staging directory plus atomic move. Offline cache hits remain usable; a cache miss returns a typed, actionable error. Automated tests inject local transport payloads and never use a provider network endpoint.
