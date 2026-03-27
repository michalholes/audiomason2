(function () {
	"use strict";

	/** @typedef {AM2FlowStepFieldSpec & { editor?: string }} AM2FlowStepFieldModelSpec */

	/** @type {Window} */
	const W = window;

	/** @template T
	 * @param {T} value
	 * @returns {T}
	 */
	function deepClone(value) {
		return JSON.parse(JSON.stringify(value));
	}

	/** @param {AM2JsonObject} step
	 * @returns {AM2JsonObject}
	 */
	function ensureStepOp(step) {
		if (!step.op || typeof step.op !== "object" || Array.isArray(step.op)) {
			step.op = {};
		}
		return /** @type {AM2JsonObject} */ (step.op);
	}

	/** @param {AM2JsonObject} step
	 * @returns {AM2JsonObject}
	 */
	function ensureStepInputs(step) {
		const op = ensureStepOp(step);
		if (
			!op.inputs ||
			typeof op.inputs !== "object" ||
			Array.isArray(op.inputs)
		) {
			op.inputs = {};
		}
		return /** @type {AM2JsonObject} */ (op.inputs);
	}

	/** @param {AM2JsonObject} step
	 * @returns {AM2DSLEditorWriteRecord[]}
	 */
	function ensureStepWrites(step) {
		const op = ensureStepOp(step);
		if (!Array.isArray(op.writes)) {
			op.writes = [];
		}
		return /** @type {AM2DSLEditorWriteRecord[]} */ (op.writes);
	}

	/**
	 * @param {AM2FlowStepModalStateShape} state
	 * @param {AM2FlowStepFieldModelSpec} spec
	 * @returns {AM2JsonValue}
	 */
	function readFieldValue(state, spec) {
		if (
			Object.prototype.hasOwnProperty.call(state.fieldBuffers, spec.fieldId)
		) {
			return state.fieldBuffers[spec.fieldId];
		}
		return spec.getValue(state.workingStep || {});
	}

	/**
	 * @param {AM2FlowStepModalStateShape} state
	 * @param {string} fieldId
	 * @returns {boolean}
	 */
	function isFieldDirty(state, fieldId) {
		return Object.prototype.hasOwnProperty.call(state.fieldBuffers, fieldId);
	}

	/**
	 * @param {AM2FlowStepModalFormApi} formApi
	 * @param {AM2FlowStepModalStateShape} state
	 * @param {string} fieldId
	 * @returns {AM2FlowStepFieldModelSpec | null}
	 */
	function findFieldSpec(formApi, state, fieldId) {
		const specs = /** @type {AM2FlowStepFieldModelSpec[]} */ (
			formApi.buildFieldSpecs(state.workingStep || {})
		);
		return (
			specs.find(function (item) {
				return item.fieldId === fieldId;
			}) || null
		);
	}

	/**
	 * @param {AM2FlowStepModalStateShape} state
	 * @param {AM2FlowStepFieldModelSpec | null} spec
	 * @param {string} rawValue
	 */
	function applyFieldValue(state, spec, rawValue) {
		if (!state.workingStep || !spec) return;
		const op = ensureStepOp(state.workingStep);
		const inputs = ensureStepInputs(state.workingStep);
		ensureStepWrites(state.workingStep);
		if (spec.fieldId === "core:step_id") {
			state.workingStep.step_id = String(rawValue || "");
			return;
		}
		if (spec.fieldId === "core:primitive_id") {
			op.primitive_id = String(rawValue || "");
			return;
		}
		if (spec.fieldId === "core:primitive_version") {
			op.primitive_version = Number(rawValue || 0);
			return;
		}
		if (spec.fieldId === "writes") {
			op.writes = /** @type {AM2DSLEditorWriteRecord[]} */ (
				JSON.parse(rawValue || "[]")
			);
			return;
		}
		if (spec.fieldId.indexOf("input:") !== 0) return;
		const key = spec.fieldId.slice(6);
		if (spec.editor === "json") {
			inputs[key] = /** @type {AM2JsonValue} */ (
				JSON.parse(rawValue || "null")
			);
			return;
		}
		if (spec.editor === "number") {
			inputs[key] = Number(rawValue || 0);
			return;
		}
		if (spec.editor === "boolean") {
			inputs[key] = rawValue === "true";
			return;
		}
		inputs[key] = String(rawValue || "");
	}

	/** @param {AM2FlowStepModalStateShape} state */
	function rebuildJsonBuffer(state) {
		state.jsonBuffer = JSON.stringify(state.workingStep || {}, null, 2);
		state.jsonDirty = false;
	}

	/**
	 * @param {AM2FlowStepModalStateShape} state
	 * @param {AM2FlowStepModalFormApi} formApi
	 * @param {string} fieldId
	 * @param {(message: string) => void} setError
	 * @returns {boolean}
	 */
	function flushField(state, formApi, fieldId, setError) {
		const spec = findFieldSpec(formApi, state, fieldId);
		if (!spec) return true;
		try {
			applyFieldValue(state, spec, state.fieldBuffers[fieldId] || "");
			delete state.fieldBuffers[fieldId];
			rebuildJsonBuffer(state);
			return true;
		} catch (err) {
			setError(String(err || "Field apply failed."));
			return false;
		}
	}

	/**
	 * @param {AM2FlowStepModalStateShape} state
	 * @param {AM2FlowStepModalFormApi} formApi
	 * @param {(message: string) => void} setError
	 * @returns {boolean}
	 */
	function flushAllFieldBuffers(state, formApi, setError) {
		const fieldIds = Object.keys(state.fieldBuffers);
		for (let i = 0; i < fieldIds.length; i += 1) {
			if (!flushField(state, formApi, fieldIds[i], setError)) return false;
		}
		return true;
	}

	/**
	 * @param {AM2FlowStepModalStateShape} state
	 * @param {(message: string) => void} setError
	 * @returns {boolean}
	 */
	function flushJSONBuffer(state, setError) {
		if (state.jsonDirty !== true) return true;
		try {
			state.workingStep = /** @type {AM2JsonObject} */ (
				JSON.parse(state.jsonBuffer || "{}")
			);
			state.fieldBuffers = {};
			state.jsonDirty = false;
			return true;
		} catch (err) {
			setError(String(err || "JSON parse failed."));
			return false;
		}
	}

	/**
	 * @param {AM2FlowStepModalStateShape} state
	 * @param {AM2FlowStepModalFormApi} formApi
	 * @param {(message: string) => void} setError
	 * @param {string} view
	 * @returns {boolean}
	 */
	function flushPendingEdits(state, formApi, setError, view) {
		if (view === "json") {
			return flushJSONBuffer(state, setError);
		}
		return flushAllFieldBuffers(state, formApi, setError);
	}

	/** @param {AM2DSLEditorGraphOpsApi} graphOps
	 * @returns {AM2JsonObject}
	 */
	function currentDefinitionClone(graphOps) {
		return deepClone(
			graphOps.currentDefinition ? graphOps.currentDefinition() : {},
		);
	}

	/**
	 * @param {AM2JsonObject} definition
	 * @param {AM2FlowStepModalStateShape} state
	 * @param {AM2JsonObject | null} nextStep
	 * @returns {string}
	 */
	function replaceSelectedNode(definition, state, nextStep) {
		const libraryId = String(state.selectedLibraryId || "");
		const originalStepId = String(state.originalStepId || "");
		const libraries =
			definition.libraries &&
			typeof definition.libraries === "object" &&
			!Array.isArray(definition.libraries)
				? /** @type {Record<string, AM2JsonObject>} */ (definition.libraries)
				: null;
		const graph =
			libraryId && libraries && libraries[libraryId]
				? libraries[libraryId]
				: definition;
		const nodes = Array.isArray(graph.nodes) ? graph.nodes : null;
		if (!nodes) throw new Error("Graph nodes are unavailable.");
		const index = nodes.findIndex(function (item) {
			return !!(
				item &&
				typeof item === "object" &&
				!Array.isArray(item) &&
				String(item.step_id || "") === originalStepId
			);
		});
		if (index < 0) throw new Error("Selected step is no longer present.");
		nodes[index] = deepClone(nextStep || {});
		const nextStepId = String((nextStep && nextStep.step_id) || "");
		if (originalStepId === nextStepId) return nextStepId;
		if (graph.entry_step_id === originalStepId)
			graph.entry_step_id = nextStepId;
		if (Array.isArray(graph.edges)) {
			graph.edges.forEach(function (edge) {
				if (!edge || typeof edge !== "object" || Array.isArray(edge)) return;
				if (edge.from === originalStepId) edge.from = nextStepId;
				if (edge.to === originalStepId) edge.to = nextStepId;
				if (edge.from_step_id === originalStepId)
					edge.from_step_id = nextStepId;
				if (edge.to_step_id === originalStepId) edge.to_step_id = nextStepId;
			});
		}
		return nextStepId;
	}

	/**
	 * @param {AM2FlowStepModalStateShape} state
	 * @param {AM2DSLEditorGraphOpsApi} graphOps
	 * @returns {{ definition: AM2JsonObject, nextStepId: string }}
	 */
	function buildCandidateDefinition(state, graphOps) {
		const definition = currentDefinitionClone(graphOps);
		return {
			definition: definition,
			nextStepId: replaceSelectedNode(definition, state, state.workingStep),
		};
	}

	/**
	 * @param {AM2FlowStepModalStateShape} state
	 * @param {AM2DSLEditorGraphOpsApi} graphOps
	 * @param {string} stepId
	 */
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

	/** @param {AM2FlowStepModalStateShape} state
	 * @returns {number}
	 */
	function pendingBufferCount(state) {
		return Object.keys(state.fieldBuffers).length + (state.jsonDirty ? 1 : 0);
	}

	/** @param {AM2FlowStepModalStateShape} state
	 * @returns {boolean}
	 */
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
