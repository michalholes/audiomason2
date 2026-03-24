(function () {
	"use strict";

	/** @typedef {(payload: AM2FlowListenerPayload) => void} AM2FlowListenerFn */
	/**
	 * @typedef {{
	 *   wizard_changed: AM2FlowListenerFn[],
	 *   config_changed: AM2FlowListenerFn[],
	 *   selection_changed: AM2FlowListenerFn[],
	 *   validation_changed: AM2FlowListenerFn[]
	 * }} AM2FlowListenerMap
	 */

	/** @param {unknown} x */
	function isNil(x) {
		return x === null || x === undefined;
	}

	/** @constructor */
	function FlowEditorState() {
		/** @type {AM2JsonObject | null} */
		this.wizardDraft = null;
		/** @type {AM2JsonObject | null} */
		this.configDraft = null;
		/** @type {string | null} */
		this.selectedStepId = null;
		/** @type {boolean} */
		this.draftDirty = false;
		/** @type {AM2FlowValidationState} */
		this.validationState = { lastOk: false, envelope: null };

		/** @type {AM2FlowListenerMap} */
		this._listeners = {
			wizard_changed: [],
			config_changed: [],
			selection_changed: [],
			validation_changed: [],
		};
	}

	/** @param {AM2FlowListenerEventName} eventName @param {AM2FlowListenerFn} fn */
	FlowEditorState.prototype.on = function on(eventName, fn) {
		const list = this._listeners[eventName];
		if (typeof fn !== "function") return function () {};
		list.push(fn);
		return () => {
			const i = list.indexOf(fn);
			if (i >= 0) list.splice(i, 1);
		};
	};

	/** @param {AM2FlowListenerEventName} eventName @param {AM2FlowListenerPayload=} payload */
	FlowEditorState.prototype.emit = function emit(eventName, payload) {
		const list = this._listeners[eventName] || [];
		list.slice(0).forEach(function (fn) {
			try {
				fn(payload || {});
			} catch (e) {}
		});
	};

	/** @param {string | null} stepIdOrNull */
	FlowEditorState.prototype._dispatchSelectionEvent =
		function _dispatchSelectionEvent(stepIdOrNull) {
			try {
				window.dispatchEvent(
					new CustomEvent("am2:wd:selected", {
						detail: { step_id: stepIdOrNull || null },
					}),
				);
			} catch (e) {}
		};

	/** @param {AM2FlowLoadAllPayload} payload @param {AM2FlowLoadAllOptions=} opts */
	FlowEditorState.prototype.loadAll = function loadAll(payload, opts) {
		const wiz = payload && payload.wizardDefinition;
		const cfg = payload && payload.flowConfig;
		this.wizardDraft =
			wiz && typeof wiz === "object" ? JSON.parse(JSON.stringify(wiz)) : {};
		const wizardDraft = /** @type {AM2JsonObject} */ (this.wizardDraft || {});
		if (!wizardDraft._am2_ui || typeof wizardDraft._am2_ui !== "object") {
			wizardDraft._am2_ui = { showOptional: true, rightTab: "details" };
		}
		this.wizardDraft = wizardDraft;
		this.configDraft =
			cfg && typeof cfg === "object" ? JSON.parse(JSON.stringify(cfg)) : {};
		this.selectedStepId = null;
		this.draftDirty = false;
		const preserveValidation = !!(opts && opts.preserveValidation === true);
		if (!preserveValidation) {
			this.validationState = { lastOk: false, envelope: null };
		}

		this.emit("wizard_changed", { reason: "load_all" });
		this.emit("config_changed", { reason: "load_all" });
		this.emit("selection_changed", { reason: "load_all" });
		this._dispatchSelectionEvent(null);
		this.emit("validation_changed", { reason: "load_all" });
	};

	FlowEditorState.prototype.getSnapshot = function getSnapshot() {
		return {
			wizardDraft: this.wizardDraft,
			configDraft: this.configDraft,
			selectedStepId: this.selectedStepId,
			draftDirty: this.draftDirty,
			validationState: this.validationState,
		};
	};

	/** @param {AM2FlowValidationState | AM2JsonValue} nextState */
	FlowEditorState.prototype.setValidationState = function setValidationState(
		nextState,
	) {
		if (nextState && typeof nextState === "object" && "lastOk" in nextState) {
			this.validationState = JSON.parse(JSON.stringify(nextState));
			this.emit("validation_changed", { reason: "set_validation_state" });
			return;
		}
		this.validationState = {
			lastOk: true,
			envelope: JSON.parse(JSON.stringify(nextState || null)),
		};
		this.emit("validation_changed", { reason: "set_validation_state" });
	};

	/** @param {() => void} fn */
	FlowEditorState.prototype.registerWizardRender =
		function registerWizardRender(fn) {
			if (typeof fn !== "function") return;
			fn();
			this.on("wizard_changed", function () {
				fn();
			});
			this.on("selection_changed", function () {
				fn();
			});
			this.on("validation_changed", function () {
				fn();
			});
		};

	/** @param {() => void} fn */
	FlowEditorState.prototype.registerConfigRender =
		function registerConfigRender(fn) {
			if (typeof fn !== "function") return;
			fn();
			this.on("config_changed", function () {
				fn();
			});
			this.on("selection_changed", function () {
				fn();
			});
			this.on("validation_changed", function () {
				fn();
			});
		};

	/** @param {string | null} stepIdOrNull */
	FlowEditorState.prototype.setSelectedStep = function setSelectedStep(
		stepIdOrNull,
	) {
		this.selectedStepId = stepIdOrNull || null;
		this.emit("selection_changed", { reason: "selection" });
		this._dispatchSelectionEvent(this.selectedStepId);
	};

	/** @param {(draft: AM2JsonObject) => void} mutatorFn @param {AM2FlowMutationOptions=} opts */
	FlowEditorState.prototype.mutateWizard = function mutateWizard(
		mutatorFn,
		opts,
	) {
		if (!this.wizardDraft) this.wizardDraft = {};
		if (mutatorFn) mutatorFn(this.wizardDraft);

		const o = opts && typeof opts === "object" ? opts : {};
		const markDirty = o.markDirty !== false;
		const resetValidation = o.resetValidation !== false;
		const reason = o.reason ? String(o.reason) : "mutate_wizard";

		if (markDirty) this.draftDirty = true;
		if (resetValidation)
			this.validationState = { lastOk: false, envelope: null };

		this.emit("wizard_changed", { reason: reason });
		if (markDirty || resetValidation) {
			this.emit("validation_changed", {
				reason: markDirty ? "dirty" : "validation_state",
			});
		}
	};

	/** @param {(draft: AM2JsonObject) => void} mutatorFn @param {AM2FlowMutationOptions=} opts */
	FlowEditorState.prototype.mutateConfig = function mutateConfig(
		mutatorFn,
		opts,
	) {
		if (!this.configDraft) this.configDraft = {};
		if (mutatorFn) mutatorFn(this.configDraft);

		const o = opts && typeof opts === "object" ? opts : {};
		const markDirty = o.markDirty !== false;
		const resetValidation = o.resetValidation !== false;
		const reason = o.reason ? String(o.reason) : "mutate_config";

		if (markDirty) this.draftDirty = true;
		if (resetValidation)
			this.validationState = { lastOk: false, envelope: null };

		this.emit("config_changed", { reason: reason });
		if (markDirty || resetValidation) {
			this.emit("validation_changed", {
				reason: markDirty ? "dirty" : "validation_state",
			});
		}
	};

	/** @param {AM2FlowMarkValidatedPayload} payload */
	FlowEditorState.prototype.markValidated = function markValidated(payload) {
		const w = payload && payload.canonicalWizardDefinition;
		const c = payload && payload.canonicalFlowConfig;
		if (!isNil(w)) this.wizardDraft = JSON.parse(JSON.stringify(w));
		if (!isNil(c)) this.configDraft = JSON.parse(JSON.stringify(c));
		this.validationState = {
			lastOk: true,
			envelope: JSON.parse(
				JSON.stringify((payload && payload.validationEnvelope) || null),
			),
		};
		this.draftDirty = false;

		this.emit("wizard_changed", { reason: "validated" });
		this.emit("config_changed", { reason: "validated" });
		this.emit("validation_changed", { reason: "validated" });
		this._dispatchSelectionEvent(this.selectedStepId);
	};

	FlowEditorState.prototype.clearDirty = function clearDirty() {
		this.draftDirty = false;
	};

	window.FlowEditorState = FlowEditorState;
	if (!window.AM2FlowEditorState) {
		window.AM2FlowEditorState = new FlowEditorState();
	}
})();
