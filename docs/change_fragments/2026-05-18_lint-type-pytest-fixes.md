# lint, mypy, pytest fixes

- expr_eval.py: lambda -> def for _is_num (ruff E731)
- expr_parser.py: temp var `dyn` before isinstance check to fix mypy assignment type error
- data_v1.py: split long list comprehension (ruff E501)
- source_v1.py: sorted imports (ruff I001)
- pytest.ini: corrected key asyncio_default_test_loop_scope -> asyncio_default_fixture_loop_scope
- pyproject.toml: added asyncio_default_fixture_loop_scope = "session" for consistency
