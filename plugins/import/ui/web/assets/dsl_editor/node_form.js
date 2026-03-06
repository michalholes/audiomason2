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

	function row(labelText, inputNode) {
		const wrap = el("label", "flowField");
		wrap.appendChild(el("div", "flowStepSectionTitle", labelText));
		wrap.appendChild(inputNode);
		return wrap;
	}

	function parseJSON(textValue, fallback) {
		if (!textValue) return fallback;
		return JSON.parse(textValue);
	}

	function currentWriteItem(pathInput, valueInput) {
		return {
			to_path: pathInput.value,
			value: parseJSON(valueInput.value, null),
		};
	}

	function writeRow(writeItem, index, onPatch, onRemove) {
		const wrap = el("div", "flowStepSection");
		const pathInput = document.createElement("input");
		pathInput.value = String((writeItem && writeItem.to_path) || "");
		pathInput.addEventListener("change", function () {
			onPatch(index, currentWriteItem(pathInput, valueInput));
		});
		wrap.appendChild(row("to_path", pathInput));

		const valueInput = document.createElement("textarea");
		valueInput.rows = 4;
		valueInput.value = JSON.stringify(writeItem && writeItem.value, null, 2);
		valueInput.addEventListener("change", function () {
			onPatch(index, currentWriteItem(pathInput, valueInput));
		});
		wrap.appendChild(row("value", valueInput));

		const removeBtn = el("button", "btn", "Remove Write");
		removeBtn.type = "button";
		removeBtn.addEventListener("click", function () {
			onRemove(index);
		});
		wrap.appendChild(removeBtn);
		return wrap;
	}

	function renderNodeForm(opts) {
		const mount = opts && opts.mount;
		if (!mount) return;
		clear(mount);

		const definition = (opts && opts.definition) || {};
		const nodes = Array.isArray(definition.nodes) ? definition.nodes : [];
		const selectedStepId = String((opts && opts.selectedStepId) || "");
		const node =
			nodes.find((item) => String(item.step_id || "") === selectedStepId) ||
			null;
		if (!node) {
			mount.appendChild(el("div", "flowStepDesc", "Select or add a v3 node."));
			return;
		}

		const actions = (opts && opts.actions) || {};
		const onSelect =
			typeof actions.onSelect === "function"
				? actions.onSelect
				: function () {};
		const onPatchNode =
			typeof actions.onPatchNode === "function"
				? actions.onPatchNode
				: function () {};
		const onAddWrite =
			typeof actions.onAddWrite === "function"
				? actions.onAddWrite
				: function () {};
		const onPatchWrite =
			typeof actions.onPatchWrite === "function"
				? actions.onPatchWrite
				: function () {};
		const onRemoveWrite =
			typeof actions.onRemoveWrite === "function"
				? actions.onRemoveWrite
				: function () {};
		const onRemoveNode =
			typeof actions.onRemoveNode === "function"
				? actions.onRemoveNode
				: function () {};

		const select = document.createElement("select");
		nodes.forEach((item) => {
			const option = document.createElement("option");
			option.value = String(item.step_id || "");
			option.textContent = String(item.step_id || "");
			option.selected = option.value === selectedStepId;
			select.appendChild(option);
		});
		select.addEventListener("change", function () {
			onSelect(select.value || "");
		});
		mount.appendChild(row("selected step_id", select));

		const stepInput = document.createElement("input");
		stepInput.value = String(node.step_id || "");
		stepInput.addEventListener("change", function () {
			onPatchNode({ step_id: stepInput.value });
		});
		mount.appendChild(row("step_id", stepInput));

		const primitiveInput = document.createElement("input");
		primitiveInput.value = String((node.op && node.op.primitive_id) || "");
		primitiveInput.addEventListener("change", function () {
			onPatchNode({ primitive_id: primitiveInput.value });
		});
		mount.appendChild(row("op.primitive_id", primitiveInput));

		const versionInput = document.createElement("input");
		versionInput.type = "number";
		versionInput.value = String((node.op && node.op.primitive_version) || 1);
		versionInput.addEventListener("change", function () {
			onPatchNode({ primitive_version: Number(versionInput.value || 0) });
		});
		mount.appendChild(row("op.primitive_version", versionInput));

		const inputsArea = document.createElement("textarea");
		inputsArea.rows = 6;
		inputsArea.value = JSON.stringify(
			(node.op && node.op.inputs) || {},
			null,
			2,
		);
		inputsArea.addEventListener("change", function () {
			onPatchNode({ inputs: parseJSON(inputsArea.value, {}) });
		});
		mount.appendChild(row("op.inputs", inputsArea));

		const writesWrap = el("div", "flowStepSection");
		writesWrap.appendChild(el("div", "flowStepSectionTitle", "op.writes"));
		const writes = Array.isArray(node.op && node.op.writes)
			? node.op.writes
			: [];
		writes.forEach((item, index) => {
			writesWrap.appendChild(
				writeRow(item || {}, index, onPatchWrite, onRemoveWrite),
			);
		});
		const addWriteBtn = el("button", "btn", "Add Write");
		addWriteBtn.type = "button";
		addWriteBtn.addEventListener("click", function () {
			onAddWrite();
		});
		writesWrap.appendChild(addWriteBtn);
		mount.appendChild(writesWrap);

		const removeBtn = el("button", "btn", "Remove Node");
		removeBtn.type = "button";
		removeBtn.addEventListener("click", function () {
			onRemoveNode(selectedStepId);
		});
		mount.appendChild(removeBtn);
	}

	window["AM2DSLEditorNodeForm"] = { renderNodeForm: renderNodeForm };
})();
