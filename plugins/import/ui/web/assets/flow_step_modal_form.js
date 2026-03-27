(function () {
	"use strict";

	/** @typedef {AM2FlowStepFieldSpec & {
	 * 	label: string,
	 * 	editor: string,
	 * }} AM2FlowStepModalRenderSpec */

	/** @type {Window} */
	const W = window;

	/** @param {Node | null | undefined} node */
	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	/**
	 * @param {string} tag
	 * @param {string | null | undefined} [cls]
	 * @param {string | number | boolean | null | undefined} [textValue]
	 * @returns {HTMLElement}
	 */
	function el(tag, cls, textValue) {
		const node = document.createElement(tag);
		if (cls) node.className = cls;
		if (textValue !== undefined) node.textContent = String(textValue);
		return node;
	}

	/** @template T
	 * @param {T} value
	 * @returns {T}
	 */
	function safeClone(value) {
		return JSON.parse(JSON.stringify(value));
	}

	/** @param {AM2JsonObject} step
	 * @returns {AM2JsonObject}
	 */
	function readStepOp(step) {
		return step &&
			step.op &&
			typeof step.op === "object" &&
			!Array.isArray(step.op)
			? /** @type {AM2JsonObject} */ (step.op)
			: {};
	}

	/** @param {AM2JsonObject} step
	 * @returns {AM2JsonObject}
	 */
	function readStepInputs(step) {
		const op = readStepOp(step);
		return op.inputs &&
			typeof op.inputs === "object" &&
			!Array.isArray(op.inputs)
			? /** @type {AM2JsonObject} */ (op.inputs)
			: {};
	}

	/**
	 * @param {AM2JsonObject} step
	 * @param {string} key
	 * @returns {AM2JsonValue}
	 */
	function readInputValue(step, key) {
		const inputs = readStepInputs(step);
		return safeClone(inputs[key]);
	}

	/**
	 * @param {string} key
	 * @param {AM2JsonValue} value
	 * @returns {string}
	 */
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

	/** @param {AM2JsonObject} step
	 * @returns {AM2FlowStepModalRenderSpec[]}
	 */
	function buildFieldSpecs(step) {
		/** @type {AM2FlowStepModalRenderSpec[]} */
		const specs = [
			{
				fieldId: "core:step_id",
				label: "step_id",
				editor: "text",
				getValue: function (node) {
					return String(node.step_id || "");
				},
			},
			{
				fieldId: "core:primitive_id",
				label: "primitive_id",
				editor: "text",
				getValue: function (node) {
					return String(readStepOp(node).primitive_id || "");
				},
			},
			{
				fieldId: "core:primitive_version",
				label: "primitive_version",
				editor: "number",
				getValue: function (node) {
					const op = readStepOp(node);
					return String(
						op.primitive_version === undefined ? "" : op.primitive_version,
					);
				},
			},
		];
		const inputs = readStepInputs(step);
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
						return editor === "json"
							? JSON.stringify(value === undefined ? null : value, null, 2)
							: String(value === undefined ? "" : value);
					},
				});
			});
		specs.push({
			fieldId: "writes",
			label: "writes",
			editor: "json",
			getValue: function (node) {
				const op = readStepOp(node);
				const writes = Array.isArray(op.writes) ? op.writes : [];
				return JSON.stringify(writes, null, 2);
			},
		});
		return specs;
	}

	/**
	 * @param {AM2FlowStepModalRenderSpec} spec
	 * @param {AM2JsonValue} value
	 * @param {AM2FlowStepModalFormHandlers} handlers
	 * @returns {HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement}
	 */
	function renderInput(spec, value, handlers) {
		/** @type {HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement} */
		let input = document.createElement("input");
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

	/**
	 * @param {HTMLElement} mount
	 * @param {AM2FlowStepModalRenderSpec} spec
	 * @param {AM2FlowStepModalFormHandlers} handlers
	 */
	function renderField(mount, spec, handlers) {
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
		const applyBtn = /** @type {HTMLButtonElement} */ (
			el("button", "btn", "Apply")
		);
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

	/** @param {{
	 * 	mount: HTMLElement | null,
	 * 	step: AM2JsonObject | null,
	 * 	handlers?: AM2FlowStepModalFormHandlers | undefined,
	 * } | null | undefined} opts */
	function renderForm(opts) {
		const mount = opts && opts.mount;
		const step = opts && opts.step;
		const handlers = (opts && opts.handlers) || {
			isFieldDirty: function () {
				return false;
			},
			readFieldValue: function () {
				return "";
			},
			onFieldApply: function () {},
			onFieldInput: function () {},
		};
		if (!mount || !step) return;
		clear(mount);
		buildFieldSpecs(step).forEach(function (spec) {
			renderField(mount, spec, handlers);
		});
		mount.appendChild(
			el(
				"div",
				"flowStepModalFormNote",
				"JSON view edits the full selected step and supports adding unknown keys.",
			),
		);
	}

	W.AM2FlowStepModalForm = {
		buildFieldSpecs: buildFieldSpecs,
		renderForm: renderForm,
	};
})();
