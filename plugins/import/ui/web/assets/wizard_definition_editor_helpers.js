(() => {
	const W = /** @type {(Window & typeof globalThis) & {
	 *   AM2WizardDefinitionEditorHelpers?: AM2WizardDefinitionEditorHelpersApi,
	 * }} */ (window);

	/** @param {AM2WizardDefinitionEditorGraphOpsDeps} deps */
	function createGraphOps(deps) {
		const {
			stableGraph,
			wizardDraft,
			ensureV2,
			mutateWizard,
			defFromGraph,
			replaceWizardDraft,
			selectedStepId,
			setSelectedStep,
		} = deps;

		/** @param {string | null | undefined} stepId */
		function isOptionalStep(stepId) {
			const sid = String(stepId || "");
			return (
				sid &&
				sid !== "select_authors" &&
				sid !== "select_books" &&
				sid !== "processing"
			);
		}

		/** @param {string | null | undefined} stepId */
		function canRemove(stepId) {
			return isOptionalStep(stepId);
		}

		/** @param {string | null | undefined} stepId */
		function hasStep(stepId) {
			const g = stableGraph(wizardDraft());
			const nodes = Array.isArray(g.nodes) ? g.nodes : [];
			return nodes.indexOf(String(stepId || "")) >= 0;
		}

		/** @param {string | null | undefined} stepId */
		function addStep(stepId) {
			ensureV2();
			mutateWizard(
				/** @param {AM2WizardUiState} uiState @param {AM2JsonObject} wd */ (
					uiState,
					wd,
				) => {
					const g = stableGraph(wd);
					const nodes = Array.isArray(g.nodes) ? g.nodes.slice(0) : [];
					const sid = String(stepId || "");
					if (!sid || nodes.indexOf(sid) >= 0) return;
					nodes.splice(nodes.length - 1, 0, sid);
					const next = defFromGraph(nodes, g.entry, g.edges);
					next._am2_ui = uiState;
					replaceWizardDraft(wd, next);
				},
			);
		}

		/** @param {string | null | undefined} stepId */
		function removeStep(stepId) {
			ensureV2();
			mutateWizard(
				/** @param {AM2WizardUiState} uiState @param {AM2JsonObject} wd */ (
					uiState,
					wd,
				) => {
					const g = stableGraph(wd);
					const sid = String(stepId || "");
					const nodes = Array.isArray(g.nodes) ? g.nodes.slice(0) : [];
					const idx = nodes.indexOf(sid);
					if (idx < 0) return;
					if (!canRemove(sid)) return;
					nodes.splice(idx, 1);
					const edges = (Array.isArray(g.edges) ? g.edges : []).filter(
						/** @param {AM2WizardDefinitionGraphEdge} e */ (e) =>
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
				},
			);
		}

		/**
		 * @param {string | null | undefined} dragStepId
		 * @param {string | null | undefined} dropBeforeStepIdOrNull
		 */
		function reorderStep(dragStepId, dropBeforeStepIdOrNull) {
			ensureV2();
			mutateWizard(
				/** @param {AM2WizardUiState} uiState @param {AM2JsonObject} wd */ (
					uiState,
					wd,
				) => {
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
					replaceWizardDraft(wd, next);
				},
			);
		}

		/** @param {string | null | undefined} stepId */
		function moveStepUp(stepId) {
			ensureV2();
			mutateWizard(
				/** @param {AM2WizardUiState} uiState @param {AM2JsonObject} wd */ (
					uiState,
					wd,
				) => {
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
					replaceWizardDraft(wd, next);
				},
			);
		}

		/** @param {string | null | undefined} stepId */
		function moveStepDown(stepId) {
			ensureV2();
			mutateWizard(
				/** @param {AM2WizardUiState} uiState @param {AM2JsonObject} wd */ (
					uiState,
					wd,
				) => {
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
					replaceWizardDraft(wd, next);
				},
			);
		}
		/**
		 * @param {string | null | undefined} fromId
		 * @param {string | null | undefined} toId
		 * @param {number | string | null | undefined} prio
		 * @param {AM2JsonValue} whenVal
		 */
		function addEdge(fromId, toId, prio, whenVal) {
			ensureV2();
			mutateWizard(
				/** @param {AM2WizardUiState} uiState @param {AM2JsonObject} wd */ (
					uiState,
					wd,
				) => {
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
					replaceWizardDraft(wd, next);
				},
			);
		}

		/** @param {string | null | undefined} fromId @param {number} outgoingIndex */
		function removeEdge(fromId, outgoingIndex) {
			ensureV2();
			mutateWizard(
				/** @param {AM2WizardUiState} uiState @param {AM2JsonObject} wd */ (
					uiState,
					wd,
				) => {
					const g = stableGraph(wd);
					const from = String(fromId || "");
					const edgesAll = Array.isArray(g.edges) ? g.edges.slice(0) : [];
					const outgoing = edgesAll.filter(
						/** @param {AM2WizardDefinitionGraphEdge} e */ (e) =>
							String(e.from_step_id || "") === from,
					);
					const target = outgoing[outgoingIndex];
					if (!target) return;
					const idx = edgesAll.indexOf(target);
					if (idx < 0) return;
					edgesAll.splice(idx, 1);
					const next = defFromGraph(g.nodes, g.entry, edgesAll);
					next._am2_ui = uiState;
					replaceWizardDraft(wd, next);
				},
			);
		}

		/**
		 * @param {string | null | undefined} fromId
		 * @param {number} outgoingIndex
		 * @param {AM2WizardDefinitionGraphEdge} newEdge
		 */
		function updateEdge(fromId, outgoingIndex, newEdge) {
			ensureV2();
			mutateWizard(
				/** @param {AM2WizardUiState} uiState @param {AM2JsonObject} wd */ (
					uiState,
					wd,
				) => {
					const g = stableGraph(wd);
					const from = String(fromId || "");
					const edgesAll = Array.isArray(g.edges) ? g.edges.slice(0) : [];
					const outgoing = edgesAll.filter(
						/** @param {AM2WizardDefinitionGraphEdge} e */ (e) =>
							String(e.from_step_id || "") === from,
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
						priority: Number(
							newEdge && newEdge.priority ? newEdge.priority : 0,
						),
						when: newEdge && "when" in newEdge ? newEdge.when : null,
					};
					edgesAll[idx] = nextEdge;
					const next = defFromGraph(g.nodes, g.entry, edgesAll);
					next._am2_ui = uiState;
					replaceWizardDraft(wd, next);
				},
			);
		}

		/** @param {string | null | undefined} fromId @param {number} outgoingIndex @param {number} dir */
		function moveEdge(fromId, outgoingIndex, dir) {
			ensureV2();
			mutateWizard(
				/** @param {AM2WizardUiState} uiState @param {AM2JsonObject} wd */ (
					uiState,
					wd,
				) => {
					const g = stableGraph(wd);
					const from = String(fromId || "");
					const edgesAll = Array.isArray(g.edges) ? g.edges.slice(0) : [];
					/** @type {{ edge: AM2WizardDefinitionGraphEdge, outgoingIndex: number }[]} */
					const outgoing = [];
					for (const [index, edge] of edgesAll.entries()) {
						if (String(edge.from_step_id || "") !== from) continue;
						outgoing.push({ edge, outgoingIndex: index });
					}
					const target = outgoing[outgoingIndex];
					if (!target) return;
					const byPri = outgoing.slice(0);
					byPri.sort(
						/**
						 * @param {{ edge: AM2WizardDefinitionGraphEdge, outgoingIndex: number }} a
						 * @param {{ edge: AM2WizardDefinitionGraphEdge, outgoingIndex: number }} b
						 */
						(a, b) =>
							Number(a.edge.priority || 0) - Number(b.edge.priority || 0),
					);
					const pos = byPri.findIndex(
						/** @param {{ edge: AM2WizardDefinitionGraphEdge, outgoingIndex: number }} x */
						(x) => x.outgoingIndex === outgoingIndex,
					);
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
					replaceWizardDraft(wd, next);
				},
			);
		}

		return {
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
		};
	}

	W.AM2WizardDefinitionEditorHelpers = { createGraphOps };
})();
