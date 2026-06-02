2026-06-02T15:40:00Z fix strict mypy issues in plugin code.

- replaced `MetadataAIPlugin.configure()` self-reinitialization with a shared config loader;
- typed the HTTP response handle in the metadata AI plugin so response reads stay non-`Any`;
- normalized `phase1_metadata_flow` validation targets to a typed `set[str]`;
- removed archive entry list redefinition in the file I/O archive service.
