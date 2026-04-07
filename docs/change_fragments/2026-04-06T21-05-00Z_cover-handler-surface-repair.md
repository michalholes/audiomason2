Issue 109 repair makes the ref-based cover contract canonical. Public path-based
discover/apply methods are demoted to private path helpers, while ref-based
candidate discovery/materialization now performs the real work directly and the
cover tests assert the ref-based surface.
