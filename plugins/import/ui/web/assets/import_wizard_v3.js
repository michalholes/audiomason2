(() => {
	/** @typedef {Node & {
	 *   attrs?: Record<string, string>,
	 *   children?: Node[] | HTMLCollection,
	 *   childNodes?: NodeListOf<ChildNode> | Node[],
	 *   dataset?: DOMStringMap,
	 *   checked?: boolean,
	 *   value?: string,
	 *   type?: string,
	 *   tag?: string,
	 *   tagName?: string,
	 *   appendChild?: (child: Node) => Node,
	 *   removeChild?: (child: Node) => Node,
	 *   setAttribute?: (name: string, value: string) => void,
	 *   getAttribute?: (name: string) => string | null,
	 *   addEventListener?: (type: string, handler: EventListenerOrEventListenerObject) => void,
	 *   oninput?: ((event: Event) => void) | null,
	 *   onchange?: ((event: Event) => void) | null,
	 *   onclick?: ((event: Event) => void) | null,
	 * }} AM2PromptNode */
	/**
	 * @typedef {(tag: string,
	 *   attrs?: Record<string, string | number | boolean | null | undefined> | null,
	 *   children?: Node[] | null) => HTMLElement} AM2PromptElementFactory
	 */
	/** @typedef {(node: AM2PromptNode) => boolean} AM2PromptPredicate */
	/** @typedef {{
	 *   body: HTMLElement,
	 *   bodyState?: AM2ImportPromptBodyState | null,
	 *   context: AM2ImportStepContext,
	 *   el?: AM2PromptElementFactory,
	 *   localDraft?: AM2JsonValue | null,
	 *   makeEl: AM2PromptElementFactory,
	 *   mode?: string,
	 *   model: AM2ImportPromptModel,
	 *   mount?: HTMLElement,
	 *   mountState?: AM2ImportWizardV3MountState,
	 *   sameStep?: boolean,
	 *   step?: AM2ImportWizardStep | null,
	 * }} AM2PromptRenderArgs */
	/** @typedef {{
	 *   actions: HTMLElement,
	 *   editor: HTMLElement,
	 *   filterInput: HTMLInputElement | null,
	 *   list: HTMLElement,
	 *   summary: HTMLElement,
	 *   wrapper: HTMLElement,
	 * }} AM2ChecklistShell */

	const root = /** @type {(Window & typeof globalThis) & {
	 *   AM2ImportWizardV3?: AM2ImportWizardV3Api,
	 *   AM2ImportWizardV3Helpers?: AM2ImportWizardV3HelpersApi,
	 * }} */ (typeof window !== "undefined" ? window : globalThis);
	/** @type {Record<string, string>} */
	const PROMPT_PAYLOAD_KEYS = {
		"ui.prompt_text": "value",
		"ui.prompt_select": "selection",
		"ui.prompt_confirm": "confirmed",
	};
	/** @type {WeakMap<HTMLElement, AM2ImportWizardV3MountState>} */
	const mountStates = new WeakMap();

	/** @param {AM2ImportWizardState | null | undefined} state */
	function isV3State(state) {
		return !!(
			state &&
			state.effective_model &&
			state.effective_model.flowmodel_kind === "dsl_step_graph_v3"
		);
	}

	/** @param {AM2ImportWizardStep | null | undefined} step */
	function isPromptStep(step) {
		if (!step || typeof step !== "object") return false;
		const primitiveId = String(step.primitive_id || "");
		const primitiveVersion = Number(step.primitive_version || 0);
		return primitiveVersion === 1 && primitiveId in PROMPT_PAYLOAD_KEYS;
	}

	/**
	 * @param {AM2ImportWizardState | null | undefined} state
	 * @returns {AM2ImportWizardStep | null}
	 */
	function findCurrentStep(state) {
		if (!isV3State(state)) return null;
		const model = state.effective_model;
		const steps = Array.isArray(model.steps) ? model.steps : [];
		const currentStepId = String(state.current_step_id || "");
		return steps.find((step) => step && step.step_id === currentStepId) || null;
	}

	/** @param {AM2ImportWizardState | null | undefined} state */
	function canRenderCurrentStep(state) {
		if (!isV3State(state)) return false;
		if (!state || state.status !== "in_progress") return false;
		return isPromptStep(findCurrentStep(state));
	}

	/** @param {unknown} items @returns {AM2ImportPromptDisplayItem[]} */
	function normalizeDisplayItems(items) {
		if (!Array.isArray(items)) return [];
		return items
			.filter((item) => item && typeof item === "object")
			.map((item) => ({
				item_id: typeof item.item_id === "string" ? item.item_id : "",
				label:
					typeof item.display_label === "string"
						? item.display_label
						: typeof item.label === "string"
							? item.label
							: typeof item.item_id === "string"
								? item.item_id
								: "",
			}));
	}

	/** @param {AM2ImportWizardStep | null | undefined} step @returns {AM2ImportPromptModel | null} */
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
			items: normalizeDisplayItems(ui.items),
			default_value: Object.prototype.hasOwnProperty.call(ui, "default_value")
				? ui.default_value
				: null,
			prefill: Object.prototype.hasOwnProperty.call(ui, "prefill")
				? ui.prefill
				: null,
		};
	}

	/** @param {HTMLElement} mount @returns {AM2ImportWizardV3MountState} */
	function getMountState(mount) {
		let state = mountStates.get(mount);
		if (!state) {
			state = { body: null, bodyState: null };
			mountStates.set(mount, state);
		}
		return state;
	}

	/** @param {AM2ImportWizardState | null | undefined} state @returns {AM2ImportStepContext} */
	function snapshotContext(state) {
		return {
			session_id: String((state && state.session_id) || ""),
			current_step_id: String((state && state.current_step_id) || ""),
			status: String((state && state.status) || ""),
		};
	}

	/**
	 * @param {AM2ImportStepContext | null | undefined} left
	 * @param {AM2ImportStepContext | null | undefined} right
	 */
	function sameActiveContext(left, right) {
		return !!(
			left &&
			right &&
			left.session_id === right.session_id &&
			left.current_step_id === right.current_step_id &&
			left.status === "in_progress" &&
			right.status === "in_progress"
		);
	}

	/**
	 * @param {AM2ImportStepContext | null | undefined} left
	 * @param {AM2ImportStepContext | null | undefined} right
	 */
	function sameStepContext(left, right) {
		return !!(
			left &&
			right &&
			left.session_id === right.session_id &&
			left.current_step_id === right.current_step_id
		);
	}

	/** @param {AM2JsonValue | undefined} value */
	function isScalar(value) {
		return (
			typeof value === "string" ||
			typeof value === "number" ||
			typeof value === "boolean"
		);
	}

	/** @param {AM2ImportPromptModel} model @returns {AM2JsonValue} */
	function seedValue(model) {
		return model && model.prefill !== null
			? model.prefill
			: model.default_value;
	}

	/** @param {AM2JsonValue | undefined} value */
	function serializeSeed(value) {
		if (value === null || value === undefined) return "";
		if (isScalar(value)) return String(value);
		try {
			return JSON.stringify(value, null, 2);
		} catch {
			return String(value);
		}
	}

	/** @param {string} raw @returns {AM2JsonValue | string} */
	function parseLooseJson(raw) {
		if (raw === "") return "";
		try {
			return JSON.parse(raw);
		} catch {
			return raw;
		}
	}

	/** @param {AM2ImportPromptModel} model */
	function isNumericPrompt(model) {
		const seed = seedValue(model);
		if (typeof seed !== "number") return false;
		return model.examples.every((example) => typeof example === "number");
	}

	/** @param {AM2ImportPromptModel | null | undefined} model */
	function isDropdownSelect(model) {
		if (!model || model.primitive_id !== "ui.prompt_select") return false;
		if (model.items.length !== 0) return false;
		if (model.examples.length === 0 || model.examples.length > 8) return false;
		return model.examples.every(isScalar);
	}

	/** @param {AM2ImportPromptModel | null | undefined} model */
	function isChecklistSelect(model) {
		return (
			model &&
			model.primitive_id === "ui.prompt_select" &&
			model.items.length > 0
		);
	}

	/** @param {AM2ImportPromptModel | null | undefined} model */
	function classifyPromptMode(model) {
		if (!model) return "";
		if (model.primitive_id === "ui.prompt_confirm") return "confirm";
		if (isChecklistSelect(model)) {
			return model.items.length > 12 ? "filterable-checklist" : "checklist";
		}
		if (isDropdownSelect(model)) return "dropdown";
		const seed = seedValue(model);
		if (seed && typeof seed === "object") return "textarea";
		if (isNumericPrompt(model)) return "number";
		return "text";
	}

	const promptHelpers = /** @type {AM2ImportWizardV3HelpersApi | undefined} */ (
		Reflect.get(root, "AM2ImportWizardV3Helpers")
	);
	if (!promptHelpers) return;
	const {
		childNodes,
		tagName,
		getAttr,
		setAttr,
		addEvent,
		clearMount,
		walkNodes,
		findNode,
		findNodes,
		findBodyMount,
		ensureBodyMount,
		markDirty,
		serializeDropdownValue,
		selectionSetFromExpr,
		selectionExprFromSet,
		extractLocalDraft,
		resolveSelectionSeed,
		visibleItemIndices,
		appendHint,
		renderExamplesList,
		createInputNode,
		ensureTextEditor,
		bindTextEditor,
	} = promptHelpers;

	/** @param {AM2PromptRenderArgs} args @returns {AM2ImportPromptBodyState} */
	function renderTextLike(args) {
		const { body, bodyState, makeEl, mode, model, localDraft, sameStep } = args;
		const key =
			PROMPT_PAYLOAD_KEYS[
				/** @type {keyof typeof PROMPT_PAYLOAD_KEYS} */ (model.primitive_id)
			];
		const next = {
			context: args.context,
			dirty: sameStep ? bodyState && bodyState.dirty : false,
			editor: ensureTextEditor(bodyState, makeEl, mode, key),
			mode,
			model,
			primitive_id: model.primitive_id,
			selectionSet: /** @type {Set<number> | null} */ (null),
		};
		bindTextEditor(next.editor, next);
		const seedText =
			next.dirty && localDraft !== null
				? String(localDraft)
				: serializeSeed(seedValue(model));
		next.editor.value = seedText;
		body.appendChild(next.editor);
		if (
			model.primitive_id === "ui.prompt_select" &&
			model.items.length === 0 &&
			!isDropdownSelect(model) &&
			model.examples.length > 0
		) {
			const helpers = makeEl("div", { class: "hint" });
			model.examples.forEach((example) => {
				const button = makeEl("button", {
					type: "button",
					text: serializeSeed(example),
				});
				addEvent(button, "click", () => {
					next.editor.value = serializeSeed(example);
					markDirty(next);
				});
				helpers.appendChild(button);
			});
			body.appendChild(helpers);
		}
		return next;
	}

	/**
	 * @param {AM2ImportPromptBodyState | null | undefined} bodyState
	 * @param {AM2PromptElementFactory} makeEl
	 * @param {string} key
	 */
	function ensureDropdownEditor(bodyState, makeEl, key) {
		if (bodyState && bodyState.mode === "dropdown" && bodyState.editor) {
			return /** @type {HTMLSelectElement} */ (bodyState.editor);
		}
		return /** @type {HTMLSelectElement} */ (
			makeEl("select", { "data-v3-payload-key": key })
		);
	}

	/** @param {AM2PromptRenderArgs} args @returns {AM2ImportPromptBodyState} */
	function renderDropdown(args) {
		const { body, bodyState, makeEl, model, localDraft, sameStep } = args;
		const key =
			PROMPT_PAYLOAD_KEYS[
				/** @type {keyof typeof PROMPT_PAYLOAD_KEYS} */ (model.primitive_id)
			];
		const editor = ensureDropdownEditor(bodyState, makeEl, key);
		clearMount(editor);
		model.examples.forEach((example) => {
			const option = makeEl("option", {
				value: serializeDropdownValue(example),
				text: serializeSeed(example),
			});
			editor.appendChild(option);
		});
		const next = {
			context: args.context,
			dirty: sameStep ? bodyState && bodyState.dirty : false,
			editor,
			mode: "dropdown",
			model,
			primitive_id: model.primitive_id,
			selectionSet: /** @type {Set<number> | null} */ (null),
		};
		addEvent(editor, "change", () => markDirty(next));
		addEvent(editor, "input", () => markDirty(next));
		const chosen =
			next.dirty && localDraft !== null
				? serializeDropdownValue(parseLooseJson(String(localDraft)))
				: serializeDropdownValue(seedValue(model));
		editor.value = chosen;
		body.appendChild(editor);
		return next;
	}

	/**
	 * @param {AM2PromptElementFactory} makeEl
	 * @param {boolean} filterable
	 * @returns {AM2ChecklistShell}
	 */
	function createChecklistShell(makeEl, filterable) {
		const wrapper = makeEl("div", { "data-v3-payload-key": "selection" });
		const summary = makeEl("div", { class: "hint" });
		const actions = makeEl("div", { class: "hint" });
		const list = makeEl("div", { class: "hint" });
		const filterInput = filterable
			? /** @type {HTMLInputElement} */ (
					makeEl("input", { type: "text", placeholder: "Filter" })
				)
			: null;
		return { actions, editor: wrapper, filterInput, list, summary, wrapper };
	}

	/**
	 * @param {AM2ImportPromptBodyState | null | undefined} bodyState
	 * @param {AM2PromptElementFactory} makeEl
	 * @param {boolean} filterable
	 * @returns {AM2ChecklistShell}
	 */
	function ensureChecklistState(bodyState, makeEl, filterable) {
		const mode = filterable ? "filterable-checklist" : "checklist";
		if (bodyState && bodyState.mode === mode && bodyState.editor) {
			return {
				actions: /** @type {HTMLElement} */ (bodyState.actions),
				editor: /** @type {HTMLElement} */ (bodyState.editor),
				filterInput: bodyState.filterInput || null,
				list: /** @type {HTMLElement} */ (bodyState.list),
				summary: /** @type {HTMLElement} */ (bodyState.summary),
				wrapper: /** @type {HTMLElement} */ (
					bodyState.wrapper || bodyState.editor
				),
			};
		}
		return createChecklistShell(makeEl, filterable);
	}

	/** @param {AM2PromptRenderArgs} args @returns {AM2ImportPromptBodyState} */
	function renderChecklist(args) {
		const {
			body,
			bodyState,
			context,
			makeEl,
			model,
			mode,
			localDraft,
			sameStep,
		} = args;
		const filterable = mode === "filterable-checklist";
		const shell = ensureChecklistState(bodyState, makeEl, filterable);
		const dirty = sameStep ? bodyState && bodyState.dirty : false;
		const filterDirty = sameStep ? bodyState && bodyState.filterDirty : false;
		const filterText =
			filterDirty && bodyState && bodyState.filterInput
				? String(bodyState.filterInput.value || "")
				: "";
		const next = {
			actions: shell.actions,
			context,
			dirty,
			editor: shell.wrapper || shell.editor,
			filterDirty,
			filterInput: shell.filterInput,
			list: shell.list,
			mode,
			model,
			primitive_id: model.primitive_id,
			selectionSet:
				dirty && bodyState && bodyState.selectionSet instanceof Set
					? new Set(bodyState.selectionSet)
					: selectionSetFromExpr(
							resolveSelectionSeed(model, localDraft),
							model.items.length,
						),
			summary: shell.summary,
		};
		if (shell.filterInput) {
			shell.filterInput.value = filterText;
			addEvent(shell.filterInput, "input", () => {
				next.filterDirty = true;
				renderChecklist({
					body,
					bodyState: next,
					context,
					mountState: args.mountState,
					localDraft: selectionExprFromSet(
						next.selectionSet,
						model.items.length,
					),
					makeEl,
					mode,
					model,
					sameStep: true,
				});
			});
		}
		clearMount(shell.editor || shell.wrapper);
		shell.summary.textContent = `Selected ${next.selectionSet.size} of ${model.items.length}`;
		(shell.editor || shell.wrapper).appendChild(shell.summary);
		if (shell.filterInput) {
			(shell.editor || shell.wrapper).appendChild(shell.filterInput);
		}
		clearMount(shell.actions);
		const actionSpecs = shell.filterInput
			? [
					["Select visible", true, true],
					["Clear visible", false, true],
					["Select all", true, false],
					["Clear all", false, false],
				]
			: [
					["Select all", true, false],
					["Clear all", false, false],
				];
		actionSpecs.forEach(([label, checked, onlyVisible]) => {
			const button = makeEl("button", { text: label, type: "button" });
			addEvent(button, "click", () => {
				const indices = onlyVisible
					? visibleItemIndices(
							model,
							shell.filterInput ? shell.filterInput.value : "",
						)
					: model.items.map((_, index) => index);
				for (const index of indices) {
					if (checked) next.selectionSet.add(index);
					else next.selectionSet.delete(index);
				}
				next.dirty = true;
				renderChecklist({
					body,
					bodyState: next,
					context,
					mountState: args.mountState,
					localDraft: selectionExprFromSet(
						next.selectionSet,
						model.items.length,
					),
					makeEl,
					mode,
					model,
					sameStep: true,
				});
			});
			shell.actions.appendChild(button);
		});
		(shell.editor || shell.wrapper).appendChild(shell.actions);
		clearMount(shell.list);
		for (const index of visibleItemIndices(
			model,
			shell.filterInput ? shell.filterInput.value : "",
		)) {
			const item = model.items[index];
			const row = makeEl("label", { class: "choiceItem" });
			const checkbox = /** @type {HTMLInputElement} */ (
				makeEl("input", { type: "checkbox" })
			);
			checkbox.checked = next.selectionSet.has(index);
			addEvent(checkbox, "change", () => {
				if (checkbox.checked) next.selectionSet.add(index);
				else next.selectionSet.delete(index);
				next.dirty = true;
				renderChecklist({
					body,
					bodyState: next,
					context,
					mountState: args.mountState,
					localDraft: selectionExprFromSet(
						next.selectionSet,
						model.items.length,
					),
					makeEl,
					mode,
					model,
					sameStep: true,
				});
			});
			row.appendChild(checkbox);
			row.appendChild(
				makeEl("span", { text: item.label || item.item_id || "" }),
			);
			shell.list.appendChild(row);
		}
		(shell.editor || shell.wrapper).appendChild(shell.list);
		body.appendChild(shell.editor || shell.wrapper);
		next.editor = shell.editor || shell.wrapper;
		if (args.mountState) args.mountState.bodyState = next;
		return next;
	}

	/** @param {AM2PromptRenderArgs} args @returns {AM2ImportPromptBodyState} */
	function renderConfirm(args) {
		const { body, bodyState, context, makeEl, model, sameStep } = args;
		let row = null;
		let checkbox = null;
		if (
			bodyState &&
			bodyState.mode === "confirm" &&
			bodyState.row &&
			bodyState.editor
		) {
			row = bodyState.row;
			checkbox = bodyState.editor;
		} else {
			row = makeEl("label", { class: "choiceItem" });
			checkbox = /** @type {HTMLInputElement} */ (
				makeEl("input", {
					type: "checkbox",
					"data-v3-payload-key": "confirmed",
				})
			);
			row.appendChild(checkbox);
			row.appendChild(makeEl("span", { text: "" }));
		}
		const next = {
			context,
			dirty: sameStep ? bodyState && bodyState.dirty : false,
			editor: checkbox,
			mode: "confirm",
			model,
			primitive_id: model.primitive_id,
			row,
			selectionSet: /** @type {Set<number> | null} */ (null),
		};
		addEvent(checkbox, "change", () => markDirty(next));
		if (!next.dirty)
			/** @type {HTMLInputElement} */ (checkbox).checked =
				seedValue(model) === true;
		let labelNode = null;
		for (const entry of childNodes(row)) {
			if (tagName(entry) === "span") {
				labelNode = entry;
				break;
			}
		}
		if (labelNode) {
			labelNode.textContent =
				model.prompt || model.label || model.title || "Confirm";
		}
		body.appendChild(row);
		return next;
	}

	/**
	 * @param {{
	 *   context: AM2ImportStepContext,
	 *   el: AM2PromptElementFactory,
	 *   model: AM2ImportPromptModel,
	 *   mount: HTMLElement,
	 *   step?: AM2ImportWizardStep | null,
	 * }} args
	 */
	function renderPromptBody(args) {
		const body = ensureBodyMount(args.mount, args.el);
		/** @type {AM2ImportWizardV3MountState} */
		const mountState = getMountState(args.mount);
		const previous = mountState.bodyState;
		const sameStep = sameStepContext(
			previous && previous.context,
			args.context,
		);
		const localDraft = sameStep ? extractLocalDraft(previous) : null;
		const mode = classifyPromptMode(args.model);
		clearMount(body);
		if (args.model.label) {
			body.appendChild(
				args.el("div", { class: "fieldName", text: args.model.label }),
			);
		}
		appendHint(
			body,
			args.el,
			args.model.prompt || args.model.label || args.model.title,
			"hint",
		);
		appendHint(body, args.el, args.model.help, "hint");
		appendHint(body, args.el, args.model.hint, "hint");
		if (!isChecklistSelect(args.model) && args.model.examples.length) {
			renderExamplesList(body, args.el, args.model.examples);
		}
		let next = null;
		if (mode === "confirm") {
			next = renderConfirm({
				body,
				bodyState: previous,
				context: args.context,
				makeEl: args.el,
				model: args.model,
				sameStep,
			});
		} else if (mode === "dropdown") {
			next = renderDropdown({
				body,
				bodyState: previous,
				context: args.context,
				localDraft,
				makeEl: args.el,
				model: args.model,
				sameStep,
			});
		} else if (mode === "checklist" || mode === "filterable-checklist") {
			next = renderChecklist({
				body,
				bodyState: previous,
				context: args.context,
				mountState,
				localDraft,
				makeEl: args.el,
				mode,
				model: args.model,
				sameStep,
			});
		} else {
			next = renderTextLike({
				body,
				bodyState: previous,
				context: args.context,
				localDraft,
				makeEl: args.el,
				mode,
				model: args.model,
				sameStep,
			});
		}
		mountState.body = body;
		mountState.bodyState = next;
		return true;
	}

	/**
	 * @param {AM2ImportWizardState | null | undefined} state
	 * @returns {Promise<AM2ImportWizardStep | null>}
	 */
	async function fetchCurrentStepProjection(state) {
		if (!state || !state.session_id || !state.current_step_id || !root.fetch) {
			return null;
		}
		const sid = encodeURIComponent(String(state.session_id || ""));
		const stepId = encodeURIComponent(String(state.current_step_id || ""));
		const response = await root.fetch(
			`/import/ui/session/${sid}/step/${stepId}`,
		);
		const text = await response.text();
		if (!response.ok) return null;
		try {
			return JSON.parse(text || "{}");
		} catch {
			return null;
		}
	}

	/**
	 * @param {{
	 *   state?: AM2ImportWizardState | null,
	 *   mount?: HTMLElement | null,
	 *   el?: AM2PromptElementFactory | null,
	 *   getLiveContext?: (() => AM2ImportStepContext | null) | null,
	 * } | null | undefined} args
	 */
	function renderCurrentStep(args) {
		const state = args && args.state ? args.state : null;
		const mount = args && args.mount ? args.mount : null;
		const makeEl =
			args && typeof args.el === "function"
				? /** @type {AM2PromptElementFactory} */ (args.el)
				: null;
		const getLiveContext =
			args && typeof args.getLiveContext === "function"
				? /** @type {() => AM2ImportStepContext | null} */ (args.getLiveContext)
				: null;
		if (!mount || !makeEl || !canRenderCurrentStep(state)) return false;
		const step = findCurrentStep(state);
		const model = buildPromptModel(step);
		if (!model) return false;
		const context = snapshotContext(state);
		renderPromptBody({ context, el: makeEl, model, mount, step });
		void fetchCurrentStepProjection(state).then((projectedStep) => {
			if (!isPromptStep(projectedStep)) return;
			const liveContext = getLiveContext ? getLiveContext() : context;
			if (!sameActiveContext(context, liveContext)) return;
			const projectedModel = buildPromptModel(projectedStep);
			if (!projectedModel) return;
			renderPromptBody({
				context: liveContext,
				el: makeEl,
				model: projectedModel,
				mount,
				step: projectedStep,
			});
		});
		return true;
	}

	/** @param {HTMLElement} mount @returns {AM2JsonValue} */
	function fallbackCollectSelect(mount) {
		/** @param {AM2PromptNode} node */
		function isSelectionPayloadNode(node) {
			return getAttr(node, "data-v3-payload-key") === "selection";
		}
		const payload = findNode(mount, isSelectionPayloadNode);
		if (!payload) return "";
		if (tagName(payload) === "select") {
			return parseLooseJson(String(payload.value || ""));
		}
		/** @param {AM2PromptNode} node */
		function isSelectionCheckbox(node) {
			return tagName(node) === "input" && getAttr(node, "type") === "checkbox";
		}
		const rows = findNodes(payload, isSelectionCheckbox);
		/** @type {number[]} */
		const picks = [];
		for (const [index, checkbox] of rows.entries()) {
			if (checkbox.checked) picks.push(index);
		}
		return selectionExprFromSet(new Set(picks), rows.length);
	}

	/**
	 * @param {{
	 *   mount?: HTMLElement | null,
	 *   step?: AM2ImportWizardStep | null,
	 * } | null | undefined} args
	 * @returns {Record<string, AM2JsonValue>}
	 */
	function collectPayload(args) {
		const mount = args && args.mount ? args.mount : null;
		const step = args && args.step ? args.step : null;
		if (!mount || !isPromptStep(step)) return {};
		const primitiveId = String(step.primitive_id || "");
		const key =
			PROMPT_PAYLOAD_KEYS[
				/** @type {keyof typeof PROMPT_PAYLOAD_KEYS} */ (primitiveId)
			];
		const mountState = getMountState(mount);
		const bodyState = mountState.bodyState;
		if (
			bodyState &&
			bodyState.context &&
			String(step.step_id || "") === bodyState.context.current_step_id
		) {
			if (primitiveId === "ui.prompt_confirm") {
				return {
					[key]: !!(
						bodyState.editor &&
						/** @type {HTMLInputElement} */ (bodyState.editor).checked
					),
				};
			}
			if (
				bodyState.mode === "checklist" ||
				bodyState.mode === "filterable-checklist"
			) {
				return {
					[key]: selectionExprFromSet(
						bodyState.selectionSet,
						bodyState.model.items.length,
					),
				};
			}
			return {
				[key]: parseLooseJson(
					String(
						(bodyState.editor &&
							/** @type {HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement} */ (
								bodyState.editor
							).value) ||
							"",
					),
				),
			};
		}
		if (primitiveId === "ui.prompt_select")
			return { [key]: fallbackCollectSelect(mount) };
		/** @param {AM2PromptNode} entry */
		function matchesPayloadKey(entry) {
			return getAttr(entry, "data-v3-payload-key") === key;
		}
		const node = findNode(mount, matchesPayloadKey);
		if (!node) return {};
		if (primitiveId === "ui.prompt_confirm") return { [key]: !!node.checked };
		return { [key]: parseLooseJson(String(node.value || "")) };
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
