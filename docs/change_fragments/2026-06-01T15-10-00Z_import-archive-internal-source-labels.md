# import phase1 archive internal source labels

- Updated PHASE 1 bundle projection to derive author/book pairs from archive internal audio paths instead of defaulting author labels to the archive filename.
- Added deterministic wrapper-folder handling: when archive entries are nested under a folder matching the archive stem, that wrapper is ignored for author/book pairing.
- Kept fallback behavior deterministic when archive introspection is unavailable, but now uses archive stem labels (for example `sp`) instead of extension-bearing archive names (for example `sp.rar`).
- Added root-audio fallback labeling from audio filename stem, so single files stored directly in archive root do not collapse to generic archive stem labels.
- This prevents `effective_author_item` suggestions from inheriting raw archive filenames in common `.rar` source flows.
