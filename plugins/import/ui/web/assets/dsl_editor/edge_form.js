(function () {
	"use strict";

	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	function el(tag, cls, textValue) {
		const node = document.createElement(tag);
		if (cls) node.className = cls;
		if (textValue !== undefined) node.textContent = String(textValue);
		return node;
	}

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

	function parseCondition(value) {
		const trimmed = String(value || "").trim();
		if (!trimmed) return null;
		return JSON.parse(trimmed);
	}

	function renderEdgeForm(opts) {
		const mount = opts && opts.mount;
		if (!mount) return;
		clear(mount);

		const definition = (opts && opts.definition) || {};
		const nodes = Array.isArray(definition.nodes) ? definition.nodes : [];
		const stepIds = nodes
			.map((item) => String(item.step_id || ""))
			.filter(Boolean);
		const edges = Array.isArray(definition.edges) ? definition.edges : [];
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
			const card = el("div", "flowStepSection");
			card.appendChild(el("div", "flowStepDesc", "edge #" + String(index + 1)));
			card.appendChild(
				selectNode(stepIds, String(edge.from || ""), function (value) {
					onPatchEdge(index, {
						from: value,
						to: edge.to,
						condition_expr: edge.condition_expr || null,
					});
				}),
			);
			card.appendChild(
				selectNode(stepIds, String(edge.to || ""), function (value) {
					onPatchEdge(index, {
						from: edge.from,
						to: value,
						condition_expr: edge.condition_expr || null,
					});
				}),
			);
			const condition = document.createElement("textarea");
			condition.rows = 4;
			condition.value = edge.condition_expr
				? JSON.stringify(edge.condition_expr, null, 2)
				: "";
			condition.addEventListener("change", function () {
				onPatchEdge(index, {
					from: edge.from,
					to: edge.to,
					condition_expr: parseCondition(condition.value),
				});
			});
			card.appendChild(condition);
			const removeBtn = el("button", "btn", "Remove Edge");
			removeBtn.type = "button";
			removeBtn.addEventListener("click", function () {
				onRemoveEdge(index);
			});
			card.appendChild(removeBtn);
			wrap.appendChild(card);
		});

		const addBtn = el("button", "btn", "Add Edge");
		addBtn.type = "button";
		addBtn.disabled = stepIds.length < 2;
		addBtn.addEventListener("click", function () {
			onAddEdge();
		});
		wrap.appendChild(addBtn);
		mount.appendChild(wrap);
	}

	window["AM2DSLEditorEdgeForm"] = { renderEdgeForm: renderEdgeForm };
})();
