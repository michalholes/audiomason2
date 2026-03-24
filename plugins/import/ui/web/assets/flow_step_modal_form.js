(function () {
	"use strict";

	/** @type {Window} */
	const W = window;

	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	function el(tag, cls, textValue) {
		const node = document.createElement(tag);
		if (cls) node.className = cls;
		if (textValue !== undefined) node.textContent = String(textValue);
		return node;
	}

	function safeClone(value) {
		return JSON.parse(JSON.stringify(value));
	}

	function readInputValue(step, key) {
		const inputs =
			step && step.op && step.op.inputs && typeof step.op.inputs === "object"
				? step.op.inputs
				: {};
		return safeClone(inputs[key]);
	}

	function fieldEditorFor(key, value) {
		if (key === "text") return "textarea";
		if (key === "help") return "textarea";
		if (key === "prompt") return "textarea";
		if (key === "hint") return "textarea";
		if (key === "label") return "text";
		if (key === "examples") return "json";
		if (key === "default_value") return "json";
		if (key === "prefill") return "json";
		if (key === "autofill_if") return "json";
		if (/_expr$/.test(key)) return "json";
		if (typeof value === "number") return "number";
		if (typeof value === "boolean") return "boolean";
		if (typeof value === "string")
			return value.length > 120 ? "textarea" : "text";
		return "json";
	}

	function buildFieldSpecs(step) {
		const specs = [
			{
				fieldId: "core:step_id",
				label: "step_id",
				editor: "text",
				getValue: function (node) {
					return String((node && node.step_id) || "");
				},
			},
			{
				fieldId: "core:primitive_id",
				label: "primitive_id",
				editor: "text",
				getValue: function (node) {
					return String((node && node.op && node.op.primitive_id) || "");
				},
			},
			{
				fieldId: "core:primitive_version",
				label: "primitive_version",
				editor: "number",
				getValue: function (node) {
					return String(
						(node && node.op && node.op.primitive_version) === undefined
							? ""
							: node.op.primitive_version,
					);
				},
			},
		];
		const inputs =
			step && step.op && step.op.inputs && typeof step.op.inputs === "object"
				? step.op.inputs
				: {};
		Object.keys(inputs)
			.sort()
			.forEach(function (key) {
				const editor = fieldEditorFor(key, inputs[key]);
				specs.push({
					fieldId: "input:" + key,
					label: key,
					editor: editor,
					getValue: function (node) {
						const value = readInputValue(node, key);
						if (editor === "json") {
							return JSON.stringify(
								value === undefined ? null : value,
								null,
								2,
							);
						}
						return String(value === undefined ? "" : value);
					},
				});
			});
		specs.push({
			fieldId: "writes",
			label: "writes",
			editor: "json",
			getValue: function (node) {
				const writes =
					node && node.op && Array.isArray(node.op.writes)
						? node.op.writes
						: [];
				return JSON.stringify(writes, null, 2);
			},
		});
		return specs;
	}

	function renderInput(spec, value, handlers) {
		let input = null;
		if (spec.editor === "textarea" || spec.editor === "json") {
			input = document.createElement("textarea");
			input.rows = spec.editor === "json" ? 8 : 3;
		} else if (spec.editor === "boolean") {
			input = document.createElement("select");
			const blank = document.createElement("option");
			blank.value = "";
			blank.textContent = "";
			input.appendChild(blank);
			["true", "false"].forEach(function (item) {
				const option = document.createElement("option");
				option.value = item;
				option.textContent = item;
				input.appendChild(option);
			});
		} else {
			input = document.createElement("input");
			input.type = spec.editor === "number" ? "number" : "text";
		}
		input.value = String(value || "");
		input.addEventListener("input", function () {
			handlers.onFieldInput(spec, input.value || "");
		});
		return input;
	}

	function renderField(mount, spec, state, handlers) {
		const row = el("div", "flowStepModalField");
		const head = el("div", "flowStepModalFieldHead");
		head.appendChild(el("label", "flowStepModalFieldLabel", spec.label));
		const badge = el("span", "flowStepModalFieldBadge", "dirty");
		head.appendChild(badge);
		row.appendChild(head);
		const value = handlers.readFieldValue(spec);
		const input = renderInput(spec, value, handlers);
		input.classList.add("flowStepModalFieldInput");
		row.appendChild(input);
		const footer = el("div", "flowStepModalFieldFooter");
		const applyBtn = el("button", "btn", "Apply");
		applyBtn.type = "button";
		function syncDirtyState() {
			const dirty = handlers.isFieldDirty(spec.fieldId) === true;
			row.classList.toggle("is-dirty", dirty);
			badge.classList.toggle("is-hidden", dirty !== true);
			applyBtn.disabled = dirty !== true;
		}
		applyBtn.addEventListener("click", function () {
			handlers.onFieldApply(spec);
			syncDirtyState();
		});
		input.addEventListener("input", function () {
			syncDirtyState();
		});
		footer.appendChild(applyBtn);
		row.appendChild(footer);
		mount.appendChild(row);
		syncDirtyState();
	}

	function renderForm(opts) {
		const mount = opts && opts.mount;
		const step = opts && opts.step;
		const handlers = (opts && opts.handlers) || {};
		if (!mount || !step) return;
		clear(mount);
		const specs = buildFieldSpecs(step);
		specs.forEach(function (spec) {
			renderField(mount, spec, step, handlers);
		});
		const note = el(
			"div",
			"flowStepModalFormNote",
			"JSON view edits the full selected step and supports adding unknown keys.",
		);
		mount.appendChild(note);
	}

	W.AM2FlowStepModalForm = {
		buildFieldSpecs: buildFieldSpecs,
		renderForm: renderForm,
	};
})();
