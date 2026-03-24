(() => {
	const W = window;
	const H = W.AM2EditorHTTP;

	const stableGraph =
		W.AM2WDGraphStable && W.AM2WDGraphStable.stableGraph
			? W.AM2WDGraphStable.stableGraph
			: () => ({ version: 1, nodes: [], edges: [], entry: null });

	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	function _summarizeWhen(whenVal) {
		if (whenVal === null || whenVal === undefined) return "<unconditional>";
		if (typeof whenVal === "boolean") return whenVal ? "true" : "false";
		if (typeof whenVal === "object") {
			const op = whenVal.op;
			const path = whenVal.path;
			if (typeof op === "string" && op && typeof path === "string" && path) {
				if ("value" in whenVal) {
					return op + ":" + path + "=" + String(whenVal.value);
				}
				return op + ":" + path;
			}
			if (typeof op === "string" && op) return op;
		}
		return "<cond>";
	}

	let _prefixesCache = null;
	let _editState = { from: null, outgoingIndex: null };
	async function _getPathPrefixes() {
		if (_prefixesCache) return _prefixesCache;
		if (!H || !H.requestJSON) {
			_prefixesCache = ["cfg.defaults."];
			return _prefixesCache;
		}
		const out = await H.requestJSON("/import/ui/transition-condition-prefixes");
		if (!out.ok) {
			_prefixesCache = ["cfg.defaults."];
			return _prefixesCache;
		}
		const items = out.data && out.data.items ? out.data.items : [];
		_prefixesCache = (Array.isArray(items) ? items : []).map((x) =>
			String(x || ""),
		);
		if (!_prefixesCache.length) _prefixesCache = ["cfg.defaults."];
		return _prefixesCache;
	}

	function renderTransitions(opts) {
		const mount = opts && opts.mount;
		const el = (opts && opts.el) || (() => {});
		const text = (opts && opts.text) || (() => {});
		const state = (opts && opts.state) || {};
		if (!mount) return;

		clear(mount);

		const wd = state.getWizardDraft ? state.getWizardDraft() : {};
		const g = stableGraph(wd);
		const selected = state.getSelectedStepId ? state.getSelectedStepId() : null;
		const nodes = Array.isArray(g.nodes) ? g.nodes : [];
		const edges = Array.isArray(g.edges) ? g.edges : [];

		const panel = el("div", "flowTransPanel");

		const body = el("div", "flowTransBody");
		panel.appendChild(body);
		mount.appendChild(panel);

		if (!selected) {
			body.appendChild(
				text("div", "flowTransEmpty", "Select a step to edit transitions."),
			);
			return;
		}

		const outgoing = edges.filter(
			(e) => String(e.from_step_id || "") === String(selected),
		);
		const outgoingWithIndex = outgoing.map((e, i) => ({
			edge: e,
			outgoingIndex: i,
		}));

		const addWrap = el("div", "flowTransAdd");
		const toSel = el("select", "flowTransSelect");
		nodes.forEach((sid) => {
			const opt = el("option", "");
			opt.value = String(sid || "");
			opt.textContent = String(sid || "");
			toSel.appendChild(opt);
		});
		const prio = el("input", "flowTransPrio");
		prio.type = "number";
		prio.value = "0";
		prio.min = "-99999";
		prio.max = "99999";
		const condType = el("select", "flowTransSelect");
		[
			{ id: "unconditional", label: "Unconditional" },
			{ id: "true", label: "Always true" },
			{ id: "false", label: "Always false" },
			{ id: "eq", label: "Equals" },
			{ id: "neq", label: "Not equals" },
			{ id: "exists", label: "Exists" },
			{ id: "not_exists", label: "Not exists" },
		].forEach((it) => {
			const opt = el("option", "");
			opt.value = it.id;
			opt.textContent = it.label;
			condType.appendChild(opt);
		});

		const pathPrefix = el("select", "flowTransSelect");
		const pathRest = el("input", "flowTransWhen");
		pathRest.type = "text";
		pathRest.placeholder = "path";

		const val = el("input", "flowTransWhen");
		val.type = "text";
		val.placeholder = "value";

		function needsPath(t) {
			return t === "eq" || t === "neq" || t === "exists" || t === "not_exists";
		}

		function needsValue(t) {
			return t === "eq" || t === "neq";
		}

		function updateCondUi() {
			const t = String(condType.value || "unconditional");
			const showPath = needsPath(t);
			const showValue = needsValue(t);
			pathPrefix.disabled = !showPath;
			pathRest.disabled = !showPath;
			val.disabled = !showValue;
			if (!showPath) {
				pathRest.value = "";
			}
			if (!showValue) {
				val.value = "";
			}
		}
		const btnAdd = text("button", "btn btnSmall", "Add");
		btnAdd.type = "button";

		btnAdd.addEventListener("click", () => {
			const toId = String(toSel.value || "");
			const p = Number(prio.value || 0);
			const t = String(condType.value || "unconditional");
			let whenVal = null;

			if (t === "true") whenVal = true;
			else if (t === "false") whenVal = false;
			else if (t === "unconditional") whenVal = null;
			else {
				const prefix = String(pathPrefix.value || "");
				const rest = String(pathRest.value || "").trim();
				if (!prefix || !rest) {
					window.alert("Condition path is required");
					return;
				}
				const fullPath = prefix + rest;
				if (t === "exists") whenVal = { op: "exists", path: fullPath };
				else if (t === "not_exists")
					whenVal = { op: "not_exists", path: fullPath };
				else if (t === "eq" || t === "neq") {
					const v = String(val.value || "");
					whenVal = { op: t, path: fullPath, value: v };
				}
			}
			state.addEdge && state.addEdge(String(selected), toId, p, whenVal);
		});

		addWrap.appendChild(toSel);
		addWrap.appendChild(prio);
		addWrap.appendChild(condType);
		addWrap.appendChild(pathPrefix);
		addWrap.appendChild(pathRest);
		addWrap.appendChild(val);
		addWrap.appendChild(btnAdd);
		body.appendChild(addWrap);

		_getPathPrefixes().then((prefixes) => {
			clear(pathPrefix);
			(Array.isArray(prefixes) ? prefixes : []).forEach((pfx) => {
				const opt = el("option", "");
				opt.value = String(pfx || "");
				opt.textContent = String(pfx || "");
				pathPrefix.appendChild(opt);
			});
			updateCondUi();
		});

		condType.addEventListener("change", () => {
			updateCondUi();
		});

		updateCondUi();

		if (!outgoingWithIndex.length) {
			body.appendChild(
				text("div", "flowTransEmpty", "No outgoing transitions."),
			);
			return;
		}

		const table = el("div", "flowTransTable");
		body.appendChild(table);

		function rerender() {
			renderTransitions(opts);
		}

		function buildWhenValue(t, prefix, rest, v) {
			if (t === "true") return true;
			if (t === "false") return false;
			if (t === "unconditional") return null;
			const r = String(rest || "").trim();
			if (!prefix || !r) return null;
			const fullPath = String(prefix) + r;
			if (t === "exists") return { op: "exists", path: fullPath };
			if (t === "not_exists") return { op: "not_exists", path: fullPath };
			if (t === "eq" || t === "neq") {
				return { op: t, path: fullPath, value: String(v || "") };
			}
			return null;
		}

		outgoingWithIndex
			.slice(0)
			.sort(
				(a, b) => Number(a.edge.priority || 0) - Number(b.edge.priority || 0),
			)
			.forEach((e) => {
				const edge = e.edge;
				const row = el("div", "flowTransRow");

				const isEditing =
					_editState &&
					String(_editState.from || "") === String(selected) &&
					Number(_editState.outgoingIndex || -1) ===
						Number(e.outgoingIndex || -2);

				if (!isEditing) {
					row.appendChild(
						text("div", "flowTransCellPri", String(edge.priority || 0)),
					);
					row.appendChild(
						text("div", "flowTransTo", String(edge.to_step_id || "")),
					);
					row.appendChild(
						text("div", "flowTransMeta", _summarizeWhen(edge.when)),
					);

					const btnUp = text("button", "btn btnSmall", "Up");
					btnUp.type = "button";
					btnUp.addEventListener("click", () => {
						state.moveEdge &&
							state.moveEdge(
								String(selected),
								Number(e.outgoingIndex || 0),
								-1,
							);
					});

					const btnDown = text("button", "btn btnSmall", "Down");
					btnDown.type = "button";
					btnDown.addEventListener("click", () => {
						state.moveEdge &&
							state.moveEdge(String(selected), Number(e.outgoingIndex || 0), 1);
					});

					const btnEdit = text("button", "btn btnSmall", "Edit");
					btnEdit.type = "button";
					btnEdit.addEventListener("click", () => {
						_editState = {
							from: String(selected),
							outgoingIndex: Number(e.outgoingIndex || 0),
						};
						rerender();
					});

					const btnDel = text("button", "btn btnSmall", "Remove");
					btnDel.type = "button";
					btnDel.addEventListener("click", () => {
						state.removeEdge &&
							state.removeEdge(String(selected), Number(e.outgoingIndex || 0));
					});

					row.appendChild(btnUp);
					row.appendChild(btnDown);
					row.appendChild(btnEdit);
					row.appendChild(btnDel);
					table.appendChild(row);
					return;
				}

				// Edit mode
				const toSelE = el("select", "flowTransSelect");
				nodes.forEach((sid) => {
					const opt = el("option", "");
					opt.value = String(sid || "");
					opt.textContent = String(sid || "");
					toSelE.appendChild(opt);
				});
				toSelE.value = String(edge.to_step_id || "");

				const prioE = el("input", "flowTransPrio");
				prioE.type = "number";
				prioE.min = "-99999";
				prioE.max = "99999";
				prioE.value = String(edge.priority || 0);

				const condTypeE = el("select", "flowTransSelect");
				[
					{ id: "unconditional", label: "Unconditional" },
					{ id: "true", label: "Always true" },
					{ id: "false", label: "Always false" },
					{ id: "eq", label: "Equals" },
					{ id: "neq", label: "Not equals" },
					{ id: "exists", label: "Exists" },
					{ id: "not_exists", label: "Not exists" },
				].forEach((it) => {
					const opt = el("option", "");
					opt.value = it.id;
					opt.textContent = it.label;
					condTypeE.appendChild(opt);
				});

				const pathPrefixE = el("select", "flowTransSelect");
				const pathRestE = el("input", "flowTransWhen");
				pathRestE.type = "text";
				pathRestE.placeholder = "path";
				const valE = el("input", "flowTransWhen");
				valE.type = "text";
				valE.placeholder = "value";

				function initFromWhen() {
					const w = edge.when;
					if (w === null || w === undefined) {
						condTypeE.value = "unconditional";
						return;
					}
					if (w === true) {
						condTypeE.value = "true";
						return;
					}
					if (w === false) {
						condTypeE.value = "false";
						return;
					}
					if (typeof w === "object" && w && typeof w.op === "string") {
						condTypeE.value = String(w.op);
						const path = typeof w.path === "string" ? w.path : "";
						const prefixes = Array.from(pathPrefixE.options).map(
							(o) => o.value,
						);
						const match = prefixes.find((p) => path.startsWith(p));
						if (match) {
							pathPrefixE.value = match;
							pathRestE.value = path.slice(match.length);
						} else {
							pathRestE.value = path;
						}
						if ("value" in w) valE.value = String(w.value);
					}
				}

				function needsPath(t) {
					return (
						t === "eq" || t === "neq" || t === "exists" || t === "not_exists"
					);
				}
				function needsValue(t) {
					return t === "eq" || t === "neq";
				}
				function updateCondUiE() {
					const t = String(condTypeE.value || "unconditional");
					const showPath = needsPath(t);
					const showValue = needsValue(t);
					pathPrefixE.disabled = !showPath;
					pathRestE.disabled = !showPath;
					valE.disabled = !showValue;
					if (!showPath) pathRestE.value = "";
					if (!showValue) valE.value = "";
				}

				condTypeE.addEventListener("change", updateCondUiE);

				_getPathPrefixes().then((prefixes) => {
					clear(pathPrefixE);
					(Array.isArray(prefixes) ? prefixes : []).forEach((pfx) => {
						const opt = el("option", "");
						opt.value = String(pfx || "");
						opt.textContent = String(pfx || "");
						pathPrefixE.appendChild(opt);
					});
					initFromWhen();
					updateCondUiE();
				});

				const btnSave = text("button", "btn btnSmall", "Save");
				btnSave.type = "button";
				btnSave.addEventListener("click", () => {
					const toId = String(toSelE.value || "");
					const p = Number(prioE.value || 0);
					const t = String(condTypeE.value || "unconditional");
					const whenVal = buildWhenValue(
						t,
						String(pathPrefixE.value || ""),
						String(pathRestE.value || ""),
						String(valE.value || ""),
					);
					state.updateEdge &&
						state.updateEdge(String(selected), Number(e.outgoingIndex || 0), {
							to_step_id: toId,
							priority: p,
							when: whenVal,
						});
					_editState = { from: null, outgoingIndex: null };
				});

				const btnCancel = text("button", "btn btnSmall", "Cancel");
				btnCancel.type = "button";
				btnCancel.addEventListener("click", () => {
					_editState = { from: null, outgoingIndex: null };
					rerender();
				});

				row.appendChild(prioE);
				row.appendChild(toSelE);
				row.appendChild(condTypeE);
				row.appendChild(pathPrefixE);
				row.appendChild(pathRestE);
				row.appendChild(valE);
				row.appendChild(btnSave);
				row.appendChild(btnCancel);
				table.appendChild(row);
			});
	}

	W.AM2WDTransitionsRender = {
		renderTransitions: renderTransitions,
	};
})();
