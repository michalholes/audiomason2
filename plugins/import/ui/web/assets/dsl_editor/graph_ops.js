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

	function currentNode() {
		const stepId = selectedStepId();
		const nodes = Array.isArray(currentDefinition().nodes)
			? currentDefinition().nodes
			: [];
		return nodes.find((item) => String(item.step_id || "") === stepId) || null;
	}

	function sanitizeStepId(value) {
		const base =
			String(value || "primitive")
				.toLowerCase()
				.replace(/[^a-z0-9]+/g, "_")
				.replace(/^_+|_+$/g, "") || "step";
		const nodes = Array.isArray(currentDefinition().nodes)
			? currentDefinition().nodes
			: [];
		const seen = new Set(nodes.map((item) => String(item.step_id || "")));
		if (!seen.has(base)) {
			return base;
		}
		let counter = 2;
		while (seen.has(base + "_" + String(counter))) {
			counter += 1;
		}
		return base + "_" + String(counter);
	}

	function addPrimitiveNode(item) {
		const stepId = sanitizeStepId(
			String(item.primitive_id || "").replace(/\./g, "_"),
		);
		mutateWizard(function (definition) {
			if (!Array.isArray(definition.nodes)) {
				definition.nodes = [];
			}
			definition.nodes.push({
				step_id: stepId,
				op: {
					primitive_id: String(item.primitive_id || ""),
					primitive_version: Number(item.version || 1),
					inputs: {},
					writes: [],
				},
			});
			if (!definition.entry_step_id) {
				definition.entry_step_id = stepId;
			}
		});
		setSelectedStep(stepId);
	}

	function patchNode(update) {
		const stepId = selectedStepId();
		if (!stepId) {
			return;
		}
		mutateWizard(function (definition) {
			const nodes = Array.isArray(definition.nodes) ? definition.nodes : [];
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
				if (definition.entry_step_id === prevId) {
					definition.entry_step_id = nextId;
				}
				const edges = Array.isArray(definition.edges) ? definition.edges : [];
				edges.forEach(function (edge) {
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
		mutateWizard(function (definition) {
			const nodes = Array.isArray(definition.nodes) ? definition.nodes : [];
			const node = nodes.find((item) => String(item.step_id || "") === stepId);
			if (node) {
				fn(node, definition);
			}
		});
	}

	function removeNode(stepId) {
		mutateWizard(function (definition) {
			const selectedId = String(stepId || "");
			definition.nodes = (
				Array.isArray(definition.nodes) ? definition.nodes : []
			).filter((item) => String(item.step_id || "") !== selectedId);
			definition.edges = (
				Array.isArray(definition.edges) ? definition.edges : []
			).filter((edge) => edge.from !== selectedId && edge.to !== selectedId);
			if (definition.entry_step_id === selectedId) {
				definition.entry_step_id = definition.nodes[0]
					? String(definition.nodes[0].step_id || "")
					: "";
			}
		});
		const nodes = Array.isArray(currentDefinition().nodes)
			? currentDefinition().nodes
			: [];
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
		const nodes = Array.isArray(currentDefinition().nodes)
			? currentDefinition().nodes
			: [];
		if (nodes.length < 2) {
			return;
		}
		mutateWizard(function (definition) {
			if (!Array.isArray(definition.edges)) {
				definition.edges = [];
			}
			definition.edges.push({
				from: String(nodes[0].step_id || ""),
				to: String(nodes[1].step_id || ""),
			});
		});
	}

	function patchEdge(index, edge) {
		mutateWizard(function (definition) {
			if (!Array.isArray(definition.edges) || !definition.edges[index]) {
				return;
			}
			const next = { from: String(edge.from || ""), to: String(edge.to || "") };
			if (edge.condition_expr) {
				next.condition_expr = edge.condition_expr;
			}
			definition.edges[index] = next;
		});
	}

	function removeEdge(index) {
		mutateWizard(function (definition) {
			if (Array.isArray(definition.edges)) {
				definition.edges.splice(index, 1);
			}
		});
	}

	window["AM2DSLEditorGraphOps"] = {
		addEdge: addEdge,
		addPrimitiveNode: addPrimitiveNode,
		addWrite: addWrite,
		clearSelectedNode: clearSelectedNode,
		currentConfig: currentConfig,
		currentDefinition: currentDefinition,
		currentNode: currentNode,
		isV3Draft: isV3Draft,
		loadAll: loadAll,
		markValidated: markValidated,
		patchEdge: patchEdge,
		patchNode: patchNode,
		patchWrite: patchWrite,
		primitiveItems: primitiveItems,
		primitiveMeta: primitiveMeta,
		removeEdge: removeEdge,
		removeNode: removeNode,
		removeWrite: removeWrite,
		selectedStepId: selectedStepId,
		setSelectedStep: setSelectedStep,
	};
})();
