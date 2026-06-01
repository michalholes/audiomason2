# import mypy strict cleanup

- Fixed `mypy .` assignment errors in PHASE 1 metadata projection by widening temporary
  override source variables to `object | None` before normalization.
- Replaced an inline archive author ranking lambda with a typed key helper to avoid
  `Any` leakage in strict mypy expression checks.
- No runtime behavior changed; this patch only tightens type-safety at conversion boundaries.
