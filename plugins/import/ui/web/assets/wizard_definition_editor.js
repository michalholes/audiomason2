(() => {
	const W = /** @type {(Window & typeof globalThis) & {
	 *   AM2WizardDefinitionEditorHelpers?: AM2WizardDefinitionEditorHelpersApi,
	 * }} */ (window);
	const H = W.AM2EditorHTTP;
	if (!H) return;

	/** @param {string} id */
	function $(id) {
		return document.getElementById(id);
	}

	const ui = {
		ta: $("wdJson"),
		err: $("wdError"),
		history: $("wdHistory"),
		reload: $("wdReload"),
		validate: $("wdValidate"),
		save: $("wdSave"),
		reset: $("wdReset"),
	};

	if (!ui.ta) return;

	/** @param {Node | null | undefined} node */
	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	/** @type {AM2DomFactoryApi} */
	function el(tag, cls) {
		const n = document.createElement(tag);
		if (cls) n.className = cls;
		return n;
	}

	/** @type {AM2TextFactoryApi} */
	function text(tag, cls, s) {
		const n = el(tag, cls);
		n.textContent = String(s || "");
		return n;
	}

	/** @type {(definition: AM2JsonObject) => AM2WDStableGraphResult} */
	const stableGraph =
		W.AM2WDGraphStable && W.AM2WDGraphStable.stableGraph
			? W.AM2WDGraphStable.stableGraph
			: () => ({ version: 1, nodes: [], edges: [], entry: null });

	/** @template T @param {T} x @returns {T} */
	function deepClone(x) {
		return x === undefined ? undefined : JSON.parse(JSON.stringify(x));
	}

	/** @param {AM2JsonObject | null | undefined} defn @returns {AM2JsonObject} */
	function stripUi(defn) {
		const x = deepClone(defn || {});
		if (x && x._am2_ui) delete x._am2_ui;
		return x;
	}

	/** @returns {AM2WizardUiState} */
	function makeWizardUiState() {
		return {
			dragId: null,
			dropBeforeId: null,
			showOptional: true,
			validation: { ok: null, local: [], server: [] },
			showRawError: false,
			hasErrorDetails: false,
		};
	}

	/** @param {AM2JsonObject | null | undefined} wd @returns {AM2WizardUiState} */
	function ensureWizardUi(wd) {
		if (!wd || typeof wd !== "object") return makeWizardUiState();
		if (!wd._am2_ui || typeof wd._am2_ui !== "object") {
			wd._am2_ui = makeWizardUiState();
		}
		return /** @type {AM2WizardUiState} */ (wd._am2_ui);
	}

	function snapshot() {
		const FE = W.AM2FlowEditorState;
		return FE && FE.getSnapshot ? FE.getSnapshot() : null;
	}

	function wizardDraft() {
		const s = snapshot();
		return (s && s.wizardDraft) || {};
	}

	function selectedStepId() {
		const s = snapshot();
		return (s && s.selectedStepId) || null;
	}

	/**
	 * @param {(uiState: AM2WizardUiState, wd: AM2JsonObject) => void} fn
	 * @param {AM2FlowMutationOptions | null | undefined} [opts]
	 */
	function mutateWizard(fn, opts) {
		const FE = W.AM2FlowEditorState;
		if (!FE || !FE.mutateWizard) return;
		FE.mutateWizard((wd) => {
			fn && fn(ensureWizardUi(wd), wd);
		}, opts || null);
	}

	/** @param {string | null | undefined} stepIdOrNull */
	function setSelectedStep(stepIdOrNull) {
		const FE = W.AM2FlowEditorState;
		if (FE && FE.setSelectedStep) FE.setSelectedStep(stepIdOrNull || null);
	}

	/**
	 * @param {string[]} nodes
	 * @param {string | null | undefined} entryStepId
	 * @param {AM2WizardDefinitionGraphEdge[]} edges
	 * @returns {AM2WizardDefinitionV2}
	 */
	function defFromGraph(nodes, entryStepId, edges) {
		const entry = entryStepId || (nodes && nodes[0]) || "";
		return {
			version: 2,
			graph: {
				entry_step_id: String(entry || ""),
				nodes: (nodes || []).map((sid) => ({ step_id: sid })),
				edges: (edges || []).map((e) => ({
					from_step_id: e.from_step_id,
					to_step_id: e.to_step_id,
					priority: typeof e.priority === "number" ? e.priority : 0,
					when: e.when === undefined ? null : e.when,
				})),
			},
		};
	}

	/**
	 * @param {AM2JsonObject} wd
	 * @param {AM2WizardDefinitionV2} next
	 */
	function replaceWizardDraft(wd, next) {
		Object.keys(wd).forEach((key) => {
			delete wd[key];
		});
		Object.assign(wd, next);
	}

	function ensureV2() {
		mutateWizard(
			/** @param {AM2WizardUiState} uiState @param {AM2JsonObject} wd */
			(uiState, wd) => {
				// Only normalize when required; avoid marking the draft dirty for
				// internal idempotent migrations.
				if (wd && typeof wd === "object") {
					const v2 = wd.version === 2;
					const hasWizardId = Object.hasOwn(wd, "wizard_id");
					const g =
						wd.graph && typeof wd.graph === "object" && !Array.isArray(wd.graph)
							? /** @type {AM2WizardDefinitionV2Graph} */ (wd.graph)
							: null;
					const graphOk =
						g &&
						Array.isArray(g.nodes) &&
						Array.isArray(g.edges) &&
						typeof g.entry_step_id === "string";
					const keys = Object.keys(wd);
					const onlyKnownKeys = keys.every(
						(k) => k === "version" || k === "graph" || k === "_am2_ui",
					);
					if (v2 && !hasWizardId && graphOk && onlyKnownKeys) return;
				}

				const g = stableGraph(wd);
				const nodes = Array.isArray(g.nodes) ? g.nodes.slice(0) : [];
				const edges = Array.isArray(g.edges) ? g.edges.slice(0) : [];
				const next = defFromGraph(nodes, g.entry, edges);
				next._am2_ui = uiState;
				replaceWizardDraft(wd, next);
			},
			{ markDirty: false, resetValidation: false, reason: "normalize_v2" },
		);
	}

	/** @type {AM2JsonObject[]} */
	/** @type {AM2JsonObject[]} */
	const paletteItems = [];

	function renderCanvasPanel() {
		const renderer = W.AM2FlowCanvasPanel;
		if (!renderer || !renderer.renderCanvas) return;
		const graph = stableGraph(wizardDraft());
		/** @type {Record<string, AM2JsonObject>} */
		const catalog = {};
		paletteItems.forEach((item) => {
			const sid = String(item && item.step_id ? item.step_id : "");
			if (sid) catalog[sid] = item;
		});
		renderer.renderCanvas({
			mount: $("flowCanvasPanel"),
			metaMount: $("flowCanvasMeta"),
			nodes: Array.isArray(graph.nodes) ? graph.nodes : [],
			edges: Array.isArray(graph.edges) ? graph.edges : [],
			selectedStepId: selectedStepId(),
			onSelectStep: setSelectedStep,
			catalog: catalog,
		});
	}

	function v3() {
		const editor = W.AM2DSLEditorV3;
		return editor && editor.isV3Draft && editor.isV3Draft(wizardDraft())
			? editor
			: null;
	}

	const root =
		W.AM2WDLayoutRoot && W.AM2WDLayoutRoot.createRoot
			? W.AM2WDLayoutRoot.createRoot({ ui: ui, el: el, text: text })
			: null;

	const flowSidebar = $("flowEditorSidebar");
	const stepPanel = $("flowStepPanel");
	const transitionsPanel = $("flowTransitionsPanel");
	const palettePanel = $("flowPalettePanel");

	if (
		W.AM2WDSidebar &&
		W.AM2WDSidebar.buildSidebarSections &&
		flowSidebar &&
		stepPanel &&
		transitionsPanel &&
		palettePanel
	) {
		W.AM2WDSidebar.buildSidebarSections({
			flowSidebar: flowSidebar,
			stepPanel: stepPanel,
			transitionsPanel: transitionsPanel,
			rightCol: palettePanel,
			clear: clear,
			el: el,
			text: text,
		});
		const C = W.AM2FlowConfigEditor;
		if (C && C.renderNow) void C.renderNow();
	}

	const wizardEditorHelperApi =
		/** @type {AM2WizardDefinitionEditorHelpersApi | undefined} */ (
			Reflect.get(W, "AM2WizardDefinitionEditorHelpers")
		);
	const wizardEditorHelpers =
		wizardEditorHelperApi && wizardEditorHelperApi.createGraphOps
			? wizardEditorHelperApi.createGraphOps({
					stableGraph: stableGraph,
					wizardDraft: wizardDraft,
					ensureV2: ensureV2,
					mutateWizard: mutateWizard,
					defFromGraph: defFromGraph,
					replaceWizardDraft: replaceWizardDraft,
					selectedStepId: selectedStepId,
					setSelectedStep: setSelectedStep,
				})
			: null;
	if (!wizardEditorHelpers) return;
	const {
		isOptionalStep,
		canRemove,
		hasStep,
		addStep,
		removeStep,
		reorderStep,
		moveStepUp,
		moveStepDown,
		addEdge,
		removeEdge,
		updateEdge,
		moveEdge,
	} = wizardEditorHelpers;

	/** @param {boolean | null} ok @param {string[]} localMsgs @param {string[]} serverMsgs */
	function setValidation(ok, localMsgs, serverMsgs) {
		mutateWizard(
			/** @param {AM2WizardUiState} uiState */ (uiState) => {
				uiState.validation = {
					ok: ok,
					local: Array.isArray(localMsgs) ? localMsgs : [],
					server: Array.isArray(serverMsgs) ? serverMsgs : [],
				};
			},
		);
	}

	function validationMessages() {
		const u = ensureWizardUi(wizardDraft());
		const v = u.validation;
		/** @type {string[]} */
		const msgs = [];
		(Array.isArray(v.local) ? v.local : []).forEach((m) => {
			msgs.push(m);
		});
		(Array.isArray(v.server) ? v.server : []).forEach((m) => {
			msgs.push(m);
		});
		return msgs;
	}

	/** @param {AM2JsonValue} errEnvelope @returns {string[]} */
	function extractServerMessages(errEnvelope) {
		const outer =
			errEnvelope &&
			typeof errEnvelope === "object" &&
			!Array.isArray(errEnvelope)
				? /** @type {AM2JsonObject} */ (errEnvelope)
				: null;
		const maybeError =
			outer &&
			outer.error &&
			typeof outer.error === "object" &&
			!Array.isArray(outer.error)
				? /** @type {AM2JsonObject} */ (outer.error)
				: null;
		const inner = maybeError || outer;
		const details = inner && "details" in inner ? inner.details : null;
		const out = [];
		const msg = inner && "message" in inner ? inner.message : null;
		if (msg) out.push(String(msg));
		(Array.isArray(details) ? details : []).forEach((d) => {
			if (!d || typeof d !== "object" || Array.isArray(d)) return;
			const detail = /** @type {AM2JsonObject} */ (d);
			const path = detail.path ? String(detail.path) : "";
			const reason = detail.reason ? String(detail.reason) : "";
			if (path || reason) out.push(path + " " + reason);
		});
		return out;
	}

	/** @param {AM2JsonValue} data @param {boolean} collapseByDefault */
	function renderError(data, collapseByDefault) {
		H.renderError(ui.err, data);
		mutateWizard(
			/** @param {AM2WizardUiState} uiState */ (uiState) => {
				uiState.hasErrorDetails = !!data;
				uiState.showRawError = data ? !collapseByDefault : false;
			},
		);
	}

	function setupRawErrorPanel() {
		/** @type {AM2WDRawErrorPanelState} */
		const rawErrorState = {
			showRawError: false,
			hasErrorDetails: false,
		};
		Object.defineProperty(rawErrorState, "showRawError", {
			get: () => !!ensureWizardUi(wizardDraft()).showRawError,
			set: (on) => {
				mutateWizard(
					/** @param {AM2WizardUiState} uiState */ (uiState) => {
						uiState.showRawError = !!on;
					},
				);
			},
		});
		Object.defineProperty(rawErrorState, "hasErrorDetails", {
			get: () => !!ensureWizardUi(wizardDraft()).hasErrorDetails,
			set: (on) => {
				mutateWizard(
					/** @param {AM2WizardUiState} uiState */ (uiState) => {
						uiState.hasErrorDetails = !!on;
					},
				);
			},
		});
		if (W.AM2WDRawError && W.AM2WDRawError.setupRawErrorPanel) {
			W.AM2WDRawError.setupRawErrorPanel({
				ui: ui,
				state: rawErrorState,
				el: el,
				text: text,
			});
		}
		rawErrorState.showRawError = false;
		if (!ui.err) return;
		ui.err.classList.toggle("is-collapsed", !rawErrorState.showRawError);

		const btn = document.querySelector(".wdErrToggle");
		if (btn)
			btn.textContent = rawErrorState.showRawError ? "Hide Details" : "Details";
	}

	setupRawErrorPanel();

	function isDirty() {
		const s = snapshot();
		return !!(s && s.draftDirty);
	}

	/** @param {string} actionName */
	function confirmIfDirty(actionName) {
		if (!isDirty()) return true;
		return window.confirm(
			actionName +
				" will discard unsaved edits. Run Validate All first, or reload after saving. Continue?",
		);
	}

	/** @param {AM2WizardDefinitionHistoryItem} item */
	function historyRow(item) {
		const row = el("div", "historyItem");
		const meta = el("div", "historyMeta");
		meta.appendChild(text("div", null, item.id || ""));
		meta.appendChild(text("div", null, item.timestamp || ""));
		const btn = text("button", "btn", "Rollback");
		btn.addEventListener("click", () => {
			rollback(String(item.id || ""));
		});
		row.appendChild(meta);
		row.appendChild(btn);
		return row;
	}

	function loadHistory() {
		return H.requestJSON("/import/ui/wizard-definition/history").then((out) => {
			if (!out.ok) {
				renderError(out.data, false);
				return false;
			}
			clear(ui.history);
			const items = out.data && out.data.items ? out.data.items : [];
			(Array.isArray(items) ? items : []).forEach((it) => {
				ui.history.appendChild(historyRow(it || {}));
			});
			return true;
		});
	}

	function loadPalette() {
		return H.requestJSON("/import/ui/steps-index").then((out) => {
			if (!out.ok) {
				renderError(out.data, false);
				return false;
			}
			const items = out.data && out.data.items ? out.data.items : [];
			paletteItems.length = 0;
			(Array.isArray(items) ? items : []).forEach((it) => {
				paletteItems.push(it);
			});
			return true;
		});
	}

	function loadDefinition() {
		return H.requestJSON("/import/ui/wizard-definition").then((out) => {
			if (!out.ok) {
				renderError(out.data, false);
				return false;
			}
			const defn = /** @type {AM2JsonObject} */ (
				out.data && out.data.definition ? out.data.definition : {}
			);
			const FE = W.AM2FlowEditorState;
			if (FE && FE.loadAll && FE.getSnapshot) {
				const snap = FE.getSnapshot();
				FE.loadAll(
					{ wizardDefinition: defn, flowConfig: snap.configDraft },
					{ preserveValidation: true },
				);
			}
			return true;
		});
	}

	/** @param {{ skipConfirm?: boolean } | null | undefined} opts */
	function reloadAll(opts) {
		const skipConfirm = !!(opts && opts.skipConfirm);
		if (!skipConfirm && !confirmIfDirty("Reload")) return false;
		renderError(null, false);
		setValidation(null, [], []);
		return loadDefinition().then((ok2) => {
			const editor = v3();
			if (ok2 && editor && editor.reloadAll)
				return editor.reloadAll({ skipConfirm: true });
			return loadPalette().then((ok1) => {
				if (ok1 && ok2) {
					return loadHistory().then(() => {
						ensureV2();
						renderAll();
						return true;
					});
				}
				return false;
			});
		});
	}

	function validateDraft() {
		renderError(null, false);
		setValidation(null, [], []);
		const s = snapshot();
		const payload = { definition: stripUi((s && s.wizardDraft) || {}) };
		return H.requestJSON("/import/ui/wizard-definition/validate", {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: JSON.stringify(payload),
		}).then((out) => {
			if (!out.ok) {
				renderError(out.data, true);
				setValidation(
					false,
					["Validation failed. See error details above."],
					extractServerMessages(out.data),
				);
				renderAll();
				return false;
			}
			const defn = /** @type {AM2JsonObject} */ (
				out.data && out.data.definition ? out.data.definition : {}
			);
			const FE = W.AM2FlowEditorState;
			if (FE && FE.markValidated && FE.getSnapshot) {
				const snap = FE.getSnapshot();
				FE.markValidated({
					canonicalWizardDefinition: defn,
					canonicalFlowConfig: snap.configDraft,
					validationEnvelope: { ok: true },
				});
			}
			setValidation(true, [], []);
			renderAll();
			return true;
		});
	}

	function saveDraft() {
		return validateDraft().then((ok) => {
			if (!ok) return false;
			const s = snapshot();
			const payload = { definition: stripUi((s && s.wizardDraft) || {}) };
			return H.requestJSON("/import/ui/wizard-definition", {
				method: "POST",
				headers: { "content-type": "application/json" },
				body: JSON.stringify(payload),
			}).then((out) => {
				if (!out.ok) {
					renderError(out.data, false);
					return false;
				}
				const defn = /** @type {AM2JsonObject} */ (
					out.data && out.data.definition ? out.data.definition : {}
				);
				const FE = W.AM2FlowEditorState;
				if (FE && FE.loadAll && FE.getSnapshot) {
					const snap = FE.getSnapshot();
					FE.loadAll(
						{ wizardDefinition: defn, flowConfig: snap.configDraft },
						{ preserveValidation: true },
					);
				}
				return loadHistory().then(() => {
					renderAll();
					return true;
				});
			});
		});
	}

	function resetDefinition() {
		if (!confirmIfDirty("Reset")) return false;

		renderError(null, false);
		setValidation(null, [], []);
		return H.requestJSON("/import/ui/wizard-definition/reset", {
			method: "POST",
		}).then((out) => {
			if (!out.ok) {
				renderError(out.data, false);
				return false;
			}
			const defn = /** @type {AM2JsonObject} */ (
				out.data && out.data.definition ? out.data.definition : {}
			);
			const FE = W.AM2FlowEditorState;
			if (FE && FE.loadAll && FE.getSnapshot) {
				const snap = FE.getSnapshot();
				FE.loadAll(
					{ wizardDefinition: defn, flowConfig: snap.configDraft },
					{ preserveValidation: true },
				);
			}
			return loadHistory().then(() => {
				renderAll();
				return true;
			});
		});
	}

	/** @param {string} id */
	function rollback(id) {
		if (!confirmIfDirty("Rollback")) return;

		renderError(null, false);
		setValidation(null, [], []);
		return H.requestJSON("/import/ui/wizard-definition/rollback", {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: JSON.stringify({ id: id }),
		}).then((out) => {
			if (!out.ok) {
				renderError(out.data, false);
				return;
			}
			const defn = /** @type {AM2JsonObject} */ (
				out.data && out.data.definition ? out.data.definition : {}
			);
			const FE = W.AM2FlowEditorState;
			if (FE && FE.loadAll && FE.getSnapshot) {
				const snap = FE.getSnapshot();
				FE.loadAll(
					{ wizardDefinition: defn, flowConfig: snap.configDraft },
					{ preserveValidation: true },
				);
			}
			return loadHistory().then(() => {
				renderAll();
			});
		});
	}

	function buildToolbar() {
		if (!root) return;
		clear(root.toolbar);

		const btnAdd = /** @type {HTMLButtonElement} */ (
			text("button", "btn", "Add Step")
		);
		const optLabel = el("label", "wdToggle");
		const optToggle = /** @type {HTMLInputElement} */ (
			el("input", "wdToggleInput")
		);
		optToggle.type = "checkbox";
		optToggle.checked = true;
		optLabel.appendChild(optToggle);
		optLabel.appendChild(text("span", "wdToggleText", "Show Optional"));

		btnAdd.type = "button";
		btnAdd.addEventListener("click", () => {
			try {
				window.dispatchEvent(
					new CustomEvent("am2:palette:focus", { detail: {} }),
				);
			} catch (e) {
				// ignore
			}
		});

		optToggle.addEventListener("change", () => {
			mutateWizard(
				/** @param {AM2WizardUiState} uiState */ (uiState) => {
					uiState.showOptional = !!optToggle.checked;
				},
			);
			renderAll();
		});

		root.toolbar.appendChild(btnAdd);
		root.toolbar.appendChild(optLabel);
	}

	const table =
		W.AM2WDTableRender && W.AM2WDTableRender.initTable && root
			? W.AM2WDTableRender.initTable({
					body: root.tableBody,
					el: el,
					text: text,
					state: {
						getWizardDraft: wizardDraft,
						getSelectedStepId: selectedStepId,
						isOptional: isOptionalStep,
						canRemove: canRemove,
						setSelectedStep: setSelectedStep,
						removeStep: (sid) => {
							removeStep(sid);
							renderAll();
						},
						moveStepUp: (sid) => {
							moveStepUp(sid);
							renderAll();
						},
						moveStepDown: (sid) => {
							moveStepDown(sid);
							renderAll();
						},
						reorderStep: (dragSid, dropBeforeSidOrNull) => {
							reorderStep(dragSid, dropBeforeSidOrNull);
							renderAll();
						},
					},
				})
			: null;

	function renderAll() {
		const editor = v3();
		if (editor && editor.renderAll) return editor.renderAll();
		if (ui.ta) ui.ta.classList.add("is-hidden");
		if (root && root.layout) root.layout.classList.remove("is-hidden");
		buildToolbar();

		if (table && table.renderAll) table.renderAll();

		if (W.AM2WDDetailsRender && W.AM2WDDetailsRender.renderValidation && root) {
			W.AM2WDDetailsRender.renderValidation({
				mount: root.validationList,
				countEl: root.validationCount,
				el: el,
				text: text,
				messages: validationMessages(),
			});

			// Step Details rendering is owned by config_editor.js (FlowConfig draft editor).
		}

		if (
			W.AM2WDPaletteRender &&
			W.AM2WDPaletteRender.renderPalette &&
			palettePanel
		) {
			W.AM2WDPaletteRender.renderPalette({
				mount: palettePanel,
				el: el,
				text: text,
				items: paletteItems,
				state: {
					canAdd: (sid) => !hasStep(sid),
					addStep: (sid) => {
						addStep(sid);
						renderAll();
					},
				},
			});
		}

		if (
			W.AM2WDTransitionsRender &&
			W.AM2WDTransitionsRender.renderTransitions &&
			transitionsPanel
		) {
			W.AM2WDTransitionsRender.renderTransitions({
				mount: transitionsPanel,
				el: el,
				text: text,
				state: {
					getWizardDraft: wizardDraft,
					getSelectedStepId: selectedStepId,
					addEdge: (fromId, toId, prio, whenVal) => {
						addEdge(fromId, toId, prio, whenVal);
						renderAll();
					},
					removeEdge: (fromId, outgoingIndex) => {
						removeEdge(fromId, outgoingIndex);
						renderAll();
					},
				},
			});
		}

		renderCanvasPanel();

		if (root && root.validationClear) {
			root.validationClear.onclick = () => {
				setValidation(null, [], []);
				renderAll();
			};
		}
	}

	const FE = W.AM2FlowEditorState;
	if (FE && FE.on) {
		FE.on("wizard_changed", () => {
			renderAll();
		});
		FE.on("selection_changed", () => {
			if (table && table.updateSelection) table.updateSelection();
			renderAll();
			if (!v3() && W.AM2FlowConfigEditor && W.AM2FlowConfigEditor.renderNow) {
				void W.AM2FlowConfigEditor.renderNow();
			}
		});
	} else if (FE && FE.registerWizardRender) {
		FE.registerWizardRender(renderAll);
	}

	if (ui.reload)
		ui.reload.addEventListener("click", () => {
			const editor = v3();
			return editor && editor.reloadAll ? editor.reloadAll({}) : reloadAll({});
		});
	if (ui.validate)
		ui.validate.addEventListener("click", () => {
			const editor = v3();
			return editor && editor.validateDraft
				? editor.validateDraft()
				: validateDraft();
		});
	if (ui.save)
		ui.save.addEventListener("click", () => {
			const editor = v3();
			return editor && editor.saveDraft ? editor.saveDraft() : saveDraft();
		});
	if (ui.reset)
		ui.reset.addEventListener("click", () => {
			const editor = v3();
			return editor && editor.resetDefinition
				? editor.resetDefinition()
				: resetDefinition();
		});

	W.AM2WizardDefinitionEditor = {
		reloadAll: () => {
			const editor = v3();
			return editor && editor.reloadAll ? editor.reloadAll({}) : reloadAll({});
		},
		validateDraft: () => {
			const editor = v3();
			return editor && editor.validateDraft
				? editor.validateDraft()
				: validateDraft();
		},
		saveDraft: () => {
			const editor = v3();
			return editor && editor.saveDraft ? editor.saveDraft() : saveDraft();
		},
		resetDefinition: () => {
			const editor = v3();
			return editor && editor.resetDefinition
				? editor.resetDefinition()
				: resetDefinition();
		},
	};

	W.AM2FlowEditor = W.AM2FlowEditor || {};
	W.AM2FlowEditor.wizard = {
		reload: () => {
			const editor = v3();
			return editor && editor.reloadAll ? editor.reloadAll({}) : reloadAll({});
		},
		validate: () => {
			const editor = v3();
			return editor && editor.validateDraft
				? editor.validateDraft()
				: validateDraft();
		},
		save: () => {
			const editor = v3();
			return editor && editor.saveDraft ? editor.saveDraft() : saveDraft();
		},
		reset: () => {
			const editor = v3();
			return editor && editor.resetDefinition
				? editor.resetDefinition()
				: resetDefinition();
		},
	};

	reloadAll({ skipConfirm: true });
})();
