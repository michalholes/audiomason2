(function () {
	"use strict";

	function snapshot() {
		const flowEditor = window.AM2FlowEditorState;
		return flowEditor && flowEditor.getSnapshot
			? flowEditor.getSnapshot()
			: null;
	}

	function currentDefinition() {
		const snap = snapshot();
		return (snap && snap.wizardDraft) || {};
	}

	function currentConfig() {
		const snap = snapshot();
		return (snap && snap.configDraft) || {};
	}

	function isV3Draft(definition) {
		return !!(
			definition &&
			definition.version === 3 &&
			Array.isArray(definition.nodes)
		);
	}

	function selectedStepId() {
		const snap = snapshot();
		return String((snap && snap.selectedStepId) || "");
	}

	function setSelectedStep(stepId) {
		const flowEditor = window.AM2FlowEditorState;
		if (flowEditor && flowEditor.setSelectedStep) {
			flowEditor.setSelectedStep(stepId || null);
		}
	}

	function mutateWizard(mutator, opts) {
		const flowEditor = window.AM2FlowEditorState;
		if (flowEditor && flowEditor.mutateWizard) {
			flowEditor.mutateWizard(mutator, opts || null);
		}
	}

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

	function primitiveItems(registry) {
		return Array.isArray(registry && registry.primitives)
			? registry.primitives
			: [];
	}

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

	function readEditorState(definition) {
		const uiState = definition && definition._am2_ui;
		const editorState = uiState && uiState.dsl_editor;
		return editorState && typeof editorState === "object" ? editorState : null;
	}

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

	function libraryMap(definition) {
		const libraries = definition && definition.libraries;
		return libraries && typeof libraries === "object" ? libraries : {};
	}

	function ensureLibraries(definition) {
		if (!definition.libraries || typeof definition.libraries !== "object") {
			definition.libraries = {};
		}
		return definition.libraries;
	}

	function selectedLibraryId() {
		const definition = currentDefinition();
		const editorState = readEditorState(definition);
		const libraryId = String(
			(editorState && editorState.selected_library_id) || "",
		);
		return libraryMap(definition)[libraryId] ? libraryId : "";
	}

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

	function currentGraphDefinition() {
		const definition = currentDefinition();
		const libraryId = selectedLibraryId();
		return libraryId
			? libraryMap(definition)[libraryId] || definition
			: definition;
	}

	function currentGraphLabel() {
		const libraryId = selectedLibraryId();
		return libraryId ? "library:" + libraryId : "root";
	}

	function graphNodes(definition) {
		return Array.isArray(definition && definition.nodes)
			? definition.nodes
			: [];
	}

	function graphEdges(definition) {
		return Array.isArray(definition && definition.edges)
			? definition.edges
			: [];
	}

	function currentNode() {
		const stepId = selectedStepId();
		const nodes = graphNodes(currentGraphDefinition());
		return nodes.find((item) => String(item.step_id || "") === stepId) || null;
	}

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

	function sanitizeStepId(value) {
		const nodes = graphNodes(currentGraphDefinition());
		const seen = new Set(nodes.map((item) => String(item.step_id || "")));
		return sanitizeId(value, seen, "step");
	}

	function sanitizeLibraryId(value) {
		const seen = new Set(Object.keys(libraryMap(currentDefinition())));
		return sanitizeId(value, seen, "library");
	}

	function ensureGraph(graph) {
		if (!Array.isArray(graph.nodes)) {
			graph.nodes = [];
		}
		if (!Array.isArray(graph.edges)) {
			graph.edges = [];
		}
		return graph;
	}

	function mutateCurrentGraph(mutator, opts) {
		mutateWizard(function (definition) {
			const libraryId = selectedLibraryId();
			const graph = libraryId
				? ensureGraph(ensureLibraries(definition)[libraryId] || {})
				: ensureGraph(definition);
			mutator(graph, definition, libraryId);
		}, opts);
	}

	function addPrimitiveNode(item) {
		const stepId = sanitizeStepId(
			String(item.primitive_id || "").replace(/\./g, "_"),
		);
		mutateCurrentGraph(function (graph) {
			graph.nodes.push({
				step_id: stepId,
				op: {
					primitive_id: String(item.primitive_id || ""),
					primitive_version: Number(item.version || 1),
					inputs: {},
					writes: [],
				},
			});
			if (!graph.entry_step_id) {
				graph.entry_step_id = stepId;
			}
		});
		setSelectedStep(stepId);
	}

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
				node.op.inputs = update.inputs || {};
			}
		});
	}

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

	function patchWrite(index, item) {
		withSelectedNode(function (node) {
			if (node.op && Array.isArray(node.op.writes) && node.op.writes[index]) {
				node.op.writes[index] = item;
			}
		});
	}

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

	function addEdge() {
		const nodes = graphNodes(currentGraphDefinition());
		if (nodes.length < 2) {
			return;
		}
		mutateCurrentGraph(function (graph) {
			graph.edges.push({
				from: String(nodes[0].step_id || ""),
				to: String(nodes[1].step_id || ""),
			});
		});
	}

	function patchEdge(index, edge) {
		mutateCurrentGraph(function (graph) {
			if (!graphEdges(graph)[index]) {
				return;
			}
			const next = { from: String(edge.from || ""), to: String(edge.to || "") };
			if (edge.condition_expr) {
				next.condition_expr = edge.condition_expr;
			}
			graph.edges[index] = next;
		});
	}

	function removeEdge(index) {
		mutateCurrentGraph(function (graph) {
			if (Array.isArray(graph.edges)) {
				graph.edges.splice(index, 1);
			}
		});
	}

	function addLibrary(name) {
		const libraryId = sanitizeLibraryId(name || "library");
		mutateWizard(function (definition) {
			const libraries = ensureLibraries(definition);
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
				library.params = Array.isArray(update.params) ? update.params : [];
			}
		});
	}

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
