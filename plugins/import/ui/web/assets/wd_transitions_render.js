(function () {
	"use strict";

	const H = window.AM2EditorHTTP;

	const stableGraph =
		window.AM2WDGraphStable && window.AM2WDGraphStable.stableGraph
			? window.AM2WDGraphStable.stableGraph
			: function () {
					return { version: 1, nodes: [], edges: [], entry: null };
				};

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
		const el = (opts && opts.el) || function () {};
		const text = (opts && opts.text) || function () {};
		const state = (opts && opts.state) || {};
		if (!mount) return;

		clear(mount);

		const wd = state.getWizardDraft ? state.getWizardDraft() : {};
		const g = stableGraph(wd);
		const selected = state.getSelectedStepId ? state.getSelectedStepId() : null;
		const nodes = Array.isArray(g.nodes) ? g.nodes : [];
		const edges = Array.isArray(g.edges) ? g.edges : [];

		const panel = el("div", "flowTransPanel");
		const header = el("div", "flowTransHeader");
		header.appendChild(text("div", "flowTransTitle", "Transitions"));
		panel.appendChild(header);

		const body = el("div", "flowTransBody");
		panel.appendChild(body);
		mount.appendChild(panel);

		if (!selected) {
			body.appendChild(
				text("div", "flowTransEmpty", "Select a step to edit transitions."),
			);
			return;
		}

		const outgoing = edges.filter(function (e) {
			return String(e.from_step_id || "") === String(selected);
		});
		const outgoingWithIndex = outgoing.map(function (e, i) {
			return { edge: e, outgoingIndex: i };
		});

		const addWrap = el("div", "flowTransAdd");
		const toSel = el("select", "flowTransSelect");
		nodes.forEach(function (sid) {
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
		].forEach(function (it) {
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

		btnAdd.addEventListener("click", function () {
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

		_getPathPrefixes().then(function (prefixes) {
			clear(pathPrefix);
			(Array.isArray(prefixes) ? prefixes : []).forEach(function (pfx) {
				const opt = el("option", "");
				opt.value = String(pfx || "");
				opt.textContent = String(pfx || "");
				pathPrefix.appendChild(opt);
			});
			updateCondUi();
		});

		condType.addEventListener("change", function () {
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

		outgoingWithIndex
			.slice(0)
			.sort(function (a, b) {
				return Number(a.edge.priority || 0) - Number(b.edge.priority || 0);
			})
			.forEach(function (e, idx) {
				const edge = e.edge;
				const row = el("div", "flowTransRow");
				row.appendChild(
					text("div", "flowTransCellPri", String(edge.priority || 0)),
				);
				row.appendChild(
					text("div", "flowTransTo", String(edge.to_step_id || "")),
				);
				row.appendChild(
					text("div", "flowTransMeta", _summarizeWhen(edge.when)),
				);

				const btnDel = text("button", "btn btnSmall", "Remove");
				btnDel.type = "button";
				btnDel.addEventListener("click", function () {
					state.removeEdge &&
						state.removeEdge(String(selected), Number(e.outgoingIndex || 0));
				});
				row.appendChild(btnDel);
				table.appendChild(row);
			});
	}

	window.AM2WDTransitionsRender = {
		renderTransitions: renderTransitions,
	};
})();
