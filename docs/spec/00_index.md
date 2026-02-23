# AudioMason2 - Specification Index (Authoritative)

Specification Version: 1.1.22

AudioMason2 maintains a layered specification to improve auditability without losing detail.

Normative authority:
- The only authoritative specification is the layered set under docs/spec/.
- docs/specification.md is an overview stub and is not normative.

Specification versioning and change log:
- Start at version 1.0.0.
- Every change to the specification MUST increment the patch number by +1.
- Every change delivered by a patch MUST be recorded in docs/changes.md.
- Each change entry in docs/changes.md MUST start with an ISO 8601 timestamp.

Layers:
- ARCH: docs/spec/10_architecture.md
- WIRE: docs/spec/20_wire_contracts.md
- LAYOUT: docs/spec/30_implementation_bindings.md

Precedence (in case of conflict):
1. AUDIOMASON2_PROJECT_CONTRACT.md
2. ARCH (architecture)
3. WIRE (wire contracts)
4. LAYOUT (implementation bindings)

If WIRE and LAYOUT conflict, WIRE is authoritative for externally visible behavior.
LAYOUT defines the required implementation binding for the chosen behavior.
