(function () {
  "use strict";

  const H = window.AM2EditorHTTP;
  if (!H) return;

  function $(id) {
    return document.getElementById(id);
  }

  const ui = {
    ta: $("wdJson"),
    err: $("wdError"),
    history: $("wdHistory"),
    reload: $("wdReload"),
    validate: $("wdValidate"),
    save: $("wdSave"),
    reset: $("wdReset"),
  };

  if (!ui.ta) return;

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function el(tag, cls) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    return n;
  }

  function text(tag, cls, s) {
    const n = el(tag, cls);
    n.textContent = String(s || "");
    return n;
  }

  const stableGraph =
    window.AM2WDGraphStable && window.AM2WDGraphStable.stableGraph
      ? window.AM2WDGraphStable.stableGraph
      : function () {
          return { version: 1, nodes: [], edges: [], entry: null };
        };

  function deepClone(x) {
    return x === undefined ? undefined : JSON.parse(JSON.stringify(x));
  }

  function stripUi(defn) {
    const x = deepClone(defn || {});
    if (x && x._am2_ui) delete x._am2_ui;
    return x;
  }

  function ensureWizardUi(wd) {
    if (!wd || typeof wd !== "object") return { showOptional: true };
    if (!wd._am2_ui || typeof wd._am2_ui !== "object") {
      wd._am2_ui = {
        dragId: null,
        dropBeforeId: null,
        showOptional: true,
        validation: { ok: null, local: [], server: [] },
        showRawError: false,
        hasErrorDetails: false,
      };
    }
    return wd._am2_ui;
  }

  function snapshot() {
    const FE = window.AM2FlowEditorState;
    return FE && FE.getSnapshot ? FE.getSnapshot() : null;
  }

  function wizardDraft() {
    const s = snapshot();
    return (s && s.wizardDraft) || {};
  }

  function selectedStepId() {
    const s = snapshot();
    return (s && s.selectedStepId) || null;
  }

  function mutateWizard(fn) {
    const FE = window.AM2FlowEditorState;
    if (!FE || !FE.mutateWizard) return;
    FE.mutateWizard(function (wd) {
      fn && fn(ensureWizardUi(wd), wd);
    });
  }

  function setSelectedStep(stepIdOrNull) {
    const FE = window.AM2FlowEditorState;
    if (FE && FE.setSelectedStep) FE.setSelectedStep(stepIdOrNull || null);
  }

  function defFromGraph(nodes, entryStepId, edges) {
    const entry = entryStepId || (nodes && nodes[0]) || "";
    return {
      version: 2,
      wizard_id: "import",
      graph: {
        entry_step_id: String(entry || ""),
        nodes: (nodes || []).map((sid) => ({ step_id: sid })),
        edges: (edges || []).map((e) => ({
          from_step_id: e.from_step_id,
          to_step_id: e.to_step_id,
          priority: typeof e.priority === "number" ? e.priority : 0,
          when: e.when === undefined ? null : e.when,
        })),
      },
    };
  }

  function ensureV2() {
    mutateWizard(function (uiState, wd) {
      const g = stableGraph(wd);
      const nodes = Array.isArray(g.nodes) ? g.nodes.slice(0) : [];
      const edges = Array.isArray(g.edges) ? g.edges.slice(0) : [];
      const v2 = defFromGraph(nodes, g.entry, edges);
      v2._am2_ui = uiState;
      Object.keys(wd).forEach((k) => delete wd[k]);
      Object.assign(wd, v2);
    });
  }

  const paletteItems = [];

  const root =
    window.AM2WDLayoutRoot && window.AM2WDLayoutRoot.createRoot
      ? window.AM2WDLayoutRoot.createRoot({ ui: ui, el: el, text: text })
      : null;

  const flowSidebar = $("flowEditorSidebar");
  const stepPanel = $("flowStepPanel");
  const transitionsPanel = $("flowTransitionsPanel");
  const palettePanel = $("flowPalettePanel");

  if (
    window.AM2WDSidebar &&
    window.AM2WDSidebar.buildSidebarSections &&
    flowSidebar &&
    stepPanel &&
    transitionsPanel &&
    palettePanel
  ) {
    window.AM2WDSidebar.buildSidebarSections({
      flowSidebar: flowSidebar,
      stepPanel: stepPanel,
      transitionsPanel: transitionsPanel,
      rightCol: palettePanel,
      clear: clear,
      el: el,
      text: text,
    });
  }

  function isOptionalStep(stepId) {
    const sid = String(stepId || "");
    return sid && sid !== "select_authors" && sid !== "select_books" && sid !== "processing";
  }

  function canRemove(stepId) {
    return isOptionalStep(stepId);
  }

  function hasStep(stepId) {
    const g = stableGraph(wizardDraft());
    const nodes = Array.isArray(g.nodes) ? g.nodes : [];
    return nodes.indexOf(String(stepId || "")) >= 0;
  }

  function addStep(stepId) {
    ensureV2();
    mutateWizard(function (uiState, wd) {
      const g = stableGraph(wd);
      const nodes = Array.isArray(g.nodes) ? g.nodes.slice(0) : [];
      const sid = String(stepId || "");
      if (!sid || nodes.indexOf(sid) >= 0) return;
      nodes.splice(nodes.length - 1, 0, sid);
      const next = defFromGraph(nodes, g.entry, g.edges);
      next._am2_ui = uiState;
      Object.keys(wd).forEach((k) => delete wd[k]);
      Object.assign(wd, next);
    });
  }

  function removeStep(stepId) {
    ensureV2();
    mutateWizard(function (uiState, wd) {
      const g = stableGraph(wd);
      const sid = String(stepId || "");
      const nodes = Array.isArray(g.nodes) ? g.nodes.slice(0) : [];
      const idx = nodes.indexOf(sid);
      if (idx < 0) return;
      if (!canRemove(sid)) return;
      nodes.splice(idx, 1);
      const edges = (Array.isArray(g.edges) ? g.edges : []).filter(function (e) {
        return String(e.from_step_id || "") !== sid && String(e.to_step_id || "") !== sid;
      });
      const next = defFromGraph(nodes, g.entry, edges);
      next._am2_ui = uiState;
      Object.keys(wd).forEach((k) => delete wd[k]);
      Object.assign(wd, next);
      if (selectedStepId() === sid) setSelectedStep(null);
    });
  }


  function reorderStep(dragStepId, dropBeforeStepIdOrNull) {
    ensureV2();
    mutateWizard(function (uiState, wd) {
      const g = stableGraph(wd);
      const nodes = Array.isArray(g.nodes) ? g.nodes.slice(0) : [];
      const dragId = String(dragStepId || "");
      const dropBeforeId = dropBeforeStepIdOrNull ? String(dropBeforeStepIdOrNull) : null;
      const fromIdx = nodes.indexOf(dragId);
      if (fromIdx < 0) return;
      if (dropBeforeId && dropBeforeId === dragId) return;
      nodes.splice(fromIdx, 1);
      let toIdx = -1;
      if (dropBeforeId) toIdx = nodes.indexOf(dropBeforeId);
      if (toIdx < 0) {
        nodes.push(dragId);
      } else {
        nodes.splice(toIdx, 0, dragId);
      }
      const next = defFromGraph(nodes, g.entry, g.edges);
      next._am2_ui = uiState;
      Object.keys(wd).forEach((k) => delete wd[k]);
      Object.assign(wd, next);
    });
  }

  function moveStepUp(stepId) {
    ensureV2();
    mutateWizard(function (uiState, wd) {
      const g = stableGraph(wd);
      const nodes = Array.isArray(g.nodes) ? g.nodes.slice(0) : [];
      const sid = String(stepId || "");
      const idx = nodes.indexOf(sid);
      if (idx <= 0) return;
      const tmp = nodes[idx - 1];
      nodes[idx - 1] = nodes[idx];
      nodes[idx] = tmp;
      const next = defFromGraph(nodes, g.entry, g.edges);
      next._am2_ui = uiState;
      Object.keys(wd).forEach((k) => delete wd[k]);
      Object.assign(wd, next);
    });
  }

  function moveStepDown(stepId) {
    ensureV2();
    mutateWizard(function (uiState, wd) {
      const g = stableGraph(wd);
      const nodes = Array.isArray(g.nodes) ? g.nodes.slice(0) : [];
      const sid = String(stepId || "");
      const idx = nodes.indexOf(sid);
      if (idx < 0 || idx >= nodes.length - 1) return;
      const tmp = nodes[idx + 1];
      nodes[idx + 1] = nodes[idx];
      nodes[idx] = tmp;
      const next = defFromGraph(nodes, g.entry, g.edges);
      next._am2_ui = uiState;
      Object.keys(wd).forEach((k) => delete wd[k]);
      Object.assign(wd, next);
    });
  }
  function addEdge(fromId, toId, prio, whenVal) {
    ensureV2();
    mutateWizard(function (uiState, wd) {
      const g = stableGraph(wd);
      const edges = Array.isArray(g.edges) ? g.edges.slice(0) : [];
      edges.push({
        from_step_id: String(fromId || ""),
        to_step_id: String(toId || ""),
        priority: Number(prio || 0),
        when: whenVal === undefined ? null : whenVal,
      });
      const next = defFromGraph(g.nodes, g.entry, edges);
      next._am2_ui = uiState;
      Object.keys(wd).forEach((k) => delete wd[k]);
      Object.assign(wd, next);
    });
  }

  function removeEdge(fromId, outgoingIndex) {
    ensureV2();
    mutateWizard(function (uiState, wd) {
      const g = stableGraph(wd);
      const from = String(fromId || "");
      const edgesAll = Array.isArray(g.edges) ? g.edges.slice(0) : [];
      const outgoing = edgesAll.filter((e) => String(e.from_step_id || "") === from);
      const target = outgoing[outgoingIndex];
      if (!target) return;
      const idx = edgesAll.indexOf(target);
      if (idx < 0) return;
      edgesAll.splice(idx, 1);
      const next = defFromGraph(g.nodes, g.entry, edgesAll);
      next._am2_ui = uiState;
      Object.keys(wd).forEach((k) => delete wd[k]);
      Object.assign(wd, next);
    });
  }

  function setValidation(ok, localMsgs, serverMsgs) {
    mutateWizard(function (uiState) {
      uiState.validation = {
        ok: ok,
        local: Array.isArray(localMsgs) ? localMsgs : [],
        server: Array.isArray(serverMsgs) ? serverMsgs : [],
      };
    });
  }

  function validationMessages() {
    const u = ensureWizardUi(wizardDraft());
    const v = u.validation || {};
    const msgs = [];
    (Array.isArray(v.local) ? v.local : []).forEach((m) => msgs.push(m));
    (Array.isArray(v.server) ? v.server : []).forEach((m) => msgs.push(m));
    return msgs;
  }

  function extractServerMessages(errEnvelope) {
    const details = errEnvelope && errEnvelope.details;
    const out = [];
    (Array.isArray(details) ? details : []).forEach(function (d) {
      if (!d) return;
      const path = d.path ? String(d.path) : "";
      const reason = d.reason ? String(d.reason) : "";
      if (path || reason) out.push(path + " " + reason);
    });
    return out;
  }

  function renderError(data, collapseByDefault) {
    H.renderError(ui.err, data);
    mutateWizard(function (uiState) {
      uiState.hasErrorDetails = !!data;
      uiState.showRawError = data ? !collapseByDefault : false;
    });
  }

  function setupRawErrorPanel() {
    const rawErrorState = {};
    Object.defineProperty(rawErrorState, "showRawError", {
      get: function () {
        return !!((wizardDraft()._am2_ui || {}).showRawError);
      },
      set: function (on) {
        mutateWizard(function (uiState) {
          uiState.showRawError = !!on;
        });
      },
    });
    Object.defineProperty(rawErrorState, "hasErrorDetails", {
      get: function () {
        return !!((wizardDraft()._am2_ui || {}).hasErrorDetails);
      },
      set: function (on) {
        mutateWizard(function (uiState) {
          uiState.hasErrorDetails = !!on;
        });
      },
    });
    if (window.AM2WDRawError && window.AM2WDRawError.setupRawErrorPanel) {
      window.AM2WDRawError.setupRawErrorPanel({
        ui: ui,
        state: rawErrorState,
        el: el,
        text: text,
      });
    }
    rawErrorState.showRawError = false;
    if (!ui.err) return;
    ui.err.classList.toggle("is-collapsed", !rawErrorState.showRawError);

    const btn = document.querySelector(".wdErrToggle");
    if (btn) btn.textContent = rawErrorState.showRawError ? "Hide Details" : "Details";
  }

  setupRawErrorPanel();

  function isDirty() {
    const s = snapshot();
    return !!(s && s.draftDirty);
  }

  function confirmIfDirty(actionName) {
    if (!isDirty()) return true;
    return window.confirm(
      actionName +
        " will discard unsaved edits. Run Validate All first, or reload after saving. Continue?"
    );
  }

  function historyRow(item) {
    const row = el("div", "historyItem");
    const meta = el("div", "historyMeta");
    meta.appendChild(text("div", null, item.id || ""));
    meta.appendChild(text("div", null, item.timestamp || ""));
    const btn = text("button", "btn", "Rollback");
    btn.addEventListener("click", async () => {
      await rollback(String(item.id || ""));
    });
    row.appendChild(meta);
    row.appendChild(btn);
    return row;
  }

  async function loadHistory() {
    const out = await H.requestJSON("/import/ui/wizard-definition/history");
    if (!out.ok) {
      renderError(out.data, false);
      return;
    }
    clear(ui.history);
    const items = out.data && out.data.items ? out.data.items : [];
    (Array.isArray(items) ? items : []).forEach((it) => {
      ui.history.appendChild(historyRow(it || {}));
    });
  }

  async function loadPalette() {
    const out = await H.requestJSON("/import/ui/steps-index");
    if (!out.ok) {
      renderError(out.data, false);
      return false;
    }
    const items = out.data && out.data.items ? out.data.items : [];
    paletteItems.length = 0;
    (Array.isArray(items) ? items : []).forEach(function (it) {
      paletteItems.push(it);
    });
    return true;
  }

  async function loadDefinition() {
    const out = await H.requestJSON("/import/ui/wizard-definition");
    if (!out.ok) {
      renderError(out.data, false);
      return false;
    }
    const defn = out.data && out.data.definition ? out.data.definition : {};
    const FE = window.AM2FlowEditorState;
    if (FE && FE.loadAll && FE.getSnapshot) {
      const snap = FE.getSnapshot();
      FE.loadAll({ wizardDefinition: defn, flowConfig: snap.configDraft });
    }
    return true;
  }

  async function reloadAll() {
    if (!confirmIfDirty("Reload")) return;
    renderError(null, false);
    setValidation(null, [], []);
    const ok1 = await loadPalette();
    const ok2 = await loadDefinition();
    if (ok1 && ok2) {
      await loadHistory();
      renderAll();
    }
    return !!(ok1 && ok2);
  }

  async function validateDraft() {
    renderError(null, false);
    setValidation(null, [], []);
    const s = snapshot();
    const payload = { definition: stripUi((s && s.wizardDraft) || {}) };
    const out = await H.requestJSON("/import/ui/wizard-definition/validate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!out.ok) {
      renderError(out.data, true);
      setValidation(
        false,
        ["Validation failed. See error details above."],
        extractServerMessages(out.data)
      );
      renderAll();
      return false;
    }
    const defn = out.data && out.data.definition ? out.data.definition : {};
    const FE = window.AM2FlowEditorState;
    if (FE && FE.markValidated && FE.getSnapshot) {
      const snap = FE.getSnapshot();
      FE.markValidated({
        canonicalWizardDefinition: defn,
        canonicalFlowConfig: snap.configDraft,
        validationEnvelope: { ok: true },
      });
    }
    setValidation(true, [], []);
    renderAll();
    return true;
  }

  async function saveDraft() {
    if (!(await validateDraft())) return false;
    const s = snapshot();
    const payload = { definition: stripUi((s && s.wizardDraft) || {}) };
    const out = await H.requestJSON("/import/ui/wizard-definition", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!out.ok) {
      renderError(out.data, false);
      return false;
    }
    const defn = out.data && out.data.definition ? out.data.definition : {};
    const FE = window.AM2FlowEditorState;
    if (FE && FE.loadAll && FE.getSnapshot) {
      const snap = FE.getSnapshot();
      FE.loadAll({ wizardDefinition: defn, flowConfig: snap.configDraft });
    }
    await loadHistory();
    renderAll();
    return true;
  }

  async function resetDefinition() {
    if (!confirmIfDirty("Reset")) return;

    renderError(null, false);
    setValidation(null, [], []);
    const out = await H.requestJSON("/import/ui/wizard-definition/reset", {
      method: "POST",
    });
    if (!out.ok) {
      renderError(out.data, false);
      return false;
    }
    const defn = out.data && out.data.definition ? out.data.definition : {};
    const FE = window.AM2FlowEditorState;
    if (FE && FE.loadAll && FE.getSnapshot) {
      const snap = FE.getSnapshot();
      FE.loadAll({ wizardDefinition: defn, flowConfig: snap.configDraft });
    }
    await loadHistory();
    renderAll();
    return true;
  }

  async function rollback(id) {
    if (!confirmIfDirty("Rollback")) return;

    renderError(null, false);
    setValidation(null, [], []);
    const out = await H.requestJSON("/import/ui/wizard-definition/rollback", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: id }),
    });
    if (!out.ok) {
      renderError(out.data, false);
      return;
    }
    const defn = out.data && out.data.definition ? out.data.definition : {};
    const FE = window.AM2FlowEditorState;
    if (FE && FE.loadAll && FE.getSnapshot) {
      const snap = FE.getSnapshot();
      FE.loadAll({ wizardDefinition: defn, flowConfig: snap.configDraft });
    }
    await loadHistory();
    renderAll();
  }

  function buildToolbar() {
    if (!root) return;
    clear(root.toolbar);

    const btnAdd = text("button", "btn", "Add Step");
    const optLabel = el("label", "wdToggle");
    const optToggle = el("input", "wdToggleInput");
    optToggle.type = "checkbox";
    optToggle.checked = true;
    optLabel.appendChild(optToggle);
    optLabel.appendChild(text("span", "wdToggleText", "Show Optional"));

    btnAdd.type = "button";
    btnAdd.addEventListener("click", function () {
      try {
        window.dispatchEvent(new CustomEvent("am2:palette:focus", { detail: {} }));
      } catch (e) {
        // ignore
      }
    });

    optToggle.addEventListener("change", function () {
      mutateWizard(function (uiState) {
        uiState.showOptional = !!optToggle.checked;
      });
      renderAll();
    });

    root.toolbar.appendChild(btnAdd);
    root.toolbar.appendChild(optLabel);
  }

  const table =
    window.AM2WDTableRender && window.AM2WDTableRender.initTable && root
      ? window.AM2WDTableRender.initTable({
          body: root.tableBody,
          el: el,
          text: text,
          state: {
            getWizardDraft: wizardDraft,
            getSelectedStepId: selectedStepId,
            isOptional: isOptionalStep,
            canRemove: canRemove,
            setSelectedStep: setSelectedStep,
            removeStep: function (sid) {
              removeStep(sid);
              renderAll();
            },
            moveStepUp: function (sid) {
              moveStepUp(sid);
              renderAll();
            },
            moveStepDown: function (sid) {
              moveStepDown(sid);
              renderAll();
            },
            reorderStep: function (dragSid, dropBeforeSidOrNull) {
              reorderStep(dragSid, dropBeforeSidOrNull);
              renderAll();
            },
          },
        })
      : null;

  function renderAll() {
    buildToolbar();

    if (table && table.renderAll) table.renderAll();

    if (window.AM2WDDetailsRender && window.AM2WDDetailsRender.renderValidation && root) {
      window.AM2WDDetailsRender.renderValidation({
        mount: root.validationList,
        countEl: root.validationCount,
        el: el,
        text: text,
        messages: validationMessages(),
      });
    }

    if (window.AM2WDPaletteRender && window.AM2WDPaletteRender.renderPalette && palettePanel) {
      window.AM2WDPaletteRender.renderPalette({
        mount: palettePanel,
        el: el,
        text: text,
        items: paletteItems,
        state: {
          canAdd: function (sid) {
            return !hasStep(sid);
          },
          addStep: function (sid) {
            addStep(sid);
            renderAll();
          },
        },
      });
    }

    if (
      window.AM2WDTransitionsRender &&
      window.AM2WDTransitionsRender.renderTransitions &&
      transitionsPanel
    ) {
      window.AM2WDTransitionsRender.renderTransitions({
        mount: transitionsPanel,
        el: el,
        text: text,
        state: {
          getWizardDraft: wizardDraft,
          getSelectedStepId: selectedStepId,
          addEdge: function (fromId, toId, prio, whenVal) {
            addEdge(fromId, toId, prio, whenVal);
            renderAll();
          },
          removeEdge: function (fromId, outgoingIndex) {
            removeEdge(fromId, outgoingIndex);
            renderAll();
          },
        },
      });
    }

    if (root && root.validationClear) {
      root.validationClear.onclick = function () {
        setValidation(null, [], []);
        renderAll();
      };
    }
  }

  const FE = window.AM2FlowEditorState;
  if (FE && FE.on) {
    FE.on("wizard_changed", function () {
      renderAll();
    });
    FE.on("selection_changed", function () {
      if (table && table.updateSelection) table.updateSelection();
      renderAll();
    });
  } else if (FE && FE.registerWizardRender) {
    FE.registerWizardRender(renderAll);
  }

  if (ui.reload) ui.reload.addEventListener("click", reloadAll);
  if (ui.validate) ui.validate.addEventListener("click", validateDraft);
  if (ui.save) ui.save.addEventListener("click", saveDraft);
  if (ui.reset) ui.reset.addEventListener("click", resetDefinition);

  window.AM2WizardDefinitionEditor = {
    reloadAll: reloadAll,
    validateDraft: validateDraft,
    saveDraft: saveDraft,
  };

  reloadAll();
})();
