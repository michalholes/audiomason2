(function () {
  "use strict";

  function deepClone(x) {
    return x === undefined ? undefined : JSON.parse(JSON.stringify(x));
  }

  function FlowEditorState() {
    this.wizardDraft = null;
    this.configDraft = null;
    this.selectedStepId = null;
    this.draftDirty = false;
    this.validationState = {
      lastOk: false,
      envelope: null,
    };
  }

  FlowEditorState.prototype.loadAll = function loadAll(payload) {
    const wiz = payload && payload.wizardDefinition;
    const cfg = payload && payload.flowConfig;
    this.wizardDraft = deepClone(wiz);
    this.configDraft = deepClone(cfg);
    this.selectedStepId = null;
    this.draftDirty = false;
    this.validationState = { lastOk: false, envelope: null };
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

  FlowEditorState.prototype.setSelectedStep = function setSelectedStep(stepIdOrNull) {
    this.selectedStepId = stepIdOrNull || null;
  };

  FlowEditorState.prototype.mutateWizard = function mutateWizard(mutatorFn) {
    const next = deepClone(this.wizardDraft);
    mutatorFn && mutatorFn(next);
    this.wizardDraft = next;
    this.draftDirty = true;
    this.validationState.lastOk = false;
  };

  FlowEditorState.prototype.mutateConfig = function mutateConfig(mutatorFn) {
    const next = deepClone(this.configDraft);
    mutatorFn && mutatorFn(next);
    this.configDraft = next;
    this.draftDirty = true;
    this.validationState.lastOk = false;
  };

  FlowEditorState.prototype.markValidated = function markValidated(payload) {
    this.wizardDraft = deepClone(payload && payload.canonicalWizardDefinition);
    this.configDraft = deepClone(payload && payload.canonicalFlowConfig);
    this.validationState = {
      lastOk: true,
      envelope: deepClone(payload && payload.validationEnvelope),
    };
    this.draftDirty = false;
  };

  window.FlowEditorState = FlowEditorState;
})();
