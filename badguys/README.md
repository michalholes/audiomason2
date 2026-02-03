# badguys

Badguys je smoke test suite pre AM Patch Runner.

Spustenie (bez commitov):
  python3 badguys/run_suite.py --commit-limit 0

Spustenie (s commit testom):
  python3 badguys/run_suite.py --commit-limit 1

Logy:
- centralny log: patches/badguys_<run_id>.log
- per-test logy: patches/badguys_logs/<run_id>__<test_name>.log

Testy:
- definicie su v badguys/tests/ ako samostatne subory test_*.py
- include/exclude sa da pouzit cez config alebo CLI

commit_limit:
- ak je vybranych viac commit testov nez commit_limit, suite failne s jasnym dovodom a navodom
