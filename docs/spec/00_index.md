# AudioMason2 - Specification Index (Authoritative)

Specification Version: 1.1.20

AudioMason2 maintains a layered specification to improve auditability without losing detail.

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
