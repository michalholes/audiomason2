(function () {
	"use strict";

	const W = /** @type {any} */ (window);

	function deepClone(value) {
		return JSON.parse(JSON.stringify(value));
	}

	function readFieldValue(state, spec) {
		if (
			Object.prototype.hasOwnProperty.call(state.fieldBuffers, spec.fieldId)
		) {
			return state.fieldBuffers[spec.fieldId];
		}
		return spec.getValue(state.workingStep);
	}

	function isFieldDirty(state, fieldId) {
		return Object.prototype.hasOwnProperty.call(state.fieldBuffers, fieldId);
	}

	function findFieldSpec(formApi, state, fieldId) {
		const specs = formApi.buildFieldSpecs(state.workingStep || {});
		return (
			specs.find(function (item) {
				return item.fieldId === fieldId;
			}) || null
		);
	}

	function applyFieldValue(state, spec, rawValue) {
		if (!state.workingStep || !spec) return;
		if (!state.workingStep.op || typeof state.workingStep.op !== "object") {
			state.workingStep.op = {};
		}
		if (
			!state.workingStep.op.inputs ||
			typeof state.workingStep.op.inputs !== "object"
		) {
			state.workingStep.op.inputs = {};
		}
		if (!Array.isArray(state.workingStep.op.writes)) {
			state.workingStep.op.writes = [];
		}
		if (spec.fieldId === "core:step_id") {
			state.workingStep.step_id = String(rawValue || "");
			return;
		}
		if (spec.fieldId === "core:primitive_id") {
			state.workingStep.op.primitive_id = String(rawValue || "");
			return;
		}
		if (spec.fieldId === "core:primitive_version") {
			state.workingStep.op.primitive_version = Number(rawValue || 0);
			return;
		}
		if (spec.fieldId === "writes") {
			state.workingStep.op.writes = JSON.parse(rawValue || "[]");
			return;
		}
		if (spec.fieldId.indexOf("input:") !== 0) {
			return;
		}
		const key = spec.fieldId.slice(6);
		if (spec.editor === "json") {
			state.workingStep.op.inputs[key] = JSON.parse(rawValue || "null");
			return;
		}
		if (spec.editor === "number") {
			state.workingStep.op.inputs[key] = Number(rawValue || 0);
			return;
		}
		if (spec.editor === "boolean") {
			state.workingStep.op.inputs[key] = rawValue === "true";
			return;
		}
		state.workingStep.op.inputs[key] = String(rawValue || "");
	}

	function rebuildJsonBuffer(state) {
		state.jsonBuffer = JSON.stringify(state.workingStep || {}, null, 2);
		state.jsonDirty = false;
	}

	function flushField(state, formApi, fieldId, setError) {
		const spec = findFieldSpec(formApi, state, fieldId);
		if (!spec) return true;
		try {
			applyFieldValue(state, spec, state.fieldBuffers[fieldId]);
			delete state.fieldBuffers[fieldId];
			rebuildJsonBuffer(state);
			return true;
		} catch (err) {
			setError(String(err || "Field apply failed."));
			return false;
		}
	}

	function flushAllFieldBuffers(state, formApi, setError) {
		const fieldIds = Object.keys(state.fieldBuffers);
		for (let i = 0; i < fieldIds.length; i += 1) {
			if (!flushField(state, formApi, fieldIds[i], setError)) {
				return false;
			}
		}
		return true;
	}

	function flushJSONBuffer(state, setError) {
		if (state.jsonDirty !== true) return true;
		try {
			state.workingStep = JSON.parse(state.jsonBuffer || "{}");
			state.fieldBuffers = {};
			state.jsonDirty = false;
			return true;
		} catch (err) {
			setError(String(err || "JSON parse failed."));
			return false;
		}
	}

	function flushPendingEdits(state, formApi, setError, view) {
		if (view === "json") {
			return flushJSONBuffer(state, setError);
		}
		return flushAllFieldBuffers(state, formApi, setError);
	}

	function currentDefinitionClone(graphOps) {
		return deepClone(
			graphOps.currentDefinition ? graphOps.currentDefinition() : {},
		);
	}

	function replaceSelectedNode(definition, state, nextStep) {
		const libraryId = String(state.selectedLibraryId || "");
		const originalStepId = String(state.originalStepId || "");
		const graph =
			libraryId &&
			definition &&
			definition.libraries &&
			definition.libraries[libraryId]
				? definition.libraries[libraryId]
				: definition;
		if (!graph || !Array.isArray(graph.nodes)) {
			throw new Error("Graph nodes are unavailable.");
		}
		const index = graph.nodes.findIndex(function (item) {
			return String((item && item.step_id) || "") === originalStepId;
		});
		if (index < 0) {
			throw new Error("Selected step is no longer present.");
		}
		graph.nodes[index] = deepClone(nextStep || {});
		const nextStepId = String((nextStep && nextStep.step_id) || "");
		if (originalStepId === nextStepId) {
			return nextStepId;
		}
		if (graph.entry_step_id === originalStepId) {
			graph.entry_step_id = nextStepId;
		}
		if (Array.isArray(graph.edges)) {
			graph.edges.forEach(function (edge) {
				if (edge.from === originalStepId) edge.from = nextStepId;
				if (edge.to === originalStepId) edge.to = nextStepId;
				if (edge.from_step_id === originalStepId)
					edge.from_step_id = nextStepId;
				if (edge.to_step_id === originalStepId) edge.to_step_id = nextStepId;
			});
		}
		return nextStepId;
	}

	function buildCandidateDefinition(state, graphOps) {
		const definition = currentDefinitionClone(graphOps);
		const nextStepId = replaceSelectedNode(
			definition,
			state,
			state.workingStep,
		);
		return { definition: definition, nextStepId: nextStepId };
	}

	function syncFromSavedStep(state, graphOps, stepId) {
		const current = graphOps.currentNode ? graphOps.currentNode() : null;
		const next =
			current && String(current.step_id || "") === String(stepId || "")
				? current
				: null;
		state.originalStepId = String(stepId || "");
		state.baselineStep = deepClone(next || state.workingStep || {});
		state.workingStep = deepClone(next || state.workingStep || {});
		state.fieldBuffers = {};
		rebuildJsonBuffer(state);
	}

	function pendingBufferCount(state) {
		const count = Object.keys(state.fieldBuffers).length;
		return count + (state.jsonDirty ? 1 : 0);
	}

	function workingStateDirty(state) {
		return (
			JSON.stringify(state.workingStep || {}) !==
			JSON.stringify(state.baselineStep || {})
		);
	}

	W.AM2FlowStepModalModel = {
		buildCandidateDefinition: buildCandidateDefinition,
		flushField: flushField,
		flushPendingEdits: flushPendingEdits,
		pendingBufferCount: pendingBufferCount,
		readFieldValue: readFieldValue,
		rebuildJsonBuffer: rebuildJsonBuffer,
		syncFromSavedStep: syncFromSavedStep,
		workingStateDirty: workingStateDirty,
		isFieldDirty: isFieldDirty,
	};
})();
