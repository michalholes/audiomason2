# issue 128: author loop cycle + expr dynamic indexing

- effective_author step replaced with cycle-based loop:
  init_author_loop -> effective_author_item -> store_author_item -> author_loop_check
  loop repeats per selected author using index in $.state.vars.author_loop.index
- effective_author_item prefill uses selected_author_label_list[index] for correct per-author prompt
- store_author_item increments index using arithmetic expr (index + 1)
- author_loop_check edges use len() comparison to stop loop after all authors
- expr_parser: dynamic path indexing expr[path_expr] now supported (PathNode stops at dynamic bracket, _parse_postfix wraps in IndexNode)
- expr_eval/expr_parser/expr_tokens: arithmetic operators +,-,*,/,//,% and postfix indexing (Bot-A)
- source_v1.py: new primitives file (source.build_catalog, source.normalize_label) - registered, not yet used in flow
- Updated test assertions: effective_author -> effective_author_item in 6 test files
