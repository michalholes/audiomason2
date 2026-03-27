(function () {
	"use strict";

	/**
	 * @typedef {(graph: AM2DSLGraphDefinition | AM2DSLEditorLibrary,
	 * 	definition: AM2DSLGraphDefinition,
	 * 	libraryId: string) => void} AM2GraphMutator
	 */
	/**
	 * @typedef {(node: AM2DSLGraphNode,
	 * 	graph: AM2DSLGraphDefinition | AM2DSLEditorLibrary,
	 * 	definition: AM2DSLGraphDefinition,
	 * 	libraryId: string) => void} AM2SelectedNodeMutator
	 */

	/** @returns {AM2FlowSnapshot | null} */
	function snapshot() {
		const flowEditor = window.AM2FlowEditorState;
		return flowEditor && flowEditor.getSnapshot
			? flowEditor.getSnapshot()
			: null;
	}

	/** @returns {AM2DSLGraphDefinition} */
	function currentDefinition() {
		const snap = snapshot();
		return /** @type {AM2DSLGraphDefinition} */ (
			(snap && snap.wizardDraft) || {}
		);
	}

	/** @returns {AM2JsonObject} */
	function currentConfig() {
		const snap = snapshot();
		return (snap && snap.configDraft) || {};
	}

	/** @param {AM2JsonObject | null | undefined} definition
	 * @returns {boolean}
	 */
	function isV3Draft(definition) {
		return !!(
			definition &&
			definition.version === 3 &&
			Array.isArray(definition.nodes)
		);
	}

	/** @returns {string} */
	function selectedStepId() {
		const snap = snapshot();
		return String((snap && snap.selectedStepId) || "");
	}

	/** @param {string | null | undefined} stepId */
	function setSelectedStep(stepId) {
		const flowEditor = window.AM2FlowEditorState;
		if (flowEditor && flowEditor.setSelectedStep) {
			flowEditor.setSelectedStep(stepId || null);
		}
	}

	/**
	 * @param {(definition: AM2DSLGraphDefinition) => void} mutator
	 * @param {AM2FlowMutationOptions | null | undefined} [opts]
	 */
	function mutateWizard(mutator, opts) {
		const flowEditor = window.AM2FlowEditorState;
		if (flowEditor && flowEditor.mutateWizard) {
			flowEditor.mutateWizard(mutator, opts || null);
		}
	}

	/**
	 * @param {AM2DSLGraphDefinition | null | undefined} definition
	 * @param {AM2FlowLoadAllOptions | null | undefined} [opts]
	 */
	function loadAll(definition, opts) {
		const flowEditor = window.AM2FlowEditorState;
		if (!flowEditor || !flowEditor.loadAll) {
			return;
		}
		flowEditor.loadAll(
			{
				wizardDefinition: definition || {},
				flowConfig: currentConfig(),
			},
			opts || { preserveValidation: true },
		);
	}

	/** @param {AM2DSLGraphDefinition | null | undefined} definition */
	function markValidated(definition) {
		const flowEditor = window.AM2FlowEditorState;
		if (!flowEditor || !flowEditor.markValidated) {
			return;
		}
		flowEditor.markValidated({
			canonicalWizardDefinition: definition || {},
			canonicalFlowConfig: currentConfig(),
			validationEnvelope: { ok: true },
		});
	}

	/**
	 * @param {AM2PrimitiveRegistryShape | null | undefined} registry
	 * @returns {AM2PrimitiveRegistryItem[]}
	 */
	function primitiveItems(registry) {
		if (!registry || !Array.isArray(registry.primitives)) {
			return [];
		}
		return /** @type {AM2PrimitiveRegistryItem[]} */ (registry.primitives);
	}

	/**
	 * @param {AM2DSLGraphNode | null | undefined} node
	 * @param {AM2PrimitiveRegistryShape | null | undefined} registry
	 * @returns {AM2PrimitiveRegistryItem | null}
	 */
	function primitiveMeta(node, registry) {
		const primitiveId = String((node && node.op && node.op.primitive_id) || "");
		const version = String(
			(node && node.op && node.op.primitive_version) || "",
		);
		return (
			primitiveItems(registry).find(
				(item) =>
					String(item.primitive_id || "") === primitiveId &&
					String(item.version || "") === version,
			) || null
		);
	}

	/**
	 * @param {AM2DSLGraphDefinition} definition
	 * @returns {AM2DSLEditorUiState | null}
	 */
	function readEditorState(definition) {
		const uiState = definition._am2_ui;
		const editorState = uiState && uiState.dsl_editor;
		return editorState && typeof editorState === "object" ? editorState : null;
	}

	/**
	 * @param {AM2DSLGraphDefinition} definition
	 * @returns {AM2DSLEditorUiState}
	 */
	function ensureEditorState(definition) {
		if (!definition._am2_ui || typeof definition._am2_ui !== "object") {
			definition._am2_ui = {};
		}
		if (
			!definition._am2_ui.dsl_editor ||
			typeof definition._am2_ui.dsl_editor !== "object"
		) {
			definition._am2_ui.dsl_editor = {};
		}
		return definition._am2_ui.dsl_editor;
	}

	/**
	 * @param {AM2DSLGraphDefinition} definition
	 * @returns {Record<string, AM2DSLEditorLibrary>}
	 */
	function libraryMap(definition) {
		const libraries = definition.libraries;
		return libraries && typeof libraries === "object"
			? /** @type {Record<string, AM2DSLEditorLibrary>} */ (libraries)
			: {};
	}

	/**
	 * @param {AM2DSLGraphDefinition} definition
	 * @returns {Record<string, AM2DSLEditorLibrary>}
	 */
	function ensureLibraries(definition) {
		if (!definition.libraries || typeof definition.libraries !== "object") {
			definition.libraries = {};
		}
		return definition.libraries;
	}

	/** @returns {string} */
	function selectedLibraryId() {
		const definition = currentDefinition();
		const editorState = readEditorState(definition);
		const libraryId = String(
			(editorState && editorState.selected_library_id) || "",
		);
		return libraryMap(definition)[libraryId] ? libraryId : "";
	}

	/** @param {string | null | undefined} libraryId */
	function setSelectedLibrary(libraryId) {
		const nextLibraryId = String(libraryId || "");
		mutateWizard(
			function (definition) {
				const editorState = ensureEditorState(definition);
				editorState.selected_library_id = libraryMap(definition)[nextLibraryId]
					? nextLibraryId
					: "";
			},
			{ markDirty: false, reason: "select_library", resetValidation: false },
		);
		setSelectedStep(null);
	}

	/** @returns {AM2DSLGraphDefinition} */
	function currentGraphDefinition() {
		const definition = currentDefinition();
		const libraryId = selectedLibraryId();
		return libraryId
			? libraryMap(definition)[libraryId] || definition
			: definition;
	}

	/** @returns {string} */
	function currentGraphLabel() {
		const libraryId = selectedLibraryId();
		return libraryId ? "library:" + libraryId : "root";
	}

	/**
	 * @param {AM2DSLGraphDefinition | AM2DSLEditorLibrary | null | undefined} definition
	 * @returns {AM2DSLGraphNode[]}
	 */
	function graphNodes(definition) {
		if (!definition || !Array.isArray(definition.nodes)) {
			return [];
		}
		return /** @type {AM2DSLGraphNode[]} */ (definition.nodes);
	}

	/**
	 * @param {AM2DSLGraphDefinition | AM2DSLEditorLibrary | null | undefined} definition
	 * @returns {AM2DSLEditorEdgeRecord[]}
	 */
	function graphEdges(definition) {
		if (!definition || !Array.isArray(definition.edges)) {
			return [];
		}
		return /** @type {AM2DSLEditorEdgeRecord[]} */ (definition.edges);
	}

	/** @returns {AM2DSLGraphNode | null} */
	function currentNode() {
		const stepId = selectedStepId();
		const nodes = graphNodes(currentGraphDefinition());
		return nodes.find((item) => String(item.step_id || "") === stepId) || null;
	}

	/**
	 * @param {string | null | undefined} value
	 * @param {Set<string>} seenValues
	 * @param {string} fallback
	 * @returns {string}
	 */
	function sanitizeId(value, seenValues, fallback) {
		const base =
			String(value || fallback)
				.toLowerCase()
				.replace(/[^a-z0-9]+/g, "_")
				.replace(/^_+|_+$/g, "") || fallback;
		if (!seenValues.has(base)) {
			return base;
		}
		let counter = 2;
		while (seenValues.has(base + "_" + String(counter))) {
			counter += 1;
		}
		return base + "_" + String(counter);
	}

	/** @param {string | null | undefined} value
	 * @returns {string}
	 */
	function sanitizeStepId(value) {
		const nodes = graphNodes(currentGraphDefinition());
		const seen = new Set(nodes.map((item) => String(item.step_id || "")));
		return sanitizeId(value, seen, "step");
	}

	/** @param {string | null | undefined} value
	 * @returns {string}
	 */
	function sanitizeLibraryId(value) {
		const seen = new Set(Object.keys(libraryMap(currentDefinition())));
		return sanitizeId(value, seen, "library");
	}

	/**
	 * @param {AM2DSLGraphDefinition | AM2DSLEditorLibrary} graph
	 * @returns {AM2DSLGraphDefinition | AM2DSLEditorLibrary}
	 */
	function ensureGraph(graph) {
		if (!Array.isArray(graph.nodes)) {
			graph.nodes = [];
		}
		if (!Array.isArray(graph.edges)) {
			graph.edges = [];
		}
		return graph;
	}

	/**
	 * @param {AM2GraphMutator} mutator
	 * @param {AM2FlowMutationOptions | null | undefined} [opts]
	 */
	function mutateCurrentGraph(mutator, opts) {
		mutateWizard(function (definition) {
			const libraryId = selectedLibraryId();
			const graph =
				libraryId && ensureLibraries(definition)[libraryId]
					? ensureGraph(ensureLibraries(definition)[libraryId])
					: ensureGraph(definition);
			mutator(graph, definition, libraryId);
		}, opts);
	}

	/** @param {AM2PrimitiveRegistryItem} item */
	function addPrimitiveNode(item) {
		const stepId = sanitizeStepId(
			String(item.primitive_id || "").replace(/\./g, "_"),
		);
		mutateCurrentGraph(function (graph) {
			/** @type {AM2DSLGraphNode} */
			const nextNode = {
				step_id: stepId,
				op: {
					primitive_id: String(item.primitive_id || ""),
					primitive_version: Number(item.version || 1),
					inputs: {},
					writes: [],
				},
			};
			graph.nodes.push(nextNode);

			if (!graph.entry_step_id) {
				graph.entry_step_id = stepId;
			}
		});
		setSelectedStep(stepId);
	}

	/** @param {AM2JsonObject} update */
	function patchNode(update) {
		const stepId = selectedStepId();
		if (!stepId) {
			return;
		}
		mutateCurrentGraph(function (graph) {
			const nodes = graphNodes(graph);
			const node = nodes.find((item) => String(item.step_id || "") === stepId);
			if (!node) {
				return;
			}
			if (!node.op || typeof node.op !== "object") {
				node.op = {};
			}
			if (Object.prototype.hasOwnProperty.call(update, "step_id")) {
				const nextId = String(update.step_id || "");
				const prevId = String(node.step_id || "");
				node.step_id = nextId;
				if (graph.entry_step_id === prevId) {
					graph.entry_step_id = nextId;
				}
				graphEdges(graph).forEach(function (edge) {
					if (edge.from === prevId) {
						edge.from = nextId;
					}
					if (edge.to === prevId) {
						edge.to = nextId;
					}
				});
				setSelectedStep(nextId);
			}
			if (Object.prototype.hasOwnProperty.call(update, "primitive_id")) {
				node.op.primitive_id = String(update.primitive_id || "");
			}
			if (Object.prototype.hasOwnProperty.call(update, "primitive_version")) {
				node.op.primitive_version = Number(update.primitive_version || 0);
			}
			if (Object.prototype.hasOwnProperty.call(update, "inputs")) {
				node.op.inputs = /** @type {AM2JsonObject} */ (update.inputs || {});
			}
		});
	}

	/**
	 * @param {AM2SelectedNodeMutator} fn
	 */
	function withSelectedNode(fn) {
		const stepId = selectedStepId();
		if (!stepId) {
			return;
		}
		mutateCurrentGraph(function (graph, definition, libraryId) {
			const node = graphNodes(graph).find(
				(item) => String(item.step_id || "") === stepId,
			);
			if (node) {
				fn(node, graph, definition, libraryId);
			}
		});
	}

	/** @param {string | null | undefined} stepId */
	function removeNode(stepId) {
		mutateCurrentGraph(function (graph) {
			const selectedId = String(stepId || "");
			graph.nodes = graphNodes(graph).filter(
				(item) => String(item.step_id || "") !== selectedId,
			);
			graph.edges = graphEdges(graph).filter(
				(edge) => edge.from !== selectedId && edge.to !== selectedId,
			);
			if (graph.entry_step_id === selectedId) {
				graph.entry_step_id = graph.nodes[0]
					? String(graph.nodes[0].step_id || "")
					: "";
			}
		});
		const nodes = graphNodes(currentGraphDefinition());
		setSelectedStep(nodes[0] ? String(nodes[0].step_id || "") : null);
	}

	/** @returns {AM2DSLEditorWriteRecord} */
	function createEmptyWrite() {
		return { to_path: "", value: null };
	}

	function addWrite() {
		withSelectedNode(function (node) {
			if (!node.op || typeof node.op !== "object") {
				node.op = {};
			}
			if (!Array.isArray(node.op.writes)) {
				node.op.writes = [];
			}
			node.op.writes.push(createEmptyWrite());
		});
	}

	/**
	 * @param {number} index
	 * @param {AM2DSLEditorWriteRecord} item
	 */
	function patchWrite(index, item) {
		withSelectedNode(function (node) {
			if (node.op && Array.isArray(node.op.writes) && node.op.writes[index]) {
				node.op.writes[index] = item;
			}
		});
	}

	/** @param {number} index */
	function removeWrite(index) {
		withSelectedNode(function (node) {
			if (node.op && Array.isArray(node.op.writes)) {
				node.op.writes.splice(index, 1);
			}
		});
	}

	function clearSelectedNode() {
		withSelectedNode(function (node) {
			if (!node.op || typeof node.op !== "object") {
				node.op = {};
			}
			node.op.inputs = {};
			node.op.writes = [];
		});
	}

	/** @returns {void} */
	function addEdge() {
		const nodes = graphNodes(currentGraphDefinition());
		if (nodes.length < 2) {
			return;
		}
		mutateCurrentGraph(function (graph) {
			const edges = graphEdges(graph);
			edges.push({
				from: String(nodes[0].step_id || ""),
				to: String(nodes[1].step_id || ""),
			});
		});
	}

	/**
	 * @param {number} index
	 * @param {AM2DSLEditorEdgeRecord} edge
	 */
	function patchEdge(index, edge) {
		mutateCurrentGraph(function (graph) {
			const edges = graphEdges(graph);
			if (!edges[index]) {
				return;
			}
			/** @type {AM2DSLEditorEdgeRecord} */
			const next = { from: String(edge.from || ""), to: String(edge.to || "") };
			if (edge.condition_expr) {
				next.condition_expr = edge.condition_expr;
			}
			edges[index] = next;
		});
	}

	/** @param {number} index */
	function removeEdge(index) {
		mutateCurrentGraph(function (graph) {
			if (Array.isArray(graph.edges)) {
				graph.edges.splice(index, 1);
			}
		});
	}

	/** @param {string | null | undefined} name */
	function addLibrary(name) {
		const libraryId = sanitizeLibraryId(name || "library");
		mutateWizard(function (definition) {
			const libraries = ensureLibraries(definition);
			/** @type {AM2DSLEditorLibrary} */
			libraries[libraryId] = {
				entry_step_id: "",
				params: [],
				nodes: [],
				edges: [],
			};
			ensureEditorState(definition).selected_library_id = libraryId;
		});
		setSelectedStep(null);
	}

	/** @param {AM2JsonObject} update */
	function patchLibrary(update) {
		const libraryId = selectedLibraryId();
		if (!libraryId) {
			return;
		}
		mutateWizard(function (definition) {
			const library = ensureLibraries(definition)[libraryId];
			if (!library || typeof library !== "object") {
				return;
			}
			if (Object.prototype.hasOwnProperty.call(update, "entry_step_id")) {
				library.entry_step_id = String(update.entry_step_id || "");
			}
			if (Object.prototype.hasOwnProperty.call(update, "params")) {
				library.params = Array.isArray(update.params)
					? /** @type {AM2DSLEditorLibraryParam[]} */ (update.params)
					: [];
			}
		});
	}

	/** @param {string | null | undefined} libraryId */
	function removeLibrary(libraryId) {
		const selectedId = String(libraryId || "");
		mutateWizard(function (definition) {
			const libraries = ensureLibraries(definition);
			delete libraries[selectedId];
			const editorState = ensureEditorState(definition);
			if (editorState.selected_library_id === selectedId) {
				editorState.selected_library_id = "";
			}
		});
		setSelectedStep(null);
	}

	/** @type {AM2DSLEditorGraphOpsApi} */
	window["AM2DSLEditorGraphOps"] = {
		addEdge: addEdge,
		addLibrary: addLibrary,
		addPrimitiveNode: addPrimitiveNode,
		addWrite: addWrite,
		clearSelectedNode: clearSelectedNode,
		currentConfig: currentConfig,
		currentDefinition: currentDefinition,
		currentGraphDefinition: currentGraphDefinition,
		currentGraphLabel: currentGraphLabel,
		currentNode: currentNode,
		isV3Draft: isV3Draft,
		loadAll: loadAll,
		markValidated: markValidated,
		patchEdge: patchEdge,
		patchLibrary: patchLibrary,
		patchNode: patchNode,
		patchWrite: patchWrite,
		primitiveItems: primitiveItems,
		primitiveMeta: primitiveMeta,
		removeEdge: removeEdge,
		removeLibrary: removeLibrary,
		removeNode: removeNode,
		removeWrite: removeWrite,
		selectedLibraryId: selectedLibraryId,
		selectedStepId: selectedStepId,
		setSelectedLibrary: setSelectedLibrary,
		setSelectedStep: setSelectedStep,
	};
})();
