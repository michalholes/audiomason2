metadata_openlibrary boundary convergence

- introduces explicit request payloads and a single execute_request authority for metadata operations
- keeps validate_author, validate_book, lookup_book, and fetch as thin wrappers over the canonical request flow
- adds phase1 validation request support for immediate import cutover wiring
- preserves openlibrary-primary validation and google-books fallback behavior
