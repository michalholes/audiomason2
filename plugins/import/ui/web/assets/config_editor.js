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
    stepDesc: $("flowStepDesc"),
    stepForm: $("flowStepForm"),
    stepApply: $("flowStepApply"),
    stepError: $("flowStepError"),
    clearStep: $("flowClearStep"),
  };

  if (!ui.ta) return;

  const unifiedMode = !!ui.stepPanel;

  const state = {
    loaded: null,
    draft: null,
    selectedStepId: null,
    stepCache: {},
  };

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
    state.loaded = cfg;
    state.draft = JSON.parse(JSON.stringify(cfg || {}));
    await loadHistory();
    if (unifiedMode) renderSelectedStep();
    return true;
  }

  async function validateOnly() {
    H.renderError(ui.err, null);
    let payloadCfg = {};
    if (unifiedMode) {
      payloadCfg = state.draft || {};
    } else {
      try {
        payloadCfg = JSON.parse(ui.ta.value || "{}");
      } catch (e) {
        ui.err.textContent = String(e || "parse error");
        return false;
      }
    }
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
    state.draft = out.data.config || {};
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
      payloadCfg = state.draft || {};
    } else {
      try {
        payloadCfg = JSON.parse(ui.ta.value || "{}");
      } catch (e) {
        ui.err.textContent = String(e || "parse error");
        return false;
      }
    }
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
    state.loaded = out.data.config || {};
    state.draft = JSON.parse(JSON.stringify(state.loaded || {}));
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
    state.loaded = out.data.config || {};
    state.draft = JSON.parse(JSON.stringify(state.loaded || {}));
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
    state.loaded = out.data.config || {};
    state.draft = JSON.parse(JSON.stringify(state.loaded || {}));
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

  function setStepValue(stepId, key, value) {
    if (!state.draft || typeof state.draft !== "object") state.draft = {};
    const defaults = safeDefaultsRoot(state.draft);
    if (!defaults[stepId] || typeof defaults[stepId] !== "object") {
      defaults[stepId] = {};
    }
    defaults[stepId][key] = value;
    ui.ta.value = H.pretty(state.draft || {});

    try {
      window.dispatchEvent(new CustomEvent("am2:cfg:changed", { detail: {} }));
    } catch (e) {
      // ignore
    }

    updateApplyStatus(stepId);
  }

  function clearStepDefaults(stepId) {
    if (!stepId) return;
    const defaults = safeDefaultsRoot(state.draft);
    if (defaults[stepId]) delete defaults[stepId];
    ui.ta.value = H.pretty(state.draft || {});
    try {
      window.dispatchEvent(new CustomEvent("am2:cfg:changed", { detail: {} }));
    } catch (e) {
      // ignore
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
    const defaults = safeDefaultsRoot(state.draft);
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

    const defaults = safeDefaultsRoot(state.draft);
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
    if (state.stepCache[sid]) return state.stepCache[sid];
    const out = await H.requestJSON("/import/ui/steps/" + encodeURIComponent(sid));
    if (!out.ok) {
      setStepError("Failed to load step details");
      return null;
    }
    const d = out.data && typeof out.data === "object" ? out.data : {};
    state.stepCache[sid] = d;
    return d;
  }

  async function renderSelectedStep() {
    if (!unifiedMode) return;
    const stepId = state.selectedStepId;

    if (!ui.stepHeader || !ui.stepDesc || !ui.stepForm || !ui.stepApply) return;

    setStepError("");

    if (!stepId) {
      ui.stepHeader.textContent = "Select a step";
      ui.stepDesc.textContent = "";
      clearNode(ui.stepForm);
      ui.stepApply.textContent = "";
      return;
    }

    const det = await fetchStepDetails(stepId);
    const title = det && det.title ? String(det.title) : "";
    const desc = det && det.description ? String(det.description) : "";
    const schema = det && det.settings_schema ? det.settings_schema : {};

    ui.stepHeader.textContent = title ? stepId + " - " + title : stepId;
    ui.stepDesc.textContent = desc;

    clearNode(ui.stepForm);
    stableFields(schema).forEach((f) => {
      ui.stepForm.appendChild(inputForField(f, stepId));
    });

    const keys = getAppliedKeys(stepId);
    updateApplyStatus(stepId);
  }

  window.addEventListener("am2:wd:selected", async (e) => {
    const d = e && e.detail ? e.detail : {};
    const sid = typeof d.step_id === "string" ? d.step_id : null;
    state.selectedStepId = sid;
    await renderSelectedStep();
  });

  ui.clearStep &&
    ui.clearStep.addEventListener("click", () => {
      clearStepDefaults(state.selectedStepId);
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
    _debug_getDraft: () => state.draft,
  };

  reload();
})();
