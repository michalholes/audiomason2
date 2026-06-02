2026-06-02T14:25:00Z prefer unrar for RAR listing and unpack fallback.

- updated archive external tool preference for RAR so file listing and unpack choose
  `unrar` before `7z` when both are available;
- keeps `7z` as the fallback backend for non-RAR formats and RAR when `unrar` is not
  available;
- resolves RAR jobs failing with `Unsupported Method` on environments where bundled
  `7z` cannot extract newer RAR methods.
