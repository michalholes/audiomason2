issue 127
- add source.resolve_selection DSL primitive to data_v1.py resolving selection_expr ("all", "1", "1,2", "1-3") against an ordered_ids list
- register source.resolve_selection in NON_INTERACTIVE_IDS and execute_non_prompt dispatch in primitives/__init__.py
- add data.filter condition_expr support: per-item expression evaluation via eval_expr_ref with $.inputs.item context
- add data.map value_expr support: per-item expression evaluation via eval_expr_ref with $.inputs.item context
- extend data_v1.execute signature with optional state parameter for expr evaluation context
- add resolve_author_ids and resolve_book_ids steps to default_wizard_v3_source.json using source.resolve_selection primitive
- update flow edges: select_authors->resolve_author_ids->select_books->resolve_book_ids->plan_preview_batch
- update acceptance and spec-alignment tests to include new auto-advance steps in expected trace
