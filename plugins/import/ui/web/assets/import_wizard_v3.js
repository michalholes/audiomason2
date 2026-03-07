(() => {
	const root = typeof window !== "undefined" ? window : globalThis;
	const PROMPT_PAYLOAD_KEYS = {
		"ui.prompt_text": "value",
		"ui.prompt_select": "selection",
		"ui.prompt_confirm": "confirmed",
	};

	function isV3State(state) {
		return !!(
			state &&
			state.effective_model &&
			state.effective_model.flowmodel_kind === "dsl_step_graph_v3"
		);
	}

	function isPromptStep(step) {
		if (!step || typeof step !== "object") return false;
		const primitiveId = String(step.primitive_id || "");
		const primitiveVersion = Number(step.primitive_version || 0);
		return primitiveVersion === 1 && primitiveId in PROMPT_PAYLOAD_KEYS;
	}

	function findCurrentStep(state) {
		if (!isV3State(state)) return null;
		const model = state.effective_model;
		const steps = Array.isArray(model.steps) ? model.steps : [];
		const currentStepId = String(state.current_step_id || "");
		return steps.find((step) => step && step.step_id === currentStepId) || null;
	}

	function canRenderCurrentStep(state) {
		if (!isV3State(state)) return false;
		if (!state || state.status !== "in_progress") return false;
		return isPromptStep(findCurrentStep(state));
	}

	function buildPromptModel(step) {
		if (!isPromptStep(step)) return null;
		const ui = step && typeof step.ui === "object" ? step.ui : {};
		return {
			step_id: String(step.step_id || ""),
			primitive_id: String(step.primitive_id || ""),
			title:
				step && step.title ? String(step.title) : String(step.step_id || ""),
			label: typeof ui.label === "string" ? ui.label : "",
			prompt: typeof ui.prompt === "string" ? ui.prompt : "",
			help: typeof ui.help === "string" ? ui.help : "",
			hint: typeof ui.hint === "string" ? ui.hint : "",
			examples: Array.isArray(ui.examples) ? ui.examples.slice() : [],
			default_value: Object.prototype.hasOwnProperty.call(ui, "default_value")
				? ui.default_value
				: null,
			prefill: Object.prototype.hasOwnProperty.call(ui, "prefill")
				? ui.prefill
				: null,
		};
	}

	function renderCurrentStep(args) {
		const state = args && args.state ? args.state : null;
		const mount = args && args.mount ? args.mount : null;
		const makeEl = args && typeof args.el === "function" ? args.el : null;
		if (!mount || !makeEl || !canRenderCurrentStep(state)) return false;
		const step = findCurrentStep(state);
		const model = buildPromptModel(step);
		if (!model) return false;
		const promptText = model.prompt || model.label || model.title;
		const seed = model.prefill !== null ? model.prefill : model.default_value;
		const seedText = serializeSeed(seed);

		if (model.label) {
			mount.appendChild(
				makeEl("div", { class: "fieldName", text: model.label }),
			);
		}
		if (promptText) {
			mount.appendChild(makeEl("div", { class: "hint", text: promptText }));
		}
		if (model.help) {
			mount.appendChild(makeEl("div", { class: "hint", text: model.help }));
		}
		if (model.hint) {
			mount.appendChild(makeEl("div", { class: "hint", text: model.hint }));
		}
		if (model.examples.length) {
			const list = makeEl("ul", { class: "hint" });
			model.examples.forEach((example) => {
				list.appendChild(makeEl("li", { text: serializeSeed(example) }));
			});
			mount.appendChild(list);
		}
		if (seed !== null) {
			mount.appendChild(
				makeEl("div", { class: "hint", text: `Prefill: ${seedText}` }),
			);
		}

		const primitiveId = String(step.primitive_id || "");
		if (primitiveId === "ui.prompt_confirm") {
			const row = makeEl("label", { class: "choiceItem" });
			const checkbox = makeEl("input", {
				type: "checkbox",
				"data-v3-payload-key": "confirmed",
			});
			checkbox.checked = seed === true;
			row.appendChild(checkbox);
			row.appendChild(makeEl("span", { text: promptText || "Confirm" }));
			mount.appendChild(row);
			return true;
		}

		const multiline = seed !== null && typeof seed === "object";
		const input = multiline
			? makeEl("textarea", {
					rows: "6",
					"data-v3-payload-key": PROMPT_PAYLOAD_KEYS[primitiveId],
				})
			: makeEl("input", {
					"data-v3-payload-key": PROMPT_PAYLOAD_KEYS[primitiveId],
				});
		input.value = seedText;
		mount.appendChild(input);
		return true;
	}

	function collectPayload(args) {
		const mount = args && args.mount ? args.mount : null;
		const step = args && args.step ? args.step : null;
		if (!mount || !isPromptStep(step)) return {};
		const primitiveId = String(step.primitive_id || "");
		const key = PROMPT_PAYLOAD_KEYS[primitiveId];
		const node = mount.querySelector("[data-v3-payload-key]");
		if (!node || !key) return {};
		if (primitiveId === "ui.prompt_confirm") {
			return { [key]: !!node.checked };
		}
		return { [key]: parseLooseJson(String(node.value || "")) };
	}

	function serializeSeed(value) {
		if (value === null || value === undefined) return "";
		if (
			typeof value === "boolean" ||
			typeof value === "number" ||
			typeof value === "string"
		) {
			return String(value);
		}
		try {
			return JSON.stringify(value, null, 2);
		} catch {
			return String(value);
		}
	}

	function parseLooseJson(raw) {
		if (raw === "") return "";
		try {
			return JSON.parse(raw);
		} catch {
			return raw;
		}
	}

	root.AM2ImportWizardV3 = {
		buildPromptModel,
		canRenderCurrentStep,
		collectPayload,
		findCurrentStep,
		isPromptStep,
		isV3State,
		renderCurrentStep,
	};
})();
