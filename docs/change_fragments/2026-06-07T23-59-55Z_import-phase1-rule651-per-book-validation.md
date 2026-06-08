2026-06-07T23:59:55Z Rule 651 hardening for per-book metadata authority after edits.

- Updated `plugins/import/primitives/phase1_metadata_projection_v1.py` to remove
  first-book-only metadata validation targeting in PHASE 1 projection.
- Author/title edit paths now validate and canonicalize deterministically for
  every selected book instead of collapsing to one representative item.
- Manual per-book override behavior remains authoritative: user-entered values
  still win over canonical suggestions while validation payload is preserved.
