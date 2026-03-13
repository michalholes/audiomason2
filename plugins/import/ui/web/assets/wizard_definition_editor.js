(() => {
	const W = /** @type {any} */ (window);
	const H = W.AM2EditorHTTP;
	if (!H) return;

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

	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	function el(tag, cls) {
		const n = document.createElement(tag);
		if (cls) n.className = cls;
		return n;
	}

	function text(tag, cls, s) {
		const n = el(tag, cls);
		n.textContent = String(s || "");
		return n;
	}

	const stableGraph =
		W.AM2WDGraphStable && W.AM2WDGraphStable.stableGraph
			? W.AM2WDGraphStable.stableGraph
			: () => ({ version: 1, nodes: [], edges: [], entry: null });

	function deepClone(x) {
		return x === undefined ? undefined : JSON.parse(JSON.stringify(x));
	}

	function stripUi(defn) {
		const x = deepClone(defn || {});
		if (x && x._am2_ui) delete x._am2_ui;
		return x;
	}

	function ensureWizardUi(wd) {
		if (!wd || typeof wd !== "object") return { showOptional: true };
		if (!wd._am2_ui || typeof wd._am2_ui !== "object") {
			wd._am2_ui = {
				dragId: null,
				dropBeforeId: null,
				showOptional: true,
				validation: { ok: null, local: [], server: [] },
				showRawError: false,
				hasErrorDetails: false,
			};
		}
		return wd._am2_ui;
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

	function mutateWizard(fn, opts) {
		const FE = W.AM2FlowEditorState;
		if (!FE || !FE.mutateWizard) return;
		FE.mutateWizard((wd) => {
			fn && fn(ensureWizardUi(wd), wd);
		}, opts || null);
	}

	function setSelectedStep(stepIdOrNull) {
		const FE = W.AM2FlowEditorState;
		if (FE && FE.setSelectedStep) FE.setSelectedStep(stepIdOrNull || null);
	}

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

	function ensureV2() {
		mutateWizard(
			(uiState, wd) => {
				// Only normalize when required; avoid marking the draft dirty for
				// internal idempotent migrations.
				if (wd && typeof wd === "object") {
					const v2 = wd.version === 2;
					const hasWizardId = Object.hasOwn(wd, "wizard_id");
					const g = wd.graph;
					const graphOk =
						g &&
						typeof g === "object" &&
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
				Object.keys(wd).forEach((k) => {
					delete wd[k];
				});
				for (const k in next) {
					wd[k] = next[k];
				}
			},
			{ markDirty: false, resetValidation: false, reason: "normalize_v2" },
		);
	}

	const paletteItems = [];

	function renderCanvasPanel() {
		const renderer = W.AM2FlowCanvasPanel;
		if (!renderer || !renderer.renderCanvas) return;
		const graph = stableGraph(wizardDraft());
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

	function isOptionalStep(stepId) {
		const sid = String(stepId || "");
		return (
			sid &&
			sid !== "select_authors" &&
			sid !== "select_books" &&
			sid !== "processing"
		);
	}

	function canRemove(stepId) {
		return isOptionalStep(stepId);
	}

	function hasStep(stepId) {
		const g = stableGraph(wizardDraft());
		const nodes = Array.isArray(g.nodes) ? g.nodes : [];
		return nodes.indexOf(String(stepId || "")) >= 0;
	}

	function addStep(stepId) {
		ensureV2();
		mutateWizard((uiState, wd) => {
			const g = stableGraph(wd);
			const nodes = Array.isArray(g.nodes) ? g.nodes.slice(0) : [];
			const sid = String(stepId || "");
			if (!sid || nodes.indexOf(sid) >= 0) return;
			nodes.splice(nodes.length - 1, 0, sid);
			const next = defFromGraph(nodes, g.entry, g.edges);
			next._am2_ui = uiState;
			Object.keys(wd).forEach((k) => {
				delete wd[k];
			});
			for (const k in next) {
				wd[k] = next[k];
			}
		});
	}

	function removeStep(stepId) {
		ensureV2();
		mutateWizard((uiState, wd) => {
			const g = stableGraph(wd);
			const sid = String(stepId || "");
			const nodes = Array.isArray(g.nodes) ? g.nodes.slice(0) : [];
			const idx = nodes.indexOf(sid);
			if (idx < 0) return;
			if (!canRemove(sid)) return;
			nodes.splice(idx, 1);
			const edges = (Array.isArray(g.edges) ? g.edges : []).filter(
				(e) =>
					String(e.from_step_id || "") !== sid &&
					String(e.to_step_id || "") !== sid,
			);
			const next = defFromGraph(nodes, g.entry, edges);
			next._am2_ui = uiState;
			Object.keys(wd).forEach((k) => {
				delete wd[k];
			});
			for (const k in next) {
				wd[k] = next[k];
			}
			if (selectedStepId() === sid) setSelectedStep(null);
		});
	}

	function reorderStep(dragStepId, dropBeforeStepIdOrNull) {
		ensureV2();
		mutateWizard((uiState, wd) => {
			const g = stableGraph(wd);
			const nodes = Array.isArray(g.nodes) ? g.nodes.slice(0) : [];
			const dragId = String(dragStepId || "");
			const dropBeforeId = dropBeforeStepIdOrNull
				? String(dropBeforeStepIdOrNull)
				: null;
			const fromIdx = nodes.indexOf(dragId);
			if (fromIdx < 0) return;
			if (dropBeforeId && dropBeforeId === dragId) return;
			nodes.splice(fromIdx, 1);
			let toIdx = -1;
			if (dropBeforeId) toIdx = nodes.indexOf(dropBeforeId);
			if (toIdx < 0) {
				nodes.push(dragId);
			} else {
				nodes.splice(toIdx, 0, dragId);
			}
			const next = defFromGraph(nodes, g.entry, g.edges);
			next._am2_ui = uiState;
			Object.keys(wd).forEach((k) => {
				delete wd[k];
			});
			for (const k in next) {
				wd[k] = next[k];
			}
		});
	}

	function moveStepUp(stepId) {
		ensureV2();
		mutateWizard((uiState, wd) => {
			const g = stableGraph(wd);
			const nodes = Array.isArray(g.nodes) ? g.nodes.slice(0) : [];
			const sid = String(stepId || "");
			const idx = nodes.indexOf(sid);
			if (idx <= 0) return;
			const tmp = nodes[idx - 1];
			nodes[idx - 1] = nodes[idx];
			nodes[idx] = tmp;
			const next = defFromGraph(nodes, g.entry, g.edges);
			next._am2_ui = uiState;
			Object.keys(wd).forEach((k) => {
				delete wd[k];
			});
			for (const k in next) {
				wd[k] = next[k];
			}
		});
	}

	function moveStepDown(stepId) {
		ensureV2();
		mutateWizard((uiState, wd) => {
			const g = stableGraph(wd);
			const nodes = Array.isArray(g.nodes) ? g.nodes.slice(0) : [];
			const sid = String(stepId || "");
			const idx = nodes.indexOf(sid);
			if (idx < 0 || idx >= nodes.length - 1) return;
			const tmp = nodes[idx + 1];
			nodes[idx + 1] = nodes[idx];
			nodes[idx] = tmp;
			const next = defFromGraph(nodes, g.entry, g.edges);
			next._am2_ui = uiState;
			Object.keys(wd).forEach((k) => {
				delete wd[k];
			});
			for (const k in next) {
				wd[k] = next[k];
			}
		});
	}
	function addEdge(fromId, toId, prio, whenVal) {
		ensureV2();
		mutateWizard((uiState, wd) => {
			const g = stableGraph(wd);
			const edges = Array.isArray(g.edges) ? g.edges.slice(0) : [];
			edges.push({
				from_step_id: String(fromId || ""),
				to_step_id: String(toId || ""),
				priority: Number(prio || 0),
				when: whenVal === undefined ? null : whenVal,
			});
			const next = defFromGraph(g.nodes, g.entry, edges);
			next._am2_ui = uiState;
			Object.keys(wd).forEach((k) => {
				delete wd[k];
			});
			for (const k in next) {
				wd[k] = next[k];
			}
		});
	}

	function removeEdge(fromId, outgoingIndex) {
		ensureV2();
		mutateWizard((uiState, wd) => {
			const g = stableGraph(wd);
			const from = String(fromId || "");
			const edgesAll = Array.isArray(g.edges) ? g.edges.slice(0) : [];
			const outgoing = edgesAll.filter(
				(e) => String(e.from_step_id || "") === from,
			);
			const target = outgoing[outgoingIndex];
			if (!target) return;
			const idx = edgesAll.indexOf(target);
			if (idx < 0) return;
			edgesAll.splice(idx, 1);
			const next = defFromGraph(g.nodes, g.entry, edgesAll);
			next._am2_ui = uiState;
			Object.keys(wd).forEach((k) => {
				delete wd[k];
			});
			for (const k in next) {
				wd[k] = next[k];
			}
		});
	}

	function updateEdge(fromId, outgoingIndex, newEdge) {
		ensureV2();
		mutateWizard((uiState, wd) => {
			const g = stableGraph(wd);
			const from = String(fromId || "");
			const edgesAll = Array.isArray(g.edges) ? g.edges.slice(0) : [];
			const outgoing = edgesAll.filter(
				(e) => String(e.from_step_id || "") === from,
			);
			const target = outgoing[outgoingIndex];
			if (!target) return;
			const idx = edgesAll.indexOf(target);
			if (idx < 0) return;
			const nextEdge = {
				from_step_id: from,
				to_step_id: String(
					newEdge && newEdge.to_step_id ? newEdge.to_step_id : "",
				),
				priority: Number(newEdge && newEdge.priority ? newEdge.priority : 0),
				when: newEdge && "when" in newEdge ? newEdge.when : null,
			};
			edgesAll[idx] = nextEdge;
			const next = defFromGraph(g.nodes, g.entry, edgesAll);
			next._am2_ui = uiState;
			Object.keys(wd).forEach((k) => {
				delete wd[k];
			});
			Object.assign(wd, next);
		});
	}

	function moveEdge(fromId, outgoingIndex, dir) {
		ensureV2();
		mutateWizard((uiState, wd) => {
			const g = stableGraph(wd);
			const from = String(fromId || "");
			const edgesAll = Array.isArray(g.edges) ? g.edges.slice(0) : [];
			const outgoing = edgesAll
				.filter((e) => String(e.from_step_id || "") === from)
				.map((e, i) => ({ edge: e, outgoingIndex: i }));
			const target = outgoing[outgoingIndex];
			if (!target) return;
			const byPri = outgoing
				.slice(0)
				.sort(
					(a, b) => Number(a.edge.priority || 0) - Number(b.edge.priority || 0),
				);
			const pos = byPri.findIndex((x) => x.outgoingIndex === outgoingIndex);
			if (pos < 0) return;
			const nextPos = pos + (dir < 0 ? -1 : 1);
			if (nextPos < 0 || nextPos >= byPri.length) return;
			const a = byPri[pos].edge;
			const b = byPri[nextPos].edge;
			const aPri = Number(a.priority || 0);
			const bPri = Number(b.priority || 0);
			a.priority = bPri;
			b.priority = aPri;
			const next = defFromGraph(g.nodes, g.entry, edgesAll);
			next._am2_ui = uiState;
			Object.keys(wd).forEach((k) => {
				delete wd[k];
			});
			Object.assign(wd, next);
		});
	}

	function setValidation(ok, localMsgs, serverMsgs) {
		mutateWizard((uiState) => {
			uiState.validation = {
				ok: ok,
				local: Array.isArray(localMsgs) ? localMsgs : [],
				server: Array.isArray(serverMsgs) ? serverMsgs : [],
			};
		});
	}

	function validationMessages() {
		const u = ensureWizardUi(wizardDraft());
		const v = u.validation || {};
		const msgs = [];
		(Array.isArray(v.local) ? v.local : []).forEach((m) => {
			msgs.push(m);
		});
		(Array.isArray(v.server) ? v.server : []).forEach((m) => {
			msgs.push(m);
		});
		return msgs;
	}

	function extractServerMessages(errEnvelope) {
		const outer =
			errEnvelope && typeof errEnvelope === "object" ? errEnvelope : null;
		const inner =
			outer && outer.error && typeof outer.error === "object"
				? outer.error
				: outer;
		const details = inner && inner.details;
		const out = [];
		const msg = inner && inner.message;
		if (msg) out.push(String(msg));
		(Array.isArray(details) ? details : []).forEach((d) => {
			if (!d) return;
			const path = d.path ? String(d.path) : "";
			const reason = d.reason ? String(d.reason) : "";
			if (path || reason) out.push(path + " " + reason);
		});
		return out;
	}

	function renderError(data, collapseByDefault) {
		H.renderError(ui.err, data);
		mutateWizard((uiState) => {
			uiState.hasErrorDetails = !!data;
			uiState.showRawError = data ? !collapseByDefault : false;
		});
	}

	function setupRawErrorPanel() {
		const rawErrorState = {};
		Object.defineProperty(rawErrorState, "showRawError", {
			get: () => !!(wizardDraft()._am2_ui || {}).showRawError,
			set: (on) => {
				mutateWizard((uiState) => {
					uiState.showRawError = !!on;
				});
			},
		});
		Object.defineProperty(rawErrorState, "hasErrorDetails", {
			get: () => !!(wizardDraft()._am2_ui || {}).hasErrorDetails,
			set: (on) => {
				mutateWizard((uiState) => {
					uiState.hasErrorDetails = !!on;
				});
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

	function confirmIfDirty(actionName) {
		if (!isDirty()) return true;
		return window.confirm(
			actionName +
				" will discard unsaved edits. Run Validate All first, or reload after saving. Continue?",
		);
	}

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
			const defn = out.data && out.data.definition ? out.data.definition : {};
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
			const defn = out.data && out.data.definition ? out.data.definition : {};
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
				const defn = out.data && out.data.definition ? out.data.definition : {};
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
			const defn = out.data && out.data.definition ? out.data.definition : {};
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
			const defn = out.data && out.data.definition ? out.data.definition : {};
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

		const btnAdd = text("button", "btn", "Add Step");
		const optLabel = el("label", "wdToggle");
		const optToggle = el("input", "wdToggleInput");
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
			mutateWizard((uiState) => {
				uiState.showOptional = !!optToggle.checked;
			});
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
		ui.reload.addEventListener("click", () =>
			(v3() || {}).reloadAll ? v3().reloadAll() : reloadAll(),
		);
	if (ui.validate)
		ui.validate.addEventListener("click", () =>
			(v3() || {}).validateDraft ? v3().validateDraft() : validateDraft(),
		);
	if (ui.save)
		ui.save.addEventListener("click", () =>
			(v3() || {}).saveDraft ? v3().saveDraft() : saveDraft(),
		);
	if (ui.reset)
		ui.reset.addEventListener("click", () =>
			(v3() || {}).resetDefinition ? v3().resetDefinition() : resetDefinition(),
		);

	W.AM2WizardDefinitionEditor = {
		reloadAll: () => ((v3() || {}).reloadAll ? v3().reloadAll() : reloadAll()),
		validateDraft: () =>
			(v3() || {}).validateDraft ? v3().validateDraft() : validateDraft(),
		saveDraft: () => ((v3() || {}).saveDraft ? v3().saveDraft() : saveDraft()),
		resetDefinition: () =>
			(v3() || {}).resetDefinition ? v3().resetDefinition() : resetDefinition(),
	};

	W.AM2FlowEditor = W.AM2FlowEditor || {};
	W.AM2FlowEditor.wizard = {
		reload: () => ((v3() || {}).reloadAll ? v3().reloadAll() : reloadAll()),
		validate: () =>
			(v3() || {}).validateDraft ? v3().validateDraft() : validateDraft(),
		save: () => ((v3() || {}).saveDraft ? v3().saveDraft() : saveDraft()),
		reset: () =>
			(v3() || {}).resetDefinition ? v3().resetDefinition() : resetDefinition(),
	};

	reloadAll({ skipConfirm: true });
})();
