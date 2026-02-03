# badguys noop allowed with -n (but promotion still blocks NOOP)
FILES = [
    "badguys/tmp/noop_allowed.txt",
]

# Intentionally do nothing. With -n, scope NOOP is allowed, but promotion should still fail PROMOTION:NOOP.
