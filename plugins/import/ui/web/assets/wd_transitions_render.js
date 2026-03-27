(() => {
	const W = window;
	const H = W.AM2EditorHTTP;

	/** @type {(definition: AM2JsonObject) => AM2WDStableGraphResult} */
	const stableGraph =
		W.AM2WDGraphStable && W.AM2WDGraphStable.stableGraph
			? W.AM2WDGraphStable.stableGraph
			: () => ({ version: 1, nodes: [], edges: [], entry: null });

	/** @param {Node | null | undefined} node */
	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	/** @param {AM2JsonValue} whenVal */
	function summarizeWhen(whenVal) {
		if (whenVal === null || whenVal === undefined) return "<unconditional>";
		if (typeof whenVal === "boolean") return whenVal ? "true" : "false";
		if (typeof whenVal === "object") {
			const condition = /** @type {AM2WDTransitionCondition} */ (whenVal);
			const op = condition.op;
			const path = condition.path;
			if (typeof op === "string" && op && typeof path === "string" && path) {
				if (Object.prototype.hasOwnProperty.call(condition, "value")) {
					return op + ":" + path + "=" + String(condition.value);
				}
				return op + ":" + path;
			}
			if (typeof op === "string" && op) return op;
		}
		return "<cond>";
	}

	/** @type {string[] | null} */
	let prefixesCache = null;
	/** @type {{ from: string | null, outgoingIndex: number | null }} */
	let editState = { from: null, outgoingIndex: null };

	/** @returns {Promise<string[]>} */
	async function getPathPrefixes() {
		if (prefixesCache) return prefixesCache;
		if (!H || !H.requestJSON) {
			prefixesCache = ["cfg.defaults."];
			return prefixesCache;
		}
		const out = await H.requestJSON("/import/ui/transition-condition-prefixes");
		if (!out.ok) {
			prefixesCache = ["cfg.defaults."];
			return prefixesCache;
		}
		const items =
			out.data && Array.isArray(out.data.items) ? out.data.items : [];
		prefixesCache = items.map((entry) => String(entry || ""));
		if (!prefixesCache.length) prefixesCache = ["cfg.defaults."];
		return prefixesCache;
	}

	/** @param {string} type */
	function needsPath(type) {
		return (
			type === "eq" ||
			type === "neq" ||
			type === "exists" ||
			type === "not_exists"
		);
	}

	/** @param {string} type */
	function needsValue(type) {
		return type === "eq" || type === "neq";
	}

	/**
	 * @param {string} type
	 * @param {string} prefix
	 * @param {string} rest
	 * @param {string} value
	 * @returns {AM2JsonValue}
	 */
	function buildWhenValue(type, prefix, rest, value) {
		if (type === "true") return true;
		if (type === "false") return false;
		if (type === "unconditional") return null;
		const trimmed = String(rest || "").trim();
		if (!prefix || !trimmed) return null;
		const fullPath = String(prefix) + trimmed;
		if (type === "exists") return { op: "exists", path: fullPath };
		if (type === "not_exists") return { op: "not_exists", path: fullPath };
		if (type === "eq" || type === "neq") {
			return { op: type, path: fullPath, value: String(value || "") };
		}
		return null;
	}

	/**
	 * @param {{
	 *   mount?: HTMLElement | null,
	 *   el?: AM2DomFactoryApi | null,
	 *   text?: AM2TextFactoryApi | null,
	 *   state?: AM2WDTransitionsStateApi | null,
	 * } | null | undefined} opts
	 */
	function renderTransitions(opts) {
		const mount = opts && opts.mount ? opts.mount : null;
		/** @type {AM2DomFactoryApi} */
		const el =
			(opts && opts.el) ||
			/** @type {AM2DomFactoryApi} */ (() => document.createElement("div"));
		/** @type {AM2TextFactoryApi} */
		const text =
			(opts && opts.text) ||
			/** @type {AM2TextFactoryApi} */ (
				(tag, cls, value) => {
					const node = document.createElement(tag);
					if (cls) node.className = cls;
					node.textContent = String(value || "");
					return node;
				}
			);
		/** @type {AM2WDTransitionsStateApi} */
		const state =
			(opts && opts.state) ||
			/** @type {AM2WDTransitionsStateApi} */ ({
				getWizardDraft: () => ({}),
				getSelectedStepId: () => null,
				addEdge: () => {},
				removeEdge: () => {},
			});
		if (!mount) return;

		clear(mount);

		const wizardDraft = state.getWizardDraft ? state.getWizardDraft() : {};
		const graph = stableGraph(wizardDraft);
		const selected = state.getSelectedStepId ? state.getSelectedStepId() : null;
		const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
		/** @type {AM2WizardDefinitionGraphEdge[]} */
		const edges = Array.isArray(graph.edges) ? graph.edges : [];

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
			(edge) => String(edge.from_step_id || "") === String(selected),
		);
		/** @type {Array<{ edge: AM2WizardDefinitionGraphEdge, outgoingIndex: number }>} */
		const outgoingWithIndex = outgoing.map((edge, outgoingIndex) => ({
			edge,
			outgoingIndex,
		}));

		const addWrap = el("div", "flowTransAdd");
		const toSel = /** @type {HTMLSelectElement} */ (
			el("select", "flowTransSelect")
		);
		nodes.forEach((stepId) => {
			const opt = /** @type {HTMLOptionElement} */ (el("option", ""));
			opt.value = String(stepId || "");
			opt.textContent = String(stepId || "");
			toSel.appendChild(opt);
		});
		const prio = /** @type {HTMLInputElement} */ (el("input", "flowTransPrio"));
		prio.type = "number";
		prio.value = "0";
		prio.min = "-99999";
		prio.max = "99999";
		const condType = /** @type {HTMLSelectElement} */ (
			el("select", "flowTransSelect")
		);
		[
			{ id: "unconditional", label: "Unconditional" },
			{ id: "true", label: "Always true" },
			{ id: "false", label: "Always false" },
			{ id: "eq", label: "Equals" },
			{ id: "neq", label: "Not equals" },
			{ id: "exists", label: "Exists" },
			{ id: "not_exists", label: "Not exists" },
		].forEach((item) => {
			const opt = /** @type {HTMLOptionElement} */ (el("option", ""));
			opt.value = item.id;
			opt.textContent = item.label;
			condType.appendChild(opt);
		});

		const pathPrefix = /** @type {HTMLSelectElement} */ (
			el("select", "flowTransSelect")
		);
		const pathRest = /** @type {HTMLInputElement} */ (
			el("input", "flowTransWhen")
		);
		pathRest.type = "text";
		pathRest.placeholder = "path";
		const val = /** @type {HTMLInputElement} */ (el("input", "flowTransWhen"));
		val.type = "text";
		val.placeholder = "value";

		function updateCondUi() {
			const type = String(condType.value || "unconditional");
			const showPath = needsPath(type);
			const showValue = needsValue(type);
			pathPrefix.disabled = !showPath;
			pathRest.disabled = !showPath;
			val.disabled = !showValue;
			if (!showPath) pathRest.value = "";
			if (!showValue) val.value = "";
		}

		const btnAdd = /** @type {HTMLButtonElement} */ (
			text("button", "btn btnSmall", "Add")
		);
		btnAdd.type = "button";
		btnAdd.addEventListener("click", () => {
			const toId = String(toSel.value || "");
			const priority = Number(prio.value || 0);
			const type = String(condType.value || "unconditional");
			let whenVal = /** @type {AM2JsonValue} */ (null);
			if (type === "true") whenVal = true;
			else if (type === "false") whenVal = false;
			else if (type === "unconditional") whenVal = null;
			else {
				const prefix = String(pathPrefix.value || "");
				const rest = String(pathRest.value || "").trim();
				if (!prefix || !rest) {
					window.alert("Condition path is required");
					return;
				}
				whenVal = buildWhenValue(type, prefix, rest, String(val.value || ""));
			}
			if (state.addEdge)
				state.addEdge(String(selected), toId, priority, whenVal);
		});

		addWrap.append(toSel, prio, condType, pathPrefix, pathRest, val, btnAdd);
		body.appendChild(addWrap);

		void getPathPrefixes().then((prefixes) => {
			clear(pathPrefix);
			prefixes.forEach((prefix) => {
				const opt = /** @type {HTMLOptionElement} */ (el("option", ""));
				opt.value = prefix;
				opt.textContent = prefix;
				pathPrefix.appendChild(opt);
			});
			updateCondUi();
		});

		condType.addEventListener("change", updateCondUi);
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

		outgoingWithIndex
			.slice(0)
			.sort(
				(left, right) =>
					Number(left.edge.priority || 0) - Number(right.edge.priority || 0),
			)
			.forEach((entry) => {
				const edge = entry.edge;
				const row = el("div", "flowTransRow");
				const isEditing =
					String(editState.from || "") === String(selected) &&
					Number(editState.outgoingIndex || -1) ===
						Number(entry.outgoingIndex || -2);

				if (!isEditing) {
					row.appendChild(
						text("div", "flowTransCellPri", String(edge.priority || 0)),
					);
					row.appendChild(
						text("div", "flowTransTo", String(edge.to_step_id || "")),
					);
					row.appendChild(
						text(
							"div",
							"flowTransMeta",
							summarizeWhen(edge.when === undefined ? null : edge.when),
						),
					);

					const btnUp = /** @type {HTMLButtonElement} */ (
						text("button", "btn btnSmall", "Up")
					);
					btnUp.type = "button";
					btnUp.addEventListener("click", () => {
						if (state.moveEdge)
							state.moveEdge(
								String(selected),
								Number(entry.outgoingIndex || 0),
								-1,
							);
					});

					const btnDown = /** @type {HTMLButtonElement} */ (
						text("button", "btn btnSmall", "Down")
					);
					btnDown.type = "button";
					btnDown.addEventListener("click", () => {
						if (state.moveEdge)
							state.moveEdge(
								String(selected),
								Number(entry.outgoingIndex || 0),
								1,
							);
					});

					const btnEdit = /** @type {HTMLButtonElement} */ (
						text("button", "btn btnSmall", "Edit")
					);
					btnEdit.type = "button";
					btnEdit.addEventListener("click", () => {
						editState = {
							from: String(selected),
							outgoingIndex: Number(entry.outgoingIndex || 0),
						};
						rerender();
					});

					const btnDel = /** @type {HTMLButtonElement} */ (
						text("button", "btn btnSmall", "Remove")
					);
					btnDel.type = "button";
					btnDel.addEventListener("click", () => {
						if (state.removeEdge)
							state.removeEdge(
								String(selected),
								Number(entry.outgoingIndex || 0),
							);
					});

					row.append(btnUp, btnDown, btnEdit, btnDel);
					table.appendChild(row);
					return;
				}

				const toSelE = /** @type {HTMLSelectElement} */ (
					el("select", "flowTransSelect")
				);
				nodes.forEach((stepId) => {
					const opt = /** @type {HTMLOptionElement} */ (el("option", ""));
					opt.value = String(stepId || "");
					opt.textContent = String(stepId || "");
					toSelE.appendChild(opt);
				});
				toSelE.value = String(edge.to_step_id || "");

				const prioE = /** @type {HTMLInputElement} */ (
					el("input", "flowTransPrio")
				);
				prioE.type = "number";
				prioE.min = "-99999";
				prioE.max = "99999";
				prioE.value = String(edge.priority || 0);

				const condTypeE = /** @type {HTMLSelectElement} */ (
					el("select", "flowTransSelect")
				);
				[
					{ id: "unconditional", label: "Unconditional" },
					{ id: "true", label: "Always true" },
					{ id: "false", label: "Always false" },
					{ id: "eq", label: "Equals" },
					{ id: "neq", label: "Not equals" },
					{ id: "exists", label: "Exists" },
					{ id: "not_exists", label: "Not exists" },
				].forEach((item) => {
					const opt = /** @type {HTMLOptionElement} */ (el("option", ""));
					opt.value = item.id;
					opt.textContent = item.label;
					condTypeE.appendChild(opt);
				});

				const pathPrefixE = /** @type {HTMLSelectElement} */ (
					el("select", "flowTransSelect")
				);
				const pathRestE = /** @type {HTMLInputElement} */ (
					el("input", "flowTransWhen")
				);
				pathRestE.type = "text";
				pathRestE.placeholder = "path";
				const valE = /** @type {HTMLInputElement} */ (
					el("input", "flowTransWhen")
				);
				valE.type = "text";
				valE.placeholder = "value";

				function initFromWhen() {
					const whenVal = edge.when;
					if (whenVal === null || whenVal === undefined) {
						condTypeE.value = "unconditional";
						return;
					}
					if (whenVal === true) {
						condTypeE.value = "true";
						return;
					}
					if (whenVal === false) {
						condTypeE.value = "false";
						return;
					}
					if (typeof whenVal === "object") {
						const condition = /** @type {AM2WDTransitionCondition} */ (whenVal);
						if (typeof condition.op === "string")
							condTypeE.value = condition.op;
						const path =
							typeof condition.path === "string" ? condition.path : "";
						const prefixes = Array.from(pathPrefixE.options).map(
							(option) => option.value,
						);
						const match = prefixes.find((prefix) => path.startsWith(prefix));
						if (match) {
							pathPrefixE.value = match;
							pathRestE.value = path.slice(match.length);
						} else {
							pathRestE.value = path;
						}
						if (Object.prototype.hasOwnProperty.call(condition, "value")) {
							valE.value = String(condition.value || "");
						}
					}
				}

				function updateCondUiE() {
					const type = String(condTypeE.value || "unconditional");
					const showPath = needsPath(type);
					const showValue = needsValue(type);
					pathPrefixE.disabled = !showPath;
					pathRestE.disabled = !showPath;
					valE.disabled = !showValue;
					if (!showPath) pathRestE.value = "";
					if (!showValue) valE.value = "";
				}

				condTypeE.addEventListener("change", updateCondUiE);
				void getPathPrefixes().then((prefixes) => {
					clear(pathPrefixE);
					prefixes.forEach((prefix) => {
						const opt = /** @type {HTMLOptionElement} */ (el("option", ""));
						opt.value = prefix;
						opt.textContent = prefix;
						pathPrefixE.appendChild(opt);
					});
					initFromWhen();
					updateCondUiE();
				});

				const btnSave = /** @type {HTMLButtonElement} */ (
					text("button", "btn btnSmall", "Save")
				);
				btnSave.type = "button";
				btnSave.addEventListener("click", () => {
					const payload = {
						to_step_id: String(toSelE.value || ""),
						priority: Number(prioE.value || 0),
						when: buildWhenValue(
							String(condTypeE.value || "unconditional"),
							String(pathPrefixE.value || ""),
							String(pathRestE.value || ""),
							String(valE.value || ""),
						),
					};
					if (state.updateEdge)
						state.updateEdge(
							String(selected),
							Number(entry.outgoingIndex || 0),
							payload,
						);
					editState = { from: null, outgoingIndex: null };
				});

				const btnCancel = /** @type {HTMLButtonElement} */ (
					text("button", "btn btnSmall", "Cancel")
				);
				btnCancel.type = "button";
				btnCancel.addEventListener("click", () => {
					editState = { from: null, outgoingIndex: null };
					rerender();
				});

				row.append(
					prioE,
					toSelE,
					condTypeE,
					pathPrefixE,
					pathRestE,
					valE,
					btnSave,
					btnCancel,
				);
				table.appendChild(row);
			});
	}

	W.AM2WDTransitionsRender = { renderTransitions };
})();
