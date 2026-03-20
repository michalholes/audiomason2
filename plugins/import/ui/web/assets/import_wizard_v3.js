(() => {
	const root = typeof window !== "undefined" ? window : globalThis;
	const PROMPT_PAYLOAD_KEYS = {
		"ui.prompt_text": "value",
		"ui.prompt_select": "selection",
		"ui.prompt_confirm": "confirmed",
	};
	const mountStates = new WeakMap();

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

	function getMountState(mount) {
		let state = mountStates.get(mount);
		if (!state) {
			state = { body: null, bodyState: null };
			mountStates.set(mount, state);
		}
		return state;
	}

	function snapshotContext(state) {
		return {
			session_id: String((state && state.session_id) || ""),
			current_step_id: String((state && state.current_step_id) || ""),
			status: String((state && state.status) || ""),
		};
	}

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

	function sameStepContext(left, right) {
		return !!(
			left &&
			right &&
			left.session_id === right.session_id &&
			left.current_step_id === right.current_step_id
		);
	}

	function isScalar(value) {
		return (
			typeof value === "string" ||
			typeof value === "number" ||
			typeof value === "boolean"
		);
	}

	function seedValue(model) {
		return model && model.prefill !== null
			? model.prefill
			: model.default_value;
	}

	function serializeSeed(value) {
		if (value === null || value === undefined) return "";
		if (isScalar(value)) return String(value);
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

	function isNumericPrompt(model) {
		const seed = seedValue(model);
		if (typeof seed !== "number") return false;
		return model.examples.every((example) => typeof example === "number");
	}

	function isDropdownSelect(model) {
		if (!model || model.primitive_id !== "ui.prompt_select") return false;
		if (model.items.length !== 0) return false;
		if (model.examples.length === 0 || model.examples.length > 8) return false;
		return model.examples.every(isScalar);
	}

	function isChecklistSelect(model) {
		return (
			model &&
			model.primitive_id === "ui.prompt_select" &&
			model.items.length > 0
		);
	}

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

	function childNodes(node) {
		if (!node || typeof node !== "object") return [];
		const children =
			node.children && typeof node.children !== "string"
				? node.children
				: node.childNodes && typeof node.childNodes !== "string"
					? node.childNodes
					: [];
		try {
			return Array.from(children);
		} catch {
			return [];
		}
	}

	function tagName(node) {
		if (!node || typeof node !== "object") return "";
		if (typeof node.tagName === "string") return node.tagName.toLowerCase();
		if (typeof node.tag === "string") return node.tag.toLowerCase();
		return "";
	}

	function getAttr(node, name) {
		if (!node || typeof node !== "object") return null;
		if (typeof node.getAttribute === "function") {
			const value = node.getAttribute(name);
			if (value !== null && value !== undefined) return String(value);
		}
		if (node.attrs && Object.prototype.hasOwnProperty.call(node.attrs, name)) {
			return String(node.attrs[name]);
		}
		if (name.startsWith("data-") && node.dataset) {
			const key = name
				.slice(5)
				.replace(/-([a-z])/g, (_, ch) => ch.toUpperCase());
			if (Object.prototype.hasOwnProperty.call(node.dataset, key)) {
				return String(node.dataset[key]);
			}
		}
		return null;
	}

	function setAttr(node, name, value) {
		if (!node || typeof node !== "object") return;
		if (typeof node.setAttribute === "function") {
			node.setAttribute(name, String(value));
		}
		if (!node.attrs || typeof node.attrs !== "object") node.attrs = {};
		node.attrs[name] = String(value);
	}

	function addEvent(node, type, handler) {
		if (!node || typeof node !== "object") return;
		if (typeof node.addEventListener === "function") {
			node.addEventListener(type, handler);
		}
		node[`on${type}`] = handler;
	}

	function clearMount(mount) {
		if (!mount) return;
		if (typeof mount.replaceChildren === "function") {
			mount.replaceChildren();
			return;
		}
		if (Array.isArray(mount.children)) {
			mount.children = [];
			return;
		}
		while (mount.firstChild && typeof mount.removeChild === "function") {
			mount.removeChild(mount.firstChild);
		}
	}

	function walkNodes(node, visit) {
		if (!node || typeof node !== "object") return false;
		if (visit(node)) return true;
		return childNodes(node).some((child) => walkNodes(child, visit));
	}

	function findNode(node, predicate) {
		let found = null;
		walkNodes(node, (entry) => {
			if (predicate(entry)) {
				found = entry;
				return true;
			}
			return false;
		});
		return found;
	}

	function findNodes(node, predicate) {
		const found = [];
		walkNodes(node, (entry) => {
			if (predicate(entry)) found.push(entry);
			return false;
		});
		return found;
	}

	function findBodyMount(mount) {
		return findNode(
			mount,
			(node) => getAttr(node, "data-v3-step-body") === "1",
		);
	}

	function ensureBodyMount(mount, makeEl) {
		const existing = findBodyMount(mount);
		if (existing) return existing;
		const body = makeEl("div", { "data-v3-step-body": "1" });
		mount.appendChild(body);
		return body;
	}

	function markDirty(bodyState) {
		if (bodyState) bodyState.dirty = true;
	}

	function serializeDropdownValue(value) {
		if (value === null || value === undefined) return "";
		return JSON.stringify(value);
	}

	function selectionSetFromExpr(raw, count) {
		const text = typeof raw === "string" ? raw.trim() : "";
		const out = new Set();
		if (text === "") return out;
		if (text === "all") {
			for (let index = 0; index < count; index += 1) out.add(index);
			return out;
		}
		text.split(",").forEach((part) => {
			if (!/^\d+$/.test(part.trim())) return;
			const ordinal = Number(part.trim());
			if (ordinal >= 1 && ordinal <= count) out.add(ordinal - 1);
		});
		return out;
	}

	function selectionExprFromSet(selectionSet, count) {
		const chosen = Array.from(selectionSet || []).filter(
			(index) => Number.isInteger(index) && index >= 0 && index < count,
		);
		chosen.sort((left, right) => left - right);
		if (count > 0 && chosen.length === count) return "all";
		if (!chosen.length) return "";
		return chosen.map((index) => String(index + 1)).join(",");
	}

	function extractLocalDraft(bodyState) {
		if (!bodyState || !bodyState.dirty) return null;
		if (bodyState.mode === "confirm")
			return !!(bodyState.editor && bodyState.editor.checked);
		if (
			bodyState.mode === "checklist" ||
			bodyState.mode === "filterable-checklist"
		) {
			return selectionExprFromSet(
				bodyState.selectionSet,
				bodyState.model ? bodyState.model.items.length : 0,
			);
		}
		if (!bodyState.editor) return null;
		if (bodyState.mode === "dropdown") {
			return parseLooseJson(String(bodyState.editor.value || ""));
		}
		return String(bodyState.editor.value || "");
	}

	function resolveSelectionSeed(model, localDraft) {
		if (typeof localDraft === "string") return localDraft;
		const seed = seedValue(model);
		return typeof seed === "string" ? seed : "";
	}

	function visibleItemIndices(model, filterText) {
		const needle = String(filterText || "")
			.trim()
			.toLowerCase();
		return model.items
			.map((item, index) => ({ item, index }))
			.filter(({ item }) => {
				if (!needle) return true;
				const haystack = `${item.label} ${item.item_id}`.toLowerCase();
				return haystack.includes(needle);
			})
			.map(({ index }) => index);
	}

	function appendHint(body, makeEl, text, className) {
		if (!text) return;
		body.appendChild(makeEl("div", { class: className || "hint", text }));
	}

	function renderExamplesList(body, makeEl, examples) {
		if (!examples.length) return;
		const list = makeEl("ul", { class: "hint" });
		examples.forEach((example) => {
			list.appendChild(makeEl("li", { text: serializeSeed(example) }));
		});
		body.appendChild(list);
	}

	function createInputNode(makeEl, mode, key) {
		if (mode === "textarea") {
			return makeEl("textarea", { rows: "6", "data-v3-payload-key": key });
		}
		const attrs = { "data-v3-payload-key": key };
		if (mode === "number") attrs.type = "number";
		return makeEl("input", attrs);
	}

	function ensureTextEditor(bodyState, makeEl, mode, key) {
		if (bodyState && bodyState.mode === mode && bodyState.editor) {
			return bodyState.editor;
		}
		return createInputNode(makeEl, mode, key);
	}

	function bindTextEditor(editor, bodyState) {
		addEvent(editor, "input", () => markDirty(bodyState));
		addEvent(editor, "change", () => markDirty(bodyState));
	}

	function renderTextLike(args) {
		const { body, bodyState, makeEl, mode, model, localDraft, sameStep } = args;
		const key = PROMPT_PAYLOAD_KEYS[model.primitive_id];
		const next = {
			context: args.context,
			dirty: sameStep ? bodyState && bodyState.dirty : false,
			editor: ensureTextEditor(bodyState, makeEl, mode, key),
			mode,
			model,
			primitive_id: model.primitive_id,
			selectionSet: null,
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

	function ensureDropdownEditor(bodyState, makeEl, key) {
		if (bodyState && bodyState.mode === "dropdown" && bodyState.editor) {
			return bodyState.editor;
		}
		return makeEl("select", { "data-v3-payload-key": key });
	}

	function renderDropdown(args) {
		const { body, bodyState, makeEl, model, localDraft, sameStep } = args;
		const key = PROMPT_PAYLOAD_KEYS[model.primitive_id];
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
			selectionSet: null,
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

	function createChecklistShell(makeEl, filterable) {
		const wrapper = makeEl("div", { "data-v3-payload-key": "selection" });
		const summary = makeEl("div", { class: "hint" });
		const actions = makeEl("div", { class: "hint" });
		const list = makeEl("div", { class: "hint" });
		const filterInput = filterable
			? makeEl("input", { type: "text", placeholder: "Filter" })
			: null;
		return { actions, filterInput, list, summary, wrapper };
	}

	function ensureChecklistState(bodyState, makeEl, filterable) {
		const mode = filterable ? "filterable-checklist" : "checklist";
		if (bodyState && bodyState.mode === mode && bodyState.editor) {
			return {
				actions: bodyState.actions,
				editor: bodyState.editor,
				filterInput: bodyState.filterInput || null,
				list: bodyState.list,
				summary: bodyState.summary,
			};
		}
		return createChecklistShell(makeEl, filterable);
	}

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
		shell.summary.text = shell.summary.textContent;
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
				indices.forEach((index) => {
					if (checked) next.selectionSet.add(index);
					else next.selectionSet.delete(index);
				});
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
		visibleItemIndices(
			model,
			shell.filterInput ? shell.filterInput.value : "",
		).forEach((index) => {
			const item = model.items[index];
			const row = makeEl("label", { class: "choiceItem" });
			const checkbox = makeEl("input", { type: "checkbox" });
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
		});
		(shell.editor || shell.wrapper).appendChild(shell.list);
		body.appendChild(shell.editor || shell.wrapper);
		next.editor = shell.editor || shell.wrapper;
		if (args.mountState) args.mountState.bodyState = next;
		return next;
	}

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
			checkbox = makeEl("input", {
				type: "checkbox",
				"data-v3-payload-key": "confirmed",
			});
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
			selectionSet: null,
		};
		addEvent(checkbox, "change", () => markDirty(next));
		if (!next.dirty) checkbox.checked = seedValue(model) === true;
		const labelNode = childNodes(row).find(
			(entry) => tagName(entry) === "span",
		);
		if (labelNode) {
			labelNode.textContent =
				model.prompt || model.label || model.title || "Confirm";
			labelNode.text = labelNode.textContent;
		}
		body.appendChild(row);
		return next;
	}

	function renderPromptBody(args) {
		const body = ensureBodyMount(args.mount, args.el);
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

	function renderCurrentStep(args) {
		const state = args && args.state ? args.state : null;
		const mount = args && args.mount ? args.mount : null;
		const makeEl = args && typeof args.el === "function" ? args.el : null;
		const getLiveContext =
			args && typeof args.getLiveContext === "function"
				? args.getLiveContext
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

	function fallbackCollectSelect(mount) {
		const payload = findNode(
			mount,
			(node) => getAttr(node, "data-v3-payload-key") === "selection",
		);
		if (!payload) return "";
		if (tagName(payload) === "select") {
			return parseLooseJson(String(payload.value || ""));
		}
		const rows = findNodes(
			payload,
			(node) =>
				tagName(node) === "input" && getAttr(node, "type") === "checkbox",
		);
		const picks = [];
		rows.forEach((checkbox, index) => {
			if (checkbox.checked) picks.push(index);
		});
		return selectionExprFromSet(new Set(picks), rows.length);
	}

	function collectPayload(args) {
		const mount = args && args.mount ? args.mount : null;
		const step = args && args.step ? args.step : null;
		if (!mount || !isPromptStep(step)) return {};
		const primitiveId = String(step.primitive_id || "");
		const key = PROMPT_PAYLOAD_KEYS[primitiveId];
		const mountState = getMountState(mount);
		const bodyState = mountState.bodyState;
		if (
			bodyState &&
			bodyState.context &&
			String(step.step_id || "") === bodyState.context.current_step_id
		) {
			if (primitiveId === "ui.prompt_confirm") {
				return { [key]: !!(bodyState.editor && bodyState.editor.checked) };
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
					String((bodyState.editor && bodyState.editor.value) || ""),
				),
			};
		}
		if (primitiveId === "ui.prompt_select")
			return { [key]: fallbackCollectSelect(mount) };
		const node = findNode(
			mount,
			(entry) => getAttr(entry, "data-v3-payload-key") === key,
		);
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
