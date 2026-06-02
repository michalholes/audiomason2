2026-06-02T15:05:00Z fix archive-root source path mapping for phase2 action scoping.

- corrected PHASE 1 archive pair projection so bundle entries without parent scope now
  produce `source_relative_path` as `bundle_rel/entry` instead of only `bundle_rel`;
- prevents PHASE 2 from treating a single-book action as full-archive import when the
  selected source item is a root-level audio file inside an archive;
- eliminates explicit rename count mismatches caused by unintended whole-archive
  expansion for one-book actions.
