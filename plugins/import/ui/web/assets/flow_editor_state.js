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

    this._wizardBridge = null;
    this._configBridge = null;
  }

  FlowEditorState.prototype.loadAll = function loadAll(payload) {
    const wiz = payload && payload.wizardDefinition;
    const cfg = payload && payload.flowConfig;
    this.wizardDraft = deepClone(wiz);
    this.configDraft = deepClone(cfg);
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

  FlowEditorState.prototype.bindWizardEditorBridge = function bindWizardEditorBridge(bridge) {
    this._wizardBridge = bridge || null;
    this._requestWizardRender();
  };

  FlowEditorState.prototype.bindConfigEditorBridge = function bindConfigEditorBridge(bridge) {
    this._configBridge = bridge || null;
    this._requestConfigRender();
  };

  FlowEditorState.prototype._requestWizardRender = function _requestWizardRender() {
    const b = this._wizardBridge;
    if (b && b.renderRequested) b.renderRequested();
  };

  FlowEditorState.prototype._requestConfigRender = function _requestConfigRender() {
    const b = this._configBridge;
    if (b && b.renderRequested) b.renderRequested();
  };

  FlowEditorState.prototype.setSelectedStep = function setSelectedStep(stepIdOrNull) {
    this.selectedStepId = stepIdOrNull || null;
    this._requestWizardRender();
    this._requestConfigRender();
  };

  FlowEditorState.prototype.mutateWizard = function mutateWizard(mutatorFn) {
    const next = deepClone(this.wizardDraft);
    mutatorFn && mutatorFn(next);
    this.wizardDraft = next;
    this.draftDirty = true;
    this.validationState = { lastOk: false, envelope: null };
    this._requestWizardRender();
  };

  FlowEditorState.prototype.mutateConfig = function mutateConfig(mutatorFn) {
    const next = deepClone(this.configDraft);
    mutatorFn && mutatorFn(next);
    this.configDraft = next;
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