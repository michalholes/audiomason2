2026-03-19T00:20:00Z
Import PROCESS processed-registry fallback selection now rejects ambiguous duplicate
job_requests paths across registered resolvers and only picks a legacy/manual
candidate when the job metadata uniquely matches that candidate. Detached runtime
bootstrap remains authoritative, and same-process multi-resolver collisions no
longer write success-only registry updates into the first matching resolver.
