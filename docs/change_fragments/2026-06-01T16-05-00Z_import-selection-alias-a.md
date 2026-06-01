# import selection alias a

- Fixed selection parsing so `a` is accepted as an alias for `all` in selection expressions.
- This aligns runtime submit validation with CLI prompt text that explicitly instructs users to use `a` for all.
- Updated both expression parsing and v3 empty-discovery validation guard to treat `a` as valid.
