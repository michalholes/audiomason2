(function () {
	"use strict";

	/** @typedef {{ skipConfirm?: boolean }} AM2ReloadAllOptions */
	/** @typedef {() => boolean | void | Promise<boolean | void>} AM2AsyncActionHandler */

	const W = window;
	/** @type {AM2EditorHttpApi} */
	const httpApi = W.AM2EditorHTTP;
	/** @type {AM2DSLEditorRegistryApi} */
	const registryApi = window["AM2DSLEditorRegistryAPI"];
	/** @type {AM2DSLEditorGraphOpsApi} */
	const graphOps = window["AM2DSLEditorGraphOps"];
	if (!httpApi || !registryApi || !graphOps) {
		return;
	}

	/**
	 * @type {{
	 * 	registry: AM2PrimitiveRegistryShape | null,
	 * 	history: AM2WizardDefinitionHistoryItem[],
	 * 	searchText: string,
	 * 	rawMode: boolean,
	 * 	status: string,
	 * 	errorPayload: AM2EditorHttpPayload | AM2JsonValue | null,
	 * }}
	 */
	const state = {
		registry: null,
		history: [],
		searchText: "",
		rawMode: false,
		status: "",
		errorPayload: null,
	};

	/** @param {string} id
	 * @returns {HTMLElement | null}
	 */
	function $(id) {
		return document.getElementById(id);
	}

	/** @param {string} id
	 * @returns {HTMLTextAreaElement | null}
	 */
	function textarea(id) {
		const node = $(id);
		return node instanceof HTMLTextAreaElement ? node : null;
	}

	/** @param {Node | null | undefined} node */
	function clear(node) {
		while (node && node.firstChild) {
			node.removeChild(node.firstChild);
		}
	}

	/**
	 * @param {string} nodeId
	 * @param {AM2EditorHttpPayload | AM2JsonValue | undefined | null} payload
	 */
	function renderHTTPError(nodeId, payload) {
		httpApi.renderError($(nodeId), payload);
	}

	/** @param {AM2EditorHttpPayload | AM2JsonValue | undefined | null} payload */
	function setError(payload) {
		state.errorPayload = payload || null;
		renderHTTPError("wdError", state.errorPayload);
		renderHTTPError("flowStepError", state.errorPayload);
	}

	/** @param {string | number | boolean | null | undefined} textValue */
	function setStatus(textValue) {
		state.status = String(textValue || "");
		const node = $("flowStepApply");
		if (node) {
			node.textContent = state.status;
		}
	}

	/** @param {string} actionName
	 * @returns {boolean}
	 */
	function confirmIfDirty(actionName) {
		const flowEditor = W.AM2FlowEditorState;
		const snap =
			flowEditor && flowEditor.getSnapshot ? flowEditor.getSnapshot() : null;
		return (
			!(snap && snap.draftDirty) ||
			window.confirm(actionName + " will discard unsaved edits. Continue?")
		);
	}

	/** @returns {Promise<boolean>} */
	async function loadDefinition() {
		const out = await registryApi.getWizardDefinition();
		if (!out.ok) {
			setError(out.data);
			return false;
		}
		graphOps.loadAll(
			out.data && out.data.definition ? out.data.definition : {},
			{
				preserveValidation: true,
			},
		);
		return true;
	}

	/** @returns {Promise<boolean>} */
	async function loadRegistry() {
		const out = await registryApi.getPrimitiveRegistry();
		if (!out.ok) {
			setError(out.data);
			return false;
		}
		state.registry =
			out.data && out.data.registry
				? /** @type {AM2PrimitiveRegistryShape} */ (out.data.registry)
				: { primitives: [] };
		return true;
	}

	/** @returns {Promise<boolean>} */
	async function loadHistory() {
		const out = await registryApi.listWizardDefinitionHistory();
		if (!out.ok) {
			setError(out.data);
			return false;
		}
		state.history = Array.isArray(out.data && out.data.items)
			? /** @type {AM2WizardDefinitionHistoryItem[]} */ (out.data.items)
			: [];
		renderHistory();
		return true;
	}

	/** @param {AM2ReloadAllOptions | null | undefined} [opts]
	 * @returns {Promise<boolean>}
	 */
	async function reloadAll(opts) {
		if (!(opts && opts.skipConfirm) && !confirmIfDirty("Reload")) {
			return false;
		}
		setError(null);
		if (!(await loadDefinition())) {
			return false;
		}
		if (!graphOps.isV3Draft(graphOps.currentDefinition())) {
			return true;
		}
		if (!(await loadRegistry())) {
			return false;
		}
		await loadHistory();
		renderAll();
		return true;
	}

	/** @returns {Promise<boolean>} */
	async function validateDraft() {
		setError(null);
		const out = await registryApi.validateWizardDefinition(
			graphOps.currentDefinition(),
		);
		if (!out.ok) {
			setError(out.data);
			setStatus("Validate failed.");
			return false;
		}
		graphOps.markValidated(
			out.data && out.data.definition ? out.data.definition : {},
		);
		setStatus("Validate OK.");
		return true;
	}

	/** @returns {Promise<boolean>} */
	async function saveDraft() {
		if (!(await validateDraft())) {
			return false;
		}
		const out = await registryApi.saveWizardDefinition(
			graphOps.currentDefinition(),
		);
		if (!out.ok) {
			setError(out.data);
			setStatus("Save failed.");
			return false;
		}
		graphOps.loadAll(
			out.data && out.data.definition ? out.data.definition : {},
			{
				preserveValidation: true,
			},
		);
		await loadHistory();
		setStatus("Save OK.");
		return true;
	}

	/** @returns {Promise<boolean>} */
	async function activateDefinition() {
		if (!(await saveDraft())) {
			return false;
		}
		const out = await registryApi.activateWizardDefinition();
		if (!out.ok) {
			setError(out.data);
			setStatus("Activate failed.");
			return false;
		}
		await reloadAll({ skipConfirm: true });
		setStatus("Activate OK.");
		return true;
	}

	/** @returns {Promise<boolean>} */
	async function resetDefinition() {
		if (!confirmIfDirty("Reset")) {
			return false;
		}
		const out = await registryApi.resetWizardDefinition();
		if (!out.ok) {
			setError(out.data);
			return false;
		}
		graphOps.loadAll(
			out.data && out.data.definition ? out.data.definition : {},
			{
				preserveValidation: true,
			},
		);
		await loadHistory();
		setStatus("Reset OK.");
		return true;
	}

	/** @param {string} id
	 * @returns {Promise<boolean>}
	 */
	async function rollback(id) {
		if (!confirmIfDirty("Rollback")) {
			return false;
		}
		const out = await registryApi.rollbackWizardDefinition(id);
		if (!out.ok) {
			setError(out.data);
			return false;
		}
		graphOps.loadAll(
			out.data && out.data.definition ? out.data.definition : {},
			{
				preserveValidation: true,
			},
		);
		await loadHistory();
		setStatus("Rollback OK.");
		return true;
	}

	/** @returns {void} */
	function renderHistory() {
		["wdHistory", "flowStepHistory"].forEach(function (id) {
			const mount = $(id);
			if (!mount) {
				return;
			}
			clear(mount);
			state.history.forEach(function (item) {
				const row = document.createElement("div");
				row.className = "historyItem";
				const meta = document.createElement("div");
				meta.className = "historyMeta";
				meta.appendChild(document.createTextNode(String(item.id || "")));
				meta.appendChild(document.createElement("br"));
				meta.appendChild(document.createTextNode(String(item.timestamp || "")));
				const button = document.createElement("button");
				button.className = "btn";
				button.type = "button";
				button.textContent = "Rollback";
				button.addEventListener("click", function () {
					void rollback(String(item.id || ""));
				});
				row.appendChild(meta);
				row.appendChild(button);
				mount.appendChild(row);
			});
		});
	}

	/** @param {string} textValue */
	function applyRawJSON(textValue) {
		try {
			graphOps.loadAll(
				/** @type {AM2DSLGraphDefinition} */ (JSON.parse(textValue || "{}")),
				{
					preserveValidation: false,
				},
			);
			setError(null);
			setStatus("Raw JSON applied to draft.");
		} catch (err) {
			setError({
				error: {
					code: "PARSE_ERROR",
					message: String(err || "parse error"),
				},
			});
		}
	}

	/** @param {AM2DSLGraphDefinition} definition */
	function renderCanvasPanel(definition) {
		const renderer = W.AM2FlowCanvasPanel;
		if (!renderer || !renderer.renderCanvas) return;
		const stepModal = W.AM2FlowStepModalState;
		renderer.renderCanvas({
			mount: $("flowCanvasPanel"),
			metaMount: $("flowCanvasMeta"),
			nodes: Array.isArray(definition.nodes) ? definition.nodes : [],
			edges: Array.isArray(definition.edges) ? definition.edges : [],
			selectedStepId: graphOps.selectedStepId(),
			onSelectStep: function (stepId) {
				graphOps.setSelectedStep(stepId);
				if (stepModal && stepModal.openStep) {
					void stepModal.openStep(stepId);
				}
			},
		});
	}

	/**
	 * @param {AM2DSLGraphDefinition} definition
	 * @param {AM2PrimitiveRegistryItem | null | undefined} meta
	 */
	function renderSummary(definition, meta) {
		const header = $("flowStepHeader");
		if (header) {
			header.textContent = "Flow editor - step modal";
		}
		const behavior = $("flowStepBehavior");
		if (behavior) {
			behavior.textContent =
				"Registry-backed v3 graph editor. Visual edits stay in the draft " +
				"until backend validate/save/activate.";
		}
		const input = $("flowStepInput");
		if (input) {
			input.textContent = httpApi.pretty((meta && meta.inputs_schema) || {});
		}
		const output = $("flowStepOutput");
		if (output) {
			output.textContent = httpApi.pretty((meta && meta.outputs_schema) || {});
		}
		const sideEffects = $("flowStepSideEffects");
		if (sideEffects) {
			sideEffects.textContent = String((meta && meta.determinism_notes) || "");
		}
		const diff = $("flowStepDiff");
		if (diff) {
			const graph = graphOps.currentGraphDefinition();
			diff.textContent =
				"graph=" +
				String(graphOps.currentGraphLabel()) +
				" entry_step_id=" +
				String((graph && graph.entry_step_id) || "") +
				" nodes=" +
				String(((graph && graph.nodes) || []).length) +
				" edges=" +
				String(((graph && graph.edges) || []).length) +
				" selected=" +
				String(graphOps.selectedStepId() || "");
		}
	}

	/** @param {AM2DSLGraphDefinition} definition */
	function renderForms(definition) {
		const textArea = textarea("wdJson");
		const graphDefinition = graphOps.currentGraphDefinition();
		if (window["AM2DSLEditorRawJSON"]) {
			window["AM2DSLEditorRawJSON"].renderRawJSON({
				mount: $("flowStepForm"),
				textarea: textArea,
				state: { rawMode: state.rawMode },
				actions: {
					onSetMode: function (value) {
						state.rawMode = value === true;
						renderAll();
					},
					onApply: applyRawJSON,
				},
			});
		}
		if (!state.rawMode && window["AM2DSLEditorNodeForm"]) {
			window["AM2DSLEditorNodeForm"].renderNodeForm({
				mount: $("flowStepForm"),
				definition: definition,
				graphDefinition: graphDefinition,
				selectedStepId: graphOps.selectedStepId(),
				actions: {
					onAddWrite: graphOps.addWrite,
					onPatchNode: graphOps.patchNode,
					onPatchWrite: graphOps.patchWrite,
					onRemoveNode: graphOps.removeNode,
					onRemoveWrite: graphOps.removeWrite,
					onSelect: graphOps.setSelectedStep,
				},
			});
		}
		if (window["AM2DSLEditorEdgeForm"]) {
			window["AM2DSLEditorEdgeForm"].renderEdgeForm({
				mount: $("flowTransitionsPanel"),
				definition: graphDefinition,
				actions: {
					onAddEdge: graphOps.addEdge,
					onPatchEdge: graphOps.patchEdge,
					onRemoveEdge: graphOps.removeEdge,
				},
			});
		}
		const palettePanel = $("flowPalettePanel");
		clear(palettePanel);
		const libraryMount = document.createElement("div");
		const paletteMount = document.createElement("div");
		if (palettePanel) {
			palettePanel.appendChild(libraryMount);
			palettePanel.appendChild(paletteMount);
		}
		if (window["AM2DSLEditorLibraryPanel"]) {
			window["AM2DSLEditorLibraryPanel"].renderLibraryPanel({
				mount: libraryMount,
				definition: definition,
				state: {
					selectedLibraryId: graphOps.selectedLibraryId(),
				},
				actions: {
					onAddLibrary: graphOps.addLibrary,
					onPatchLibrary: graphOps.patchLibrary,
					onRemoveLibrary: graphOps.removeLibrary,
					onSelectLibrary: graphOps.setSelectedLibrary,
					onSelectRoot: function () {
						graphOps.setSelectedLibrary("");
						renderAll();
					},
				},
			});
		}
		if (window["AM2DSLEditorPalette"]) {
			window["AM2DSLEditorPalette"].renderPalette({
				mount: paletteMount,
				registry: graphOps.primitiveItems(state.registry),
				state: {
					onAddPrimitive: graphOps.addPrimitiveNode,
					onSearch: function (value) {
						state.searchText = String(value || "");
						renderAll();
					},
					searchText: state.searchText,
				},
			});
		}
	}

	/** @returns {boolean} */
	function renderAll() {
		const definition = graphOps.currentDefinition();
		if (!graphOps.isV3Draft(definition)) {
			return false;
		}
		if (
			!graphOps.selectedStepId() &&
			Array.isArray(definition.nodes) &&
			definition.nodes[0]
		) {
			graphOps.setSelectedStep(String(definition.nodes[0].step_id || ""));
			return true;
		}
		const textArea = $("wdJson");
		if (textArea instanceof HTMLTextAreaElement) {
			textArea.value = httpApi.pretty(definition);
			textArea.classList.remove("is-hidden");
			textArea.classList.remove("wdHidden");
		}
		const root = /** @type {HTMLElement | null} */ (
			document.querySelector(".wdLayoutRoot")
		);
		if (root) root.classList.add("is-hidden");
		renderSummary(
			definition,
			graphOps.primitiveMeta(graphOps.currentNode(), state.registry),
		);
		renderCanvasPanel(graphOps.currentGraphDefinition());
		renderForms(definition);
		renderHistory();
		setError(state.errorPayload);
		setStatus(state.status);
		return true;
	}

	/**
	 * @param {string} buttonId
	 * @param {AM2AsyncActionHandler} handler
	 */
	function intercept(buttonId, handler) {
		const node = $(buttonId);
		if (!node) {
			return;
		}
		node.addEventListener(
			"click",
			function (event) {
				if (!graphOps.isV3Draft(graphOps.currentDefinition())) {
					return;
				}
				event.preventDefault();
				event.stopImmediatePropagation();
				void handler();
			},
			true,
		);
	}

	intercept("flowStepValidate", validateDraft);
	intercept("flowStepSave", saveDraft);
	intercept("flowStepActivate", activateDefinition);
	intercept("flowStepApplyNow", activateDefinition);
	intercept("flowClearStep", function () {
		graphOps.clearSelectedNode();
		setStatus("Selected node inputs and writes cleared.");
		return true;
	});
	intercept("flowStepShowHistory", loadHistory);

	/** @type {AM2DSLEditorV3Api} */
	window["AM2DSLEditorV3"] = {
		activateDefinition: activateDefinition,
		isV3Draft: graphOps.isV3Draft,
		reloadAll: reloadAll,
		renderAll: renderAll,
		resetDefinition: resetDefinition,
		rollback: rollback,
		saveDraft: saveDraft,
		validateDraft: validateDraft,
	};
})();
