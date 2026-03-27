Title: tighten dsl editor typing cluster surfaces

Summary:
- typed graph ops, node form, capability forms,
  and boot orchestration against the types/ layer
- added compile-time contracts for node ops,
  writes, branch specs, and capability form wiring
- reduced import plugin TypeScript debt
  without changing tsconfig behavior or runtime semantics

Why:
- remove noImplicitAny and ambient contract gaps
  in the v3 dsl editor authoring cluster
- keep types/ as the single compile-time authority
  for shared frontend surfaces
