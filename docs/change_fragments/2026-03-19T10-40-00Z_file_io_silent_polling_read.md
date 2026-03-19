2026-03-19T10:40:00Z

File I/O open_read and resolve_path now support an explicit silent polling read opt-in
for internal self-inspection loops so file-backed reads keep the same root-jail and
exception behavior without emitting low-level file_io diagnostics or summary logs
for that specific polling read.
