2026-04-09T00:00:00Z
Import Phase 1 metadata validation now resolves providers through registry-backed loader authority and an explicit job boundary; import bootstrap no longer relies on plugin.py second-truth helpers or path-based required-plugin loading.
Import cover boundary no longer imports file-io root enums directly; root normalization remains delegated to the import file-io boundary.
