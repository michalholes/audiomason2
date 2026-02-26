(function () {
  "use strict";

  function deepClone(x) {
    return x === undefined ? undefined : JSON.parse(JSON.stringify(x));
  }

  function isNil(x) {
    return x === null || x === undefined;
  }

  function FlowEditorState() {
    this.wizardDraft = null;
    this.configDraft = null;
    this.selectedStepId = null;
    this.draftDirty = false;
    this.validationState = { lastOk: false, envelope: null };

    this._wizardRenders = [];
    this._configRenders = [];
  }

  FlowEditorState.prototype.loadAll = function loadAll(payload) {
    const wiz = payload && payload.wizardDefinition;
    const cfg = payload && payload.flowConfig;
    this.wizardDraft = deepClone(wiz) || {};
    if (!this.wizardDraft._am2_ui || typeof this.wizardDraft._am2_ui !== "object") {
      this.wizardDraft._am2_ui = { showOptional: true, rightTab: "details" };
    }
    this.configDraft = deepClone(cfg) || {};
    this.selectedStepId = null;
    this.draftDirty = false;
    this.validationState = { lastOk: false, envelope: null };
    this._requestWizardRender();
    this._requestConfigRender();
  };

  FlowEditorState.prototype.getSnapshot = function getSnapshot() {
    return {
      wizardDraft: deepClone(this.wizardDraft),
      configDraft: deepClone(this.configDraft),
      selectedStepId: this.selectedStepId,
      draftDirty: this.draftDirty,
      validationState: deepClone(this.validationState),
    };
  };

  FlowEditorState.prototype.setValidationState = function setValidationState(nextState) {
    if (nextState && typeof nextState === "object" && "lastOk" in nextState) {
      this.validationState = deepClone(nextState);
      return;
    }
    this.validationState = { lastOk: true, envelope: deepClone(nextState) };
  };

  FlowEditorState.prototype.registerWizardRender = function registerWizardRender(fn) {
    if (typeof fn !== "function") return;
    this._wizardRenders.push(fn);
    fn();
  };

  FlowEditorState.prototype.registerConfigRender = function registerConfigRender(fn) {
    if (typeof fn !== "function") return;
    this._configRenders.push(fn);
    fn();
  };

  FlowEditorState.prototype._requestWizardRender = function _requestWizardRender() {
    (this._wizardRenders || []).forEach(function (fn) {
      try {
        fn();
      } catch (e) {
      }
    });
  };

  FlowEditorState.prototype._requestConfigRender = function _requestConfigRender() {
    (this._configRenders || []).forEach(function (fn) {
      try {
        fn();
      } catch (e) {
      }
    });
  };

  FlowEditorState.prototype.setSelectedStep = function setSelectedStep(stepIdOrNull) {
    this.selectedStepId = stepIdOrNull || null;
    this._requestWizardRender();
    this._requestConfigRender();
  };

  FlowEditorState.prototype.mutateWizard = function mutateWizard(mutatorFn) {
    if (!this.wizardDraft) this.wizardDraft = {};
    mutatorFn && mutatorFn(this.wizardDraft);
    this.draftDirty = true;
    this.validationState = { lastOk: false, envelope: null };
    this._requestWizardRender();
  };

  FlowEditorState.prototype.mutateConfig = function mutateConfig(mutatorFn) {
    if (!this.configDraft) this.configDraft = {};
    mutatorFn && mutatorFn(this.configDraft);
    this.draftDirty = true;
    this.validationState = { lastOk: false, envelope: null };
    this._requestConfigRender();
  };

  FlowEditorState.prototype.markValidated = function markValidated(payload) {
    const w = payload && payload.canonicalWizardDefinition;
    const c = payload && payload.canonicalFlowConfig;
    if (!isNil(w)) this.wizardDraft = deepClone(w);
    if (!isNil(c)) this.configDraft = deepClone(c);
    this.validationState = {
      lastOk: true,
      envelope: deepClone(payload && payload.validationEnvelope),
    };
    this.draftDirty = false;
    this._requestWizardRender();
    this._requestConfigRender();
  };

  window.FlowEditorState = FlowEditorState;
})();