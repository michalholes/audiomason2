(function () {
  "use strict";

  const H = window.AM2EditorHTTP;
  if (!H) return;

  function $(id) {
    return document.getElementById(id);
  }

  const ui = {
    ta: $("cfgJson"),
    err: $("cfgError"),
    history: $("cfgHistory"),
    reload: $("cfgReload"),
    validate: $("cfgValidate"),
    save: $("cfgSave"),
    reset: $("cfgReset"),

    stepPanel: $("flowStepPanel"),
    stepHeader: $("flowStepHeader"),
    stepBehavior: $("flowStepBehavior"),
    stepInput: $("flowStepInput"),
    stepOutput: $("flowStepOutput"),
    stepSideEffects: $("flowStepSideEffects"),
    stepForm: $("flowStepForm"),
    stepApply: $("flowStepApply"),
    stepError: $("flowStepError"),
    clearStep: $("flowClearStep"),
  };

  if (!ui.ta) return;

  const unifiedMode = !!ui.stepPanel;

  function deepClone(x) {
    return x === undefined ? undefined : JSON.parse(JSON.stringify(x));
  }

  function snapshot() {
    const FE = window.AM2FlowEditorState;
    return FE && FE.getSnapshot ? FE.getSnapshot() : null;
  }

  const stepCache = {};

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function historyRow(item) {
    const row = document.createElement("div");
    row.className = "historyItem";
    const meta = document.createElement("div");
    meta.className = "historyMeta";
    const id = document.createElement("div");
    id.textContent = String(item.id || "");
    const ts = document.createElement("div");
    ts.textContent = String(item.timestamp || "");
    meta.appendChild(id);
    meta.appendChild(ts);
    const btn = document.createElement("button");
    btn.className = "btn";
    btn.textContent = "Rollback";
    btn.addEventListener("click", async () => {
      await rollback(String(item.id || ""));
    });
    row.appendChild(meta);
    row.appendChild(btn);
    return row;
  }

  async function loadHistory() {
    const out = await H.requestJSON("/import/ui/config/history");
    if (!out.ok) {
      H.renderError(ui.err, out.data);
      return;
    }
    clear(ui.history);
    const items = out.data && out.data.items ? out.data.items : [];
    (Array.isArray(items) ? items : []).forEach((it) => {
      ui.history.appendChild(historyRow(it || {}));
    });
  }

  async function reload() {
    H.renderError(ui.err, null);
    const out = await H.requestJSON("/import/ui/config");
    if (!out.ok) {
      H.renderError(ui.err, out.data);
      return false;
    }
    const cfg = out.data && out.data.config ? out.data.config : {};
    ui.ta.value = H.pretty(cfg);
    const FE = window.AM2FlowEditorState;
    if (FE && FE.loadAll && FE.getSnapshot) {
      const snap = FE.getSnapshot();
      FE.loadAll({ wizardDefinition: snap.wizardDraft, flowConfig: cfg });
    }
    await loadHistory();
    if (unifiedMode) renderSelectedStep();
    return true;
  }

  async function validateOnly() {
    H.renderError(ui.err, null);
    let payloadCfg = {};
    if (unifiedMode) {
      const s = snapshot();
      payloadCfg = (s && s.configDraft) || {};
    } else {
      try {
        payloadCfg = JSON.parse(ui.ta.value || "{}");
      } catch (e) {
        ui.err.textContent = String(e || "parse error");
        return false;
      }
    }
    if (payloadCfg && typeof payloadCfg === "object") { delete payloadCfg.ui; }
    const out = await H.requestJSON("/import/ui/config/validate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ config: payloadCfg }),
    });
    if (!out.ok) {
      H.renderError(ui.err, out.data);
      return false;
    }
    ui.ta.value = H.pretty(out.data.config || {});

    const FE = window.AM2FlowEditorState;
    if (FE && FE.markValidated && FE.getSnapshot) {
      const snap = FE.getSnapshot();
      FE.markValidated({
        canonicalWizardDefinition: snap.wizardDraft,
        canonicalFlowConfig: out.data.config || {},
        validationEnvelope: { ok: true },
      });
    }

    if (unifiedMode) renderSelectedStep();
    return true;
  }

  async function save() {
    H.renderError(ui.err, null);
    if (unifiedMode) {
      const ok = await validateOnly();
      if (!ok) return false;
    }
    let payloadCfg = {};
    if (unifiedMode) {
      const s = snapshot();
      payloadCfg = (s && s.configDraft) || {};
    } else {
      try {
        payloadCfg = JSON.parse(ui.ta.value || "{}");
      } catch (e) {
        ui.err.textContent = String(e || "parse error");
        return false;
      }
    }
    if (payloadCfg && typeof payloadCfg === "object") { delete payloadCfg.ui; }
    const out = await H.requestJSON("/import/ui/config", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ config: payloadCfg }),
    });
    if (!out.ok) {
      H.renderError(ui.err, out.data);
      return false;
    }
    ui.ta.value = H.pretty(out.data.config || {});

    const FE = window.AM2FlowEditorState;
    if (FE && FE.loadAll && FE.getSnapshot) {
      const snap = FE.getSnapshot();
      FE.loadAll({ wizardDefinition: snap.wizardDraft, flowConfig: out.data.config || {} });
    }

    await loadHistory();
    if (unifiedMode) renderSelectedStep();
    return true;
  }

  async function reset() {
    H.renderError(ui.err, null);
    const out = await H.requestJSON("/import/ui/config/reset", { method: "POST" });
    if (!out.ok) {
      H.renderError(ui.err, out.data);
      return false;
    }
    ui.ta.value = H.pretty(out.data.config || {});

    const FE = window.AM2FlowEditorState;
    if (FE && FE.loadAll && FE.getSnapshot) {
      const snap = FE.getSnapshot();
      FE.loadAll({ wizardDefinition: snap.wizardDraft, flowConfig: out.data.config || {} });
    }

    await loadHistory();
    if (unifiedMode) renderSelectedStep();
    return true;
  }

  async function rollback(id) {
    H.renderError(ui.err, null);
    const out = await H.requestJSON("/import/ui/config/rollback", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: id }),
    });
    if (!out.ok) {
      H.renderError(ui.err, out.data);
      return;
    }
    ui.ta.value = H.pretty(out.data.config || {});

    const FE = window.AM2FlowEditorState;
    if (FE && FE.loadAll && FE.getSnapshot) {
      const snap = FE.getSnapshot();
      FE.loadAll({ wizardDefinition: snap.wizardDraft, flowConfig: out.data.config || {} });
    }

    await loadHistory();
    if (unifiedMode) renderSelectedStep();
  }

  function stableFields(schema) {
    const root = schema && typeof schema === "object" ? schema : {};
    const fields = Array.isArray(root.fields) ? root.fields : [];
    return fields.filter((f) => f && typeof f.key === "string" && f.key);
  }

  function safeDefaultsRoot(cfg) {
    if (!cfg || typeof cfg !== "object") return {};
    if (!cfg.defaults || typeof cfg.defaults !== "object") cfg.defaults = {};
    return cfg.defaults;
  }

  function currentConfig() {
    const s = snapshot();
    return deepClone((s && s.configDraft) || {});
  }

  function emitChanged() {
    try {
      window.dispatchEvent(new CustomEvent("am2:cfg:changed", { detail: {} }));
    } catch (e) {
    }
  }

  function setStepValue(stepId, key, value) {
    const FE = window.AM2FlowEditorState;
    if (FE && FE.mutateConfig) {
      FE.mutateConfig(function (cfg) {
        const defaults = safeDefaultsRoot(cfg);
        if (!defaults[stepId] || typeof defaults[stepId] !== "object") defaults[stepId] = {};
        defaults[stepId][key] = value;
      });
    }

    if (!unifiedMode) {
      ui.ta.value = H.pretty(currentConfig());
      emitChanged();
    }
    updateApplyStatus(stepId);
  }

  function clearStepDefaults(stepId) {
    if (!stepId) return;
    const FE = window.AM2FlowEditorState;
    if (FE && FE.mutateConfig) {
      FE.mutateConfig(function (cfg) {
        const defaults = safeDefaultsRoot(cfg);
        if (defaults && defaults[stepId]) delete defaults[stepId];
      });
    }
    if (!unifiedMode) {
      ui.ta.value = H.pretty(currentConfig());
      emitChanged();
    }
    renderSelectedStep();
  }

  function updateApplyStatus(stepId) {
    if (!ui.stepApply) return;
    if (!stepId) {
      ui.stepApply.textContent = "";
      return;
    }
    const keys = getAppliedKeys(stepId);
    ui.stepApply.textContent = keys.length
      ? "Applied keys: " + keys.join(", ")
      : "No settings applied";
  }

  function getAppliedKeys(stepId) {
    const cfg = currentConfig();
    const defaults = safeDefaultsRoot(cfg);
    const o = defaults[stepId];
    if (!o || typeof o !== "object") return [];
    return Object.keys(o).sort();
  }

  function inputForField(field, stepId) {
    const wrap = document.createElement("div");
    wrap.className = "flowField";

    const label = document.createElement("label");
    label.className = "flowFieldLabel";
    label.textContent = String(field.key || "");

    const meta = document.createElement("div");
    meta.className = "flowFieldMeta";
    const req = field.required ? "required" : "optional";
    const typ = field.type ? String(field.type) : "string";
    meta.textContent = req + " - " + typ;

    const inp = document.createElement("input");
    inp.className = "flowFieldInput";

    const cfg = currentConfig();
    const defaults = safeDefaultsRoot(cfg);
    const cur =
      defaults[stepId] && typeof defaults[stepId] === "object"
        ? defaults[stepId][field.key]
        : undefined;

    if (typ === "bool") {
      inp.type = "checkbox";
      inp.checked = typeof cur === "boolean" ? cur : !!field.default;
      inp.addEventListener("change", () => {
        setStepValue(stepId, field.key, !!inp.checked);
      });
    } else if (typ === "number") {
      inp.type = "number";
      if (typeof cur === "number") inp.value = String(cur);
      else if (typeof field.default === "number") inp.value = String(field.default);
      inp.addEventListener("input", () => {
        const v = inp.value === "" ? null : Number(inp.value);
        if (inp.value === "") {
          setStepValue(stepId, field.key, null);
        } else if (!Number.isNaN(v)) {
          setStepValue(stepId, field.key, v);
        }
      });
    } else {
      inp.type = "text";
      inp.value = typeof cur === "string" ? cur : String(field.default || "");
      inp.addEventListener("input", () => {
        setStepValue(stepId, field.key, String(inp.value || ""));
      });
    }

    wrap.appendChild(label);
    wrap.appendChild(meta);
    wrap.appendChild(inp);
    return wrap;
  }

  function clearNode(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function setStepError(msg) {
    if (!ui.stepError) return;
    ui.stepError.textContent = String(msg || "");
  }

  async function fetchStepDetails(stepId) {
    const sid = String(stepId || "");
    if (!sid) return null;
    if (stepCache[sid]) return stepCache[sid];
    const out = await H.requestJSON("/import/ui/steps/" + encodeURIComponent(sid));
    if (!out.ok) {
      setStepError("Failed to load step details");
      return null;
    }
    const d = out.data && typeof out.data === "object" ? out.data : {};
    stepCache[sid] = d;
    return d;
  }

  async function renderSelectedStep() {
    if (!unifiedMode) return;
    const s = snapshot();
    const stepId = (s && s.selectedStepId) || null;

    if (!ui.stepHeader || !ui.stepBehavior || !ui.stepForm || !ui.stepApply) return;

    setStepError("");

    if (!stepId) {
      ui.stepHeader.textContent = "Select a step";
      ui.stepBehavior.textContent = "";
      if (ui.stepInput) ui.stepInput.textContent = "";
      if (ui.stepOutput) ui.stepOutput.textContent = "";
      if (ui.stepSideEffects) ui.stepSideEffects.textContent = "";
      clearNode(ui.stepForm);
      ui.stepApply.textContent = "";
      return;
    }

    const det = await fetchStepDetails(stepId);
    const title =
      det && (det.displayName || det.title) ? String(det.displayName || det.title) : "";
    const behavior = det && det.behavioralSummary ? String(det.behavioralSummary) : "";
    const inC = det && det.inputContract ? String(det.inputContract) : "";
    const outC = det && det.outputContract ? String(det.outputContract) : "";
    const sideFx = det && det.sideEffectsDescription ? String(det.sideEffectsDescription) : "";
    const schema = det && det.settings_schema ? det.settings_schema : {};

    ui.stepHeader.textContent = title ? stepId + " - " + title : stepId;
    ui.stepBehavior.textContent = behavior;
    if (ui.stepInput) ui.stepInput.textContent = inC;
    if (ui.stepOutput) ui.stepOutput.textContent = outC;
    if (ui.stepSideEffects) ui.stepSideEffects.textContent = sideFx;

    clearNode(ui.stepForm);
    stableFields(schema).forEach((f) => {
      ui.stepForm.appendChild(inputForField(f, stepId));
    });

    const keys = getAppliedKeys(stepId);
    updateApplyStatus(stepId);
  }

  window.addEventListener("am2:wd:selected", async (e) => {
    await renderSelectedStep();
  });

  ui.clearStep &&
    ui.clearStep.addEventListener("click", () => {
      const s = snapshot();
      clearStepDefaults((s && s.selectedStepId) || null);
    });

  ui.reload && ui.reload.addEventListener("click", reload);
  ui.validate && ui.validate.addEventListener("click", validateOnly);
  ui.save && ui.save.addEventListener("click", save);
  ui.reset && ui.reset.addEventListener("click", reset);

  window.AM2FlowConfigEditor = {
    reload: reload,
    validate: validateOnly,
    save: save,
    reset: reset,
    _debug_getDraft: () => currentConfig(),
  };


  const FE = window.AM2FlowEditorState;
  if (FE && FE.registerConfigRender) {
    FE.registerConfigRender(function () {
      if (unifiedMode) renderSelectedStep();
    });
  }

  reload();
})();