(function () {
  "use strict";

  function isNil(x) {
    return x === null || x === undefined;
  }

  function FlowEditorState() {
    this.wizardDraft = null;
    this.configDraft = null;
    this.selectedStepId = null;
    this.draftDirty = false;
    this.validationState = { lastOk: false, envelope: null };

    this._listeners = {
      wizard_changed: [],
      config_changed: [],
      selection_changed: [],
      validation_changed: [],
    };
  }

  FlowEditorState.prototype.on = function on(eventName, fn) {
    const list = this._listeners && this._listeners[eventName];
    if (!list || typeof fn !== "function") return function () {};
    list.push(fn);
    return () => {
      const i = list.indexOf(fn);
      if (i >= 0) list.splice(i, 1);
    };
  };

  FlowEditorState.prototype.emit = function emit(eventName, payload) {
    const list = (this._listeners && this._listeners[eventName]) || [];
    list.slice(0).forEach(function (fn) {
      try {
        fn(payload || {});
      } catch (e) {
      }
    });
  };

  FlowEditorState.prototype.loadAll = function loadAll(payload) {
    const wiz = payload && payload.wizardDefinition;
    const cfg = payload && payload.flowConfig;
    this.wizardDraft = wiz && typeof wiz === "object" ? JSON.parse(JSON.stringify(wiz)) : {};
    if (!this.wizardDraft._am2_ui || typeof this.wizardDraft._am2_ui !== "object") {
      this.wizardDraft._am2_ui = { showOptional: true, rightTab: "details" };
    }
    this.configDraft = cfg && typeof cfg === "object" ? JSON.parse(JSON.stringify(cfg)) : {};
    this.selectedStepId = null;
    this.draftDirty = false;
    this.validationState = { lastOk: false, envelope: null };

    this.emit("wizard_changed", { reason: "load_all" });
    this.emit("config_changed", { reason: "load_all" });
    this.emit("selection_changed", { reason: "load_all" });
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

  FlowEditorState.prototype.setValidationState = function setValidationState(nextState) {
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

  // Backward-compat adapters for older modules.
  FlowEditorState.prototype.registerWizardRender = function registerWizardRender(fn) {
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

  FlowEditorState.prototype.registerConfigRender = function registerConfigRender(fn) {
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

  FlowEditorState.prototype.setSelectedStep = function setSelectedStep(stepIdOrNull) {
    this.selectedStepId = stepIdOrNull || null;
    this.emit("selection_changed", { reason: "selection" });
  };

  FlowEditorState.prototype.mutateWizard = function mutateWizard(mutatorFn) {
    if (!this.wizardDraft) this.wizardDraft = {};
    mutatorFn && mutatorFn(this.wizardDraft);
    this.draftDirty = true;
    this.validationState = { lastOk: false, envelope: null };
    this.emit("wizard_changed", { reason: "mutate_wizard" });
    this.emit("validation_changed", { reason: "dirty" });
  };

  FlowEditorState.prototype.mutateConfig = function mutateConfig(mutatorFn) {
    if (!this.configDraft) this.configDraft = {};
    mutatorFn && mutatorFn(this.configDraft);
    this.draftDirty = true;
    this.validationState = { lastOk: false, envelope: null };
    this.emit("config_changed", { reason: "mutate_config" });
    this.emit("validation_changed", { reason: "dirty" });
  };

  FlowEditorState.prototype.markValidated = function markValidated(payload) {
    const w = payload && payload.canonicalWizardDefinition;
    const c = payload && payload.canonicalFlowConfig;
    if (!isNil(w)) this.wizardDraft = JSON.parse(JSON.stringify(w));
    if (!isNil(c)) this.configDraft = JSON.parse(JSON.stringify(c));
    this.validationState = {
      lastOk: true,
      envelope: JSON.parse(
        JSON.stringify((payload && payload.validationEnvelope) || null)
      ),
    };
    this.draftDirty = false;

    this.emit("wizard_changed", { reason: "validated" });
    this.emit("config_changed", { reason: "validated" });
    this.emit("validation_changed", { reason: "validated" });
  };

  window.FlowEditorState = FlowEditorState;
})();