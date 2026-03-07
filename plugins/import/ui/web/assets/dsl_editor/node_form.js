(function () {
	"use strict";

	const PROMPT_PRIMITIVE_IDS = {
		"ui.prompt_text": "value",
		"ui.prompt_select": "selection",
		"ui.prompt_confirm": "confirmed",
	};
	const PROMPT_INFO_KEYS = ["label", "prompt", "help", "hint"];
	const PROMPT_RUNTIME_JSON_KEYS = ["default_value", "prefill"];
	const PROMPT_RUNTIME_EXPR_KEYS = [
		"default_expr",
		"prefill_expr",
		"autofill_if",
	];
	const PROMPT_METADATA_KEYS = [
		"label",
		"prompt",
		"help",
		"hint",
		"examples",
		"default_value",
		"prefill",
		"default_expr",
		"prefill_expr",
		"autofill_if",
	];

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

	function parseLooseJSON(textValue) {
		if (textValue === "") return "";
		try {
			return JSON.parse(textValue);
		} catch (_err) {
			return textValue;
		}
	}

	function serializeLooseJSON(value) {
		if (value === undefined || value === null) return "";
		if (
			typeof value === "string" ||
			typeof value === "number" ||
			typeof value === "boolean"
		) {
			return String(value);
		}
		return JSON.stringify(value, null, 2);
	}

	function cloneInputs(node) {
		const raw =
			node && node.op && typeof node.op.inputs === "object"
				? node.op.inputs
				: {};
		return JSON.parse(JSON.stringify(raw || {}));
	}

	function applyTextInput(node, key, rawValue) {
		const next = cloneInputs(node);
		if (String(rawValue || "") === "") {
			delete next[key];
		} else {
			next[key] = String(rawValue);
		}
		return next;
	}

	function applyLooseJSONInput(node, key, rawValue) {
		const next = cloneInputs(node);
		if (String(rawValue || "") === "") {
			delete next[key];
		} else {
			next[key] = parseLooseJSON(String(rawValue));
		}
		return next;
	}

	function applyExprInput(node, key, rawValue) {
		const next = cloneInputs(node);
		if (String(rawValue || "") === "") {
			delete next[key];
		} else {
			next[key] = { expr: String(rawValue) };
		}
		return next;
	}

	function currentWriteItem(pathInput, valueInput) {
		return {
			to_path: pathInput.value,
			value: parseJSON(valueInput.value, null),
		};
	}

	function isPromptPrimitive(node) {
		const primitiveId = String((node && node.op && node.op.primitive_id) || "");
		const version = Number((node && node.op && node.op.primitive_version) || 0);
		return (
			version === 1 &&
			Object.prototype.hasOwnProperty.call(PROMPT_PRIMITIVE_IDS, primitiveId)
		);
	}

	function isMessagePrimitive(node) {
		const primitiveId = String((node && node.op && node.op.primitive_id) || "");
		const version = Number((node && node.op && node.op.primitive_version) || 0);
		return version === 1 && primitiveId === "ui.message";
	}

	function setControlKey(node, key) {
		node.setAttribute("data-am2-input-key", key);
		return node;
	}

	function appendNote(mount, key, textValue) {
		const note = el("div", "flowStepDesc", textValue);
		note.setAttribute("data-am2-note", key);
		mount.appendChild(note);
	}

	function appendTextField(mount, node, onPatchNode, key, labelText, rows) {
		let input;
		if (rows > 1) {
			input = document.createElement("textarea");
			input.rows = rows;
		} else {
			input = document.createElement("input");
		}
		input.value = String(
			(node.op && node.op.inputs && node.op.inputs[key]) || "",
		);
		setControlKey(input, key);
		input.addEventListener("change", function () {
			onPatchNode({ inputs: applyTextInput(node, key, input.value) });
		});
		mount.appendChild(row(labelText, input));
	}

	function appendLooseJSONField(mount, node, onPatchNode, key, labelText) {
		const input = document.createElement("textarea");
		input.rows = 3;
		input.value = serializeLooseJSON(
			node.op && node.op.inputs && node.op.inputs[key],
		);
		setControlKey(input, key);
		input.addEventListener("change", function () {
			onPatchNode({ inputs: applyLooseJSONInput(node, key, input.value) });
		});
		mount.appendChild(row(labelText, input));
	}

	function appendExprField(mount, node, onPatchNode, key, labelText) {
		const input = document.createElement("input");
		const current = node.op && node.op.inputs ? node.op.inputs[key] : null;
		input.value =
			current && typeof current.expr === "string" ? current.expr : "";
		setControlKey(input, key);
		input.addEventListener("change", function () {
			onPatchNode({ inputs: applyExprInput(node, key, input.value) });
		});
		mount.appendChild(row(labelText, input));
	}

	function appendExamplesSection(mount, node, onPatchNode) {
		const section = el("div", "flowStepSection");
		section.setAttribute("data-am2-section", "examples");
		section.appendChild(el("div", "flowStepSectionTitle", "examples"));

		const baseInputs = cloneInputs(node);
		const examples = Array.isArray(baseInputs.examples)
			? baseInputs.examples.slice(0)
			: [];
		if (!examples.length) {
			section.appendChild(el("div", "flowStepDesc", "No examples configured."));
		}

		examples.forEach(function (exampleValue, index) {
			const wrap = el("div", "flowField");
			const input = document.createElement("textarea");
			input.rows = 2;
			input.value = serializeLooseJSON(exampleValue);
			setControlKey(input, "examples." + String(index));
			input.addEventListener("change", function () {
				const next = cloneInputs(node);
				const nextExamples = Array.isArray(next.examples)
					? next.examples.slice(0)
					: [];
				nextExamples[index] = parseLooseJSON(String(input.value || ""));
				next.examples = nextExamples;
				onPatchNode({ inputs: next });
			});
			wrap.appendChild(
				el("div", "flowStepSectionTitle", "example #" + String(index + 1)),
			);
			wrap.appendChild(input);

			const removeBtn = el("button", "btn", "Remove Example");
			removeBtn.type = "button";
			removeBtn.setAttribute("data-am2-example-remove", String(index));
			removeBtn.addEventListener("click", function () {
				const next = cloneInputs(node);
				const nextExamples = Array.isArray(next.examples)
					? next.examples.slice(0)
					: [];
				nextExamples.splice(index, 1);
				if (nextExamples.length) {
					next.examples = nextExamples;
				} else {
					delete next.examples;
				}
				onPatchNode({ inputs: next });
			});
			wrap.appendChild(removeBtn);
			section.appendChild(wrap);
		});

		const addBtn = el("button", "btn", "Add Example");
		addBtn.type = "button";
		addBtn.setAttribute("data-am2-example-add", "true");
		addBtn.addEventListener("click", function () {
			const next = cloneInputs(node);
			const nextExamples = Array.isArray(next.examples)
				? next.examples.slice(0)
				: [];
			nextExamples.push("");
			next.examples = nextExamples;
			onPatchNode({ inputs: next });
		});
		section.appendChild(addBtn);
		mount.appendChild(section);
	}

	function appendPromptPrimitiveFields(mount, node, onPatchNode) {
		const primitiveId = String((node && node.op && node.op.primitive_id) || "");
		mount.setAttribute("data-am2-node-form", "prompt");
		appendNote(
			mount,
			"prompt-authoring",
			"Prompt metadata is authored here. Raw JSON remains authoritative for advanced keys.",
		);
		appendNote(
			mount,
			"submit-key",
			"Submit payload key: " + String(PROMPT_PRIMITIVE_IDS[primitiveId] || ""),
		);
		PROMPT_INFO_KEYS.forEach(function (key) {
			appendTextField(
				mount,
				node,
				onPatchNode,
				key,
				key,
				key === "help" ? 3 : 1,
			);
		});
		appendExamplesSection(mount, node, onPatchNode);
		PROMPT_RUNTIME_JSON_KEYS.forEach(function (key) {
			appendLooseJSONField(mount, node, onPatchNode, key, key);
		});
		PROMPT_RUNTIME_EXPR_KEYS.forEach(function (key) {
			appendExprField(mount, node, onPatchNode, key, key);
		});

		const unknownKeys = Object.keys(cloneInputs(node)).filter(function (key) {
			return PROMPT_METADATA_KEYS.indexOf(key) < 0;
		});
		if (unknownKeys.length) {
			appendNote(
				mount,
				"advanced-keys",
				"Advanced op.inputs keys are preserved in Raw JSON: " +
					unknownKeys.join(", "),
			);
		}
	}

	function appendMessagePrimitiveFields(mount, node, onPatchNode) {
		mount.setAttribute("data-am2-node-form", "message");
		appendNote(
			mount,
			"message-info",
			"ui.message@1 is non-interactive. It has no submit payload, defaults, or autofill.",
		);
		appendTextField(mount, node, onPatchNode, "text", "text", 3);

		const unknownKeys = Object.keys(cloneInputs(node)).filter(function (key) {
			return key !== "text";
		});
		if (unknownKeys.length) {
			appendNote(
				mount,
				"message-raw-json",
				"Additional ui.message inputs are preserved in Raw JSON: " +
					unknownKeys.join(", "),
			);
		}
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

		if (isPromptPrimitive(node)) {
			appendPromptPrimitiveFields(mount, node, onPatchNode);
		} else if (isMessagePrimitive(node)) {
			appendMessagePrimitiveFields(mount, node, onPatchNode);
		} else {
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
		}

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
