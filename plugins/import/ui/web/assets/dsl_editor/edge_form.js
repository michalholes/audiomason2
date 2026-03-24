(function () {
	"use strict";

	/** @param {Node | null} node */
	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	/** @param {string} tag @param {string | null | undefined} cls @param {unknown=} textValue */
	function el(tag, cls, textValue) {
		const node = document.createElement(tag);
		if (cls) node.className = cls;
		if (textValue !== undefined) node.textContent = String(textValue);
		return node;
	}

	/** @param {string} label @returns {HTMLButtonElement} */
	function button(label) {
		const node = document.createElement("button");
		node.className = "btn";
		node.type = "button";
		node.textContent = label;
		return node;
	}

	/** @param {AM2JsonObject[]} nodes @returns {string[]} */
	function stepIdsOf(nodes) {
		return nodes.map((item) => String(item.step_id || "")).filter(Boolean);
	}

	/** @param {string[]} stepIds @param {string} value @param {(value: string) => void} onChange */
	function selectNode(stepIds, value, onChange) {
		const select = document.createElement("select");
		stepIds.forEach((stepId) => {
			const option = document.createElement("option");
			option.value = stepId;
			option.textContent = stepId;
			option.selected = stepId === value;
			select.appendChild(option);
		});
		select.addEventListener("change", function () {
			onChange(select.value || "");
		});
		return select;
	}

	/** @param {unknown} value @returns {AM2JsonValue | null} */
	function parseCondition(value) {
		const trimmed = String(value || "").trim();
		if (!trimmed) return null;
		return /** @type {AM2JsonValue} */ (JSON.parse(trimmed));
	}

	/** @param {AM2DSLEditorEdgeRecord} edge @returns {AM2DSLEditorEdgeRecord} */
	function normalizedEdge(edge) {
		return {
			from: String(edge.from || ""),
			to: String(edge.to || ""),
			condition_expr: edge.condition_expr || null,
		};
	}

	/** @param {AM2DSLEditorEdgeFormOptions} opts */
	function renderEdgeForm(opts) {
		const mount = opts && opts.mount;
		if (!mount) return;
		clear(mount);

		const definition = (opts && opts.definition) || {};
		const nodes = /** @type {AM2JsonObject[]} */ (
			Array.isArray(definition.nodes) ? definition.nodes : []
		);
		const stepIds = stepIdsOf(nodes);
		const edges = /** @type {AM2DSLEditorEdgeRecord[]} */ (
			Array.isArray(definition.edges) ? definition.edges : []
		);
		const actions = (opts && opts.actions) || {};
		const onAddEdge =
			typeof actions.onAddEdge === "function"
				? actions.onAddEdge
				: function () {};
		const onPatchEdge =
			typeof actions.onPatchEdge === "function"
				? actions.onPatchEdge
				: function () {};
		const onRemoveEdge =
			typeof actions.onRemoveEdge === "function"
				? actions.onRemoveEdge
				: function () {};

		const wrap = el("div", "flowStepSection");
		wrap.appendChild(el("div", "flowStepSectionTitle", "Edges"));

		edges.forEach((edge, index) => {
			const edgeRecord = normalizedEdge(edge);
			const card = el("div", "flowStepSection");
			card.appendChild(el("div", "flowStepDesc", "edge #" + String(index + 1)));
			card.appendChild(
				selectNode(stepIds, String(edgeRecord.from || ""), function (value) {
					onPatchEdge(index, {
						from: value,
						to: String(edgeRecord.to || ""),
						condition_expr: edgeRecord.condition_expr || null,
					});
				}),
			);
			card.appendChild(
				selectNode(stepIds, String(edgeRecord.to || ""), function (value) {
					onPatchEdge(index, {
						from: String(edgeRecord.from || ""),
						to: value,
						condition_expr: edgeRecord.condition_expr || null,
					});
				}),
			);
			const condition = document.createElement("textarea");
			condition.rows = 4;
			condition.value = edgeRecord.condition_expr
				? JSON.stringify(edgeRecord.condition_expr, null, 2)
				: "";
			condition.addEventListener("change", function () {
				onPatchEdge(index, {
					from: String(edgeRecord.from || ""),
					to: String(edgeRecord.to || ""),
					condition_expr: parseCondition(condition.value),
				});
			});
			card.appendChild(condition);
			const removeBtn = button("Remove Edge");
			removeBtn.addEventListener("click", function () {
				onRemoveEdge(index);
			});
			card.appendChild(removeBtn);
			wrap.appendChild(card);
		});

		const addBtn = button("Add Edge");
		addBtn.disabled = stepIds.length < 2;
		addBtn.addEventListener("click", function () {
			onAddEdge();
		});
		wrap.appendChild(addBtn);
		mount.appendChild(wrap);
	}

	window.AM2DSLEditorEdgeForm = { renderEdgeForm };
})();
