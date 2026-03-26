# PM_SPEC

AUTHORITATIVE -- AudioMason2 Status: active Version: v1.0

HARD: This document is the controller-only PM contract for authority-phase work.
HARD: Implementation patch authoring, repair workflow, patch delivery, and implementation evidence remain exclusively in docs/am_patch_instructions.md.
HARD: Shared norms MUST NOT be duplicated here if they are already authoritative in RC or AUDIOMASON2_PROJECT_CONTRACT.md.

SPEC CONTEXT
PM version used: <PM_VERSION>

## Authority pre-flight
1. A valid authority target scope MUST be identified.
2. The authoritative workspace corpus MUST be inspected before authority planning.
3. Discovery resolver evidence MUST exist before plan negotiation.

## Authority freeze
1. AUTHORITY FREEZE MUST be emitted before any authority patch is authored.
2. AUTHORITY FREEZE MUST preserve approved P1..Pn exactly.
3. Every authority patch MUST be checked against the approved AUTHORITY FREEZE before delivery.

## Authority patch contract
1. Authority patching MAY modify only the authority files named in the authority FILES MANIFEST.
2. Every authority patch touching docs/ MUST require one docs/change_fragments/ fragment.
3. Hidden scope expansion is forbidden.

## Authority validation
1. AUTHORITY VALIDATION MUST verify freeze-to-spec conformance.
2. AUTHORITY VALIDATION MUST verify resolver prerequisites, artifact integrity, and no-drift behavior.
3. Implementation freeze delivery is forbidden until AUTHORITY VALIDATION passes.

## Drift lock
1. If authority patching reveals missing scope, the process MUST return to plan negotiation.
2. Silent additions are forbidden.
