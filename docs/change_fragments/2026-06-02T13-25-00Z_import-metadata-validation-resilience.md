2026-06-02T13:25:00Z import metadata validation resilience and title language-preservation updates.

- reduced metadata validation fan-out during author loop so PHASE 1 no longer performs
  network lookups for every selected book before the title loop starts;
- added transient retry handling for timeout/handshake/429 failures in import metadata
  boundary job execution;
- normalized metadata cache keys and persisted successful author/title suggestions across
  runs to stabilize prompt defaults under transient provider outages;
- added deterministic title normalization fallback for labels like `Surname Initial
  Title...` so raw archive-style prefixes do not leak into `effective_title_item`;
- prevented automatic cross-language title rewrites by keeping source-language titles when
  suggestion/token overlap indicates a translation rather than normalization.
