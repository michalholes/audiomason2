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

  const svgIcon =
    window.AM2WDDomIcons && window.AM2WDDomIcons.svgIcon
      ? window.AM2WDDomIcons.svgIcon
      : function () {
          return document.createElement("span");
        };

  const stableGraph =
    window.AM2WDGraphStable && window.AM2WDGraphStable.stableGraph
      ? window.AM2WDGraphStable.stableGraph
      : function () {
          return { version: 1, nodes: [], edges: [], entry: null };
        };

  function defFromGraph(nodes, entryStepId, edges) {
    const entry = entryStepId || (nodes && nodes[0]) || null;
    return {
      version: 2,
      wizard_id: "import",
      graph: {
        entry_step_id: entry || "",
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

  function defFromSteps(stepIds) {
    return defFromGraph(stepIds || [], view.entry_step_id, view.edges || []);
  }


  const view = {
    draft: [],
    palette: [],
    selected: null,
    dragId: null,
    dropBeforeId: null,
    showOptional: true,
    validation: { ok: null, local: [], server: [] },
    showRawError: false,
    hasErrorDetails: false,

    entry_step_id: null,
    edges: [],
    rightTab: "details",
    editingEdgeIdx: null,
  };

  const layout = el("div", "wdLayout wdLayoutSingle");
  const leftCol = el("div", "wdLeftCol");
  const rightCol = el("div", "wdPalette");

  const toolbar = el("div", "wdToolbar");
  const btnAdd = text("button", "btn", "Add Step");
  const btnRemove = text("button", "btn", "Remove");
  const btnUp = text("button", "btn", "Move Up");
  const btnDown = text("button", "btn", "Move Down");
  const optLabel = el("label", "wdToggle");
  const optToggle = el("input", "wdToggleInput");
  optToggle.type = "checkbox";
  optToggle.checked = true;
  optLabel.appendChild(optToggle);
  optLabel.appendChild(text("span", "wdToggleText", "Show Optional"));

  toolbar.appendChild(btnAdd);
  toolbar.appendChild(btnRemove);
  toolbar.appendChild(btnUp);
  toolbar.appendChild(btnDown);
  toolbar.appendChild(optLabel);

  const table = el("div", "wdTable");
  const head = el("div", "wdHead");
  head.appendChild(text("div", "wdCellOrder", "Order"));
  head.appendChild(text("div", "wdCellId", "Step ID"));
  head.appendChild(text("div", "wdCellType", "Type"));
  head.appendChild(text("div", "wdCellReq", "Required"));
  head.appendChild(text("div", "wdCellActions", "Actions"));
  const body = el("div", "wdBody");

  const dropHint = el("div", "wdDropHint");
  dropHint.appendChild(text("div", "wdDropHintText", "Drop to insert"));

  const validation = el("div", "wdValidation");
  const validationHeader = el("div", "wdValidationHeader");
  const validationTitle = text(
    "div",
    "wdValidationTitle",
    "Validation Messages"
  );
  const validationCount = text("div", "wdValidationCount", "");
  const validationClear = text("button", "btn wdValidationClear", "Clear All");
  validationClear.type = "button";
  const validationList = el("div", "wdValidationList");

  validationHeader.appendChild(validationTitle);
  validationHeader.appendChild(validationCount);
  validationHeader.appendChild(validationClear);
  validation.appendChild(validationHeader);
  validation.appendChild(validationList);

  table.appendChild(head);
  table.appendChild(body);

  const paletteHeader = el("div", "wdPaletteHeader");
  paletteHeader.appendChild(text("div", "wdPaletteTitle", "Step Palette"));
  paletteHeader.appendChild(el("div", "wdPaletteSpacer"));

  const paletteSearch = el("div", "wdPaletteSearch");
  const searchIcon = el("span", "wdSearchIcon");
  searchIcon.appendChild(svgIcon("search", "wdSvg", "Search"));
  const search = el("input", "wdPaletteSearchInput");
  search.type = "search";
  search.placeholder = "Search";
  paletteSearch.appendChild(searchIcon);
  paletteSearch.appendChild(search);

  const paletteGroups = el("div", "wdPaletteGroups");
  rightCol.appendChild(paletteHeader);
  rightCol.appendChild(paletteSearch);
  rightCol.appendChild(paletteGroups);

  leftCol.appendChild(toolbar);
  leftCol.appendChild(table);
  leftCol.appendChild(dropHint);
  leftCol.appendChild(validation);

  layout.appendChild(leftCol);

  ui.ta.parentNode.insertBefore(layout, ui.ta);
  ui.ta.classList.add("wdHidden");

  const flowSidebar = document.getElementById("flowEditorSidebar");
  const stepPanel = document.getElementById("flowStepPanel");
  const transitionsPanel = el("div", "flowTransPanel");

  if (window.AM2WDSidebar && window.AM2WDSidebar.buildSidebarTabs) {
    window.AM2WDSidebar.buildSidebarTabs({
      flowSidebar: flowSidebar,
      stepPanel: stepPanel,
      transitionsPanel: transitionsPanel,
      rightCol: rightCol,
      state: view,
      clear: clear,
      el: el,
      text: text,
      renderTransitions: function () {
        renderTransitions();
      },
    });
  }
  if (window.AM2WDSidebar && window.AM2WDSidebar.clearSidebar) {
    window.AM2WDSidebar.clearSidebar(view);
  }

  function setupRawErrorPanel() {
    if (window.AM2WDRawError && window.AM2WDRawError.setupRawErrorPanel) {
      window.AM2WDRawError.setupRawErrorPanel({ ui: ui, state: view, el: el, text: text });
    }
    setRawErrorVisible(false);
  }

  function setRawErrorVisible(on) {
    view.showRawError = !!on;
    if (!ui.err) return;
    ui.err.classList.toggle("is-collapsed", !view.showRawError);

    const btn = document.querySelector(".wdErrToggle");
    if (btn) btn.textContent = view.showRawError ? "Hide Details" : "Details";
  }

  function renderError(data, collapseByDefault) {
    H.renderError(ui.err, data);
    view.hasErrorDetails = !!data;
    if (!data) {
      setRawErrorVisible(false);
      return;
    }
    setRawErrorVisible(!collapseByDefault);
  }


  setupRawErrorPanel();

  function refreshFromFlowState() {
    const FE = window.AM2FlowEditorState;
    if (!FE || !FE.getSnapshot) return;
    const s = FE.getSnapshot();
    const defn = (s && s.wizardDraft) || {};
    const g = stableGraph(defn);
    view.draft = g.nodes.slice();
    view.edges = Array.isArray(g.edges) ? g.edges.slice() : [];
    view.entry_step_id = g.entry || null;
    view.selected = (s && s.selectedStepId) || null;
    normalizeEdges();
  }


  function isDirty() {
    const FE = window.AM2FlowEditorState;
    if (!FE || !FE.getSnapshot) return false;
    const s = FE.getSnapshot();
    return !!(s && s.draftDirty);
  }

  function confirmIfDirty(actionName) {
    if (!isDirty()) return true;
    return window.confirm("Unsaved changes. Continue: " + actionName + "?");
  }

  function kindOf(stepId) {
    const item = view.palette.find((x) => x && x.step_id === stepId);
    return item && item.kind ? String(item.kind) : "optional";
  }

  function pinnedOf(stepId) {
    const item = view.palette.find((x) => x && x.step_id === stepId);
    return item && item.pinned ? String(item.pinned) : "none";
  }

  function isPinned(stepId) {
    const p = pinnedOf(stepId);
    return p === "first" || p === "last";
  }

  function isMandatory(stepId) {
    return kindOf(stepId) === "mandatory";
  }

  function canRemove(stepId) {
    if (isPinned(stepId)) return false;
    if (isMandatory(stepId)) return false;
    return true;
  }

  function idxOf(stepId) {
    return view.draft.indexOf(stepId);
  }

  function clampDropIndex(idx) {
    const first = idxOf("select_authors");
    const last = idxOf("processing");
    const min = first >= 0 ? first + 1 : 0;
    const max = last >= 0 ? last : view.draft.length;
    if (idx < min) return min;
    if (idx > max) return max;
    return idx;
  }

  function syncTextarea() {
    ui.ta.value = H.pretty(defFromGraph(view.draft, view.entry_step_id, view.edges));
  }

  function setSelected(stepId) {
    const FE = window.AM2FlowEditorState;
    const next = stepId || null;
    if (FE && FE.setSelectedStep) FE.setSelectedStep(next);
    if (window.AM2WDSidebar && window.AM2WDSidebar.renderSidebar && next) {
      window.AM2WDSidebar.renderSidebar(view, next);
    } else if (window.AM2WDSidebar && window.AM2WDSidebar.clearSidebar) {
      window.AM2WDSidebar.clearSidebar(view);
    }
    render();
  }

  function emitChanged() {
    const FE = window.AM2FlowEditorState;
    if (FE && FE.mutateWizard) {
      const defn = defFromGraph(view.draft, view.entry_step_id, view.edges);
      FE.mutateWizard(function (wd) {
        const next = defn;
        Object.keys(wd || {}).forEach(function (k) {
          try {
            delete wd[k];
          } catch (e) {
          }
        });
        Object.keys(next || {}).forEach(function (k) {
          wd[k] = next[k];
        });
      });
    }
    try {
      window.dispatchEvent(new CustomEvent("am2:wd:changed", { detail: {} }));
    } catch (e) {
      // ignore
    }
  }

  function setValidation(ok, localItems, serverItems) {
    view.validation = {
      ok: typeof ok === "boolean" ? ok : null,
      local: Array.isArray(localItems) ? localItems.slice() : [],
      server: Array.isArray(serverItems) ? serverItems.slice() : [],
    };
    renderValidation();
  }

  function pushLocalValidation(msgText) {
    const next = view.validation.local.slice();
    next.push(String(msgText || ""));
    setValidation(false, next, view.validation.server);
  }


  function extractServerMessages(data) {
    try {
      return [JSON.stringify(data, null, 2)];
    } catch (e) {
      return [String(data || "")];
    }
  }


  function removeStep(stepId) {
    if (!canRemove(stepId)) return;
    view.draft = view.draft.filter((x) => x !== stepId);
    if (view.selected === stepId) setSelected(null);
    emitChanged();
    render();
  }

  function addStep(stepId) {
    const sid = String(stepId || "");
    if (!sid) return;
    if (view.draft.includes(sid)) {
      pushLocalValidation("Step already present: " + sid);
      return;
    }

    let insertAt = view.draft.length;
    const sel = view.selected;
    if (sel && view.draft.includes(sel)) {
      insertAt = idxOf(sel) + 1;
    } else {
      const last = idxOf("processing");
      insertAt = last >= 0 ? last : view.draft.length;
    }

    insertAt = clampDropIndex(insertAt);

    const next = view.draft.slice();
    next.splice(insertAt, 0, sid);
    view.draft = next;
    normalizeEdges();
    emitChanged();
    render();
  }

  function moveStep(dragId, beforeId) {
    const from = idxOf(dragId);
    if (from < 0) return;
    if (isPinned(dragId)) return;

    const filtered = view.draft.filter((x) => x !== dragId);

    let to = filtered.length;
    if (beforeId) {
      const bi = filtered.indexOf(beforeId);
      to = bi >= 0 ? bi : filtered.length;
    }

    to = clampDropIndex(to);

    filtered.splice(to, 0, dragId);
    view.draft = filtered;
    normalizeEdges();
    emitChanged();
    render();
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
    view.palette = Array.isArray(items) ? items : [];
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
      render();
    }
    return !!(ok1 && ok2);
  }

  async function validateDraft() {
    renderError(null, false);
    setValidation(null, [], []);
    const payload = {
      definition: defFromGraph(view.draft, view.entry_step_id, view.edges),
    };
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
    return true;
  }

  async function saveDraft() {
    if (!(await validateDraft())) return false;
    const payload = {
      definition: defFromGraph(view.draft, view.entry_step_id, view.edges),
    };
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
  }

  function renderStepRow(stepId, idx) {
    const row = el("div", "wdRow");
    row.dataset.stepId = stepId;

    const kind = kindOf(stepId);
    const pinned = pinnedOf(stepId);
    if (kind === "mandatory") row.classList.add("kind-mandatory");
    if (kind === "optional") row.classList.add("kind-optional");
    if (kind === "conditional") row.classList.add("kind-conditional");
    if (pinned === "first") row.classList.add("is-pinned-first");
    if (pinned === "last") row.classList.add("is-pinned-last");
    if (isPinned(stepId)) row.classList.add("is-locked");
    if (view.selected === stepId) row.classList.add("is-selected");

    const orderCell = el("div", "wdCellOrder");
    const handle = el("span", "wdDragHandle");
    handle.appendChild(svgIcon("grip", "wdSvg wdGrip", "Drag"));
    handle.title = isPinned(stepId) ? "Locked" : "Drag to reorder";

    if (!isPinned(stepId)) {
      handle.draggable = true;
      handle.addEventListener("dragstart", (e) => {
        view.dragId = stepId;
        view.dropBeforeId = stepId;
        e.dataTransfer.effectAllowed = "move";
        dropHint.classList.add("is-visible");
      });
    } else {
      handle.classList.add("is-disabled");
    }

    orderCell.appendChild(handle);
    orderCell.appendChild(text("span", "wdOrderNum", String(idx + 1)));

    const idCell = text("div", "wdCellId", stepId);

    const typeCell = el("div", "wdCellType");
    const badge = el("span", "wdTypeBadge");
    badge.dataset.kind = kind;
    badge.appendChild(el("span", "wdBadgeIcon"));
    badge.appendChild(text("span", "wdBadgeText", kind));
    typeCell.appendChild(badge);

    const reqCell = el("div", "wdCellReq");
    const req = el("span", "wdReqIcon");
    if (isPinned(stepId)) {
      req.appendChild(svgIcon("lock", "wdSvg", "Locked"));
    } else if (isMandatory(stepId)) {
      req.appendChild(svgIcon("required", "wdSvg", "Required"));
    }
    reqCell.appendChild(req);

    const actCell = el("div", "wdCellActions");
    if (!isPinned(stepId) && canRemove(stepId)) {
      const rm = el("button", "wdIconBtn wdDeleteBtn");
      rm.type = "button";
      rm.setAttribute("aria-label", "Delete step");
      rm.title = "Delete";
      rm.appendChild(svgIcon("trash", "wdSvg", "Delete"));
      rm.appendChild(text("span", "srOnly", "Delete"));
      rm.addEventListener("click", (e) => {
        e.stopPropagation();
        removeStep(stepId);
      });
      actCell.appendChild(rm);
    } else {
      actCell.appendChild(el("span", "wdActionsPlaceholder"));
    }

    row.appendChild(orderCell);
    row.appendChild(idCell);
    row.appendChild(typeCell);
    row.appendChild(reqCell);
    row.appendChild(actCell);

    row.addEventListener("click", () => setSelected(stepId));
    row.addEventListener("dragover", (e) => {
      if (!view.dragId) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      view.dropBeforeId = stepId;
    });

    row.addEventListener("drop", (e) => {
      if (!view.dragId) return;
      e.preventDefault();
      const dragId = view.dragId;
      const beforeId = view.dropBeforeId;
      view.dragId = null;
      view.dropBeforeId = null;
      dropHint.classList.remove("is-visible");
      moveStep(dragId, beforeId);
    });

    row.addEventListener("dragend", () => {
      view.dragId = null;
      view.dropBeforeId = null;
      dropHint.classList.remove("is-visible");
    });

    return row;
  }

  function paletteButton(sid) {
    const already = view.draft.includes(sid);

    const add = el("button", "btn wdPaletteAdd");
    add.type = "button";

    if (already) {
      add.classList.add("is-added");
      add.disabled = true;
      add.appendChild(svgIcon("check", "wdSvg", "Added"));
      add.appendChild(text("span", "wdPaletteAddText", "Added"));
      return add;
    }

    add.textContent = "+ Add";
    add.addEventListener("click", () => addStep(sid));
    return add;
  }

  function renderPaletteGroup(titleText, kind, items) {
    const g = el("div", "wdPaletteGroup");
    if (kind === "mandatory") g.classList.add("kind-mandatory");
    if (kind === "optional") g.classList.add("kind-optional");
    if (kind === "conditional") g.classList.add("kind-conditional");

    g.appendChild(text("div", "wdPaletteGroupTitle", titleText));
    items.forEach((it) => {
      const sid = String(it.step_id || "");
      if (!sid) return;
      if (!view.showOptional && kind !== "mandatory") return;

      const item = el("div", "wdPaletteItem");
      if (kind === "mandatory") item.classList.add("kind-mandatory");
      if (kind === "optional") item.classList.add("kind-optional");
      if (kind === "conditional") item.classList.add("kind-conditional");

      item.appendChild(text("div", "wdPaletteItemId", sid));
      item.appendChild(paletteButton(sid));
      g.appendChild(item);
    });
    return g;
  }

  function validationGroup(titleText, items, groupClass) {
    const wrap = el("div", "wdValidationGroup");
    if (groupClass) wrap.classList.add(groupClass);
    wrap.appendChild(text("div", "wdValidationGroupTitle", titleText));

    if (!items.length) {
      wrap.appendChild(text("div", "wdValidationItem", "None"));
      return wrap;
    }

    items.forEach((s) => {
      wrap.appendChild(text("div", "wdValidationItem", s));
    });
    return wrap;
  }

  function renderValidation() {
    clear(validationList);
    validation.classList.remove("is-ok");
    validation.classList.remove("is-error");

    const ok = view.validation.ok;
    const localItems = view.validation.local;
    const serverItems = view.validation.server;
    const total = localItems.length + serverItems.length;

    validationClear.disabled = localItems.length === 0;

    if (ok === true && total === 0) {
      validation.classList.add("is-ok");
      validationCount.textContent = "OK";
      const okItem = el("div", "wdValidationItem wdValidationOk");
      okItem.appendChild(svgIcon("check", "wdSvg", "OK"));
      okItem.appendChild(text("span", "wdValidationOkText", "No validation errors."));
      validationList.appendChild(okItem);
      return;
    }

    if (total) {
      validation.classList.add("is-error");
      validationCount.textContent = String(total);
      validationList.appendChild(
        validationGroup("Local UI Messages", localItems, "is-local")
      );
      validationList.appendChild(
        validationGroup("Server Validation Messages", serverItems, "is-server")
      );
      return;
    }

    validationCount.textContent = "";
  }

  function render() {
    refreshFromFlowState();
    syncTextarea();
    btnRemove.disabled = !view.selected || !canRemove(view.selected);
    btnUp.disabled = !view.selected || isPinned(view.selected);
    btnDown.disabled = !view.selected || isPinned(view.selected);

    clear(body);
    view.draft.forEach((sid, idx) => {
      body.appendChild(renderStepRow(sid, idx));
    });

    clear(paletteGroups);
    const q = String(search.value || "").toLowerCase();
    const filtered = view.palette
      .filter((it) => it && it.step_id)
      .filter((it) => String(it.step_id).toLowerCase().includes(q));

    const mandatory = filtered.filter((it) => String(it.kind) === "mandatory");
    const optional = filtered.filter((it) => String(it.kind) === "optional");
    const conditional = filtered.filter((it) => String(it.kind) === "conditional");

    paletteGroups.appendChild(
      renderPaletteGroup("Mandatory", "mandatory", mandatory)
    );
    paletteGroups.appendChild(renderPaletteGroup("Optional", "optional", optional));
    paletteGroups.appendChild(
      renderPaletteGroup("Conditional", "conditional", conditional)
    );
  }

  function normPath(s) {
    const raw = String(s || "").trim();
    if (raw.startsWith("$.")) return raw.slice(2);
    return raw;
  }

  function condSummary(when) {
    if (when === null || when === undefined) return "Always";
    if (typeof when === "boolean") return when ? "True" : "False";
    if (!when || typeof when !== "object") return "Custom";

    const op = when.op ? String(when.op) : "";
    if (op === "eq" || op === "ne") {
      const p = when.path ? String(when.path) : "";
      const v = when.value;
      return op + " " + p + " = " + String(v);
    }
    if (op === "exists" || op === "truthy") {
      return op + " " + String(when.path || "");
    }
    if (op === "not" && when.cond && typeof when.cond === "object") {
      const c = when.cond;
      const cop = c.op ? String(c.op) : "";
      if (cop === "truthy") return "falsy " + String(c.path || "");
      if (cop === "exists") return "not_exists " + String(c.path || "");
    }
    if (op === "or" && Array.isArray(when.conds)) {
      const conds = when.conds;
      const eqs = conds.filter((c) => c && c.op === "eq" && c.path);
      if (eqs.length === conds.length && eqs.length) {
        const path = String(eqs[0].path);
        const vals = eqs.map((c) => String(c.value));
        return "in " + path + " [" + vals.join(", " ) + "]";
      }
    }
    return "Custom";
  }

  function parseWhenToUI(when) {
    if (when === null || when === undefined) {
      return {
        always: true,
        op: "eq",
        path: "",
        valueType: "text",
        valueText: "",
        inList: [],
      };
    }
    if (!when || typeof when !== "object") {
      return {
        always: false,
        op: "eq",
        path: "",
        valueType: "text",
        valueText: "",
        inList: [],
      };
    }
    const op = when.op ? String(when.op) : "";
    if (op === "eq" || op === "ne") {
      const v = when.value;
      if (typeof v === "boolean") {
        return {
          always: false,
          op: op,
          path: String(when.path || ""),
          valueType: v ? "true" : "false",
          valueText: "",
          inList: [],
        };
      }
      return {
        always: false,
        op: op,
        path: String(when.path || ""),
        valueType: "text",
        valueText: v === undefined || v === null ? "" : String(v),
        inList: [],
      };
    }
    if (op === "exists" || op === "truthy") {
      return {
        always: false,
        op: op,
        path: String(when.path || ""),
        valueType: "text",
        valueText: "",
        inList: [],
      };
    }
    if (op === "not" && when.cond && typeof when.cond === "object") {
      const c = when.cond;
      const cop = c.op ? String(c.op) : "";
      if (cop === "truthy") {
        return {
          always: false,
          op: "falsy",
          path: String(c.path || ""),
          valueType: "text",
          valueText: "",
          inList: [],
        };
      }
      if (cop === "exists") {
        return {
          always: false,
          op: "not_exists",
          path: String(c.path || ""),
          valueType: "text",
          valueText: "",
          inList: [],
        };
      }
    }
    if (op === "or" && Array.isArray(when.conds)) {
      const conds = when.conds;
      const eqs = conds.filter((c) => c && c.op === "eq" && c.path);
      if (eqs.length === conds.length && eqs.length) {
        const path = String(eqs[0].path);
        const vals = eqs.map((c) => String(c.value));
        return {
          always: false,
          op: "in",
          path: path,
          valueType: "text",
          valueText: "",
          inList: vals,
        };
      }
    }
    return {
      always: false,
      op: "eq",
      path: "",
      valueType: "text",
      valueText: "",
      inList: [],
    };
  }

  function buildWhenFromUI(d) {
    if (d.always) return null;
    const op = String(d.op || "");
    const path = normPath(d.path);
    if (!path) return null;

    if (op === "eq" || op === "ne") {
      let v = d.valueText;
      if (d.valueType === "true") v = true;
      if (d.valueType === "false") v = false;
      return { op: op, path: path, value: v };
    }
    if (op === "exists" || op === "truthy") {
      return { op: op, path: path };
    }
    if (op === "falsy") {
      return { op: "not", cond: { op: "truthy", path: path } };
    }
    if (op === "not_exists") {
      return { op: "not", cond: { op: "exists", path: path } };
    }
    if (op === "in") {
      const items = Array.isArray(d.inList) ? d.inList : [];
      return {
        op: "or",
        conds: items
          .filter((x) => String(x || "").trim())
          .map((x) => ({ op: "eq", path: path, value: String(x) })),
      };
    }
    return null;
  }

  function normalizeEdges() {
    const fn =
      window.AM2WDEdgesIntegrity && window.AM2WDEdgesIntegrity.normalizeEdges
        ? window.AM2WDEdgesIntegrity.normalizeEdges
        : null;
    if (fn) {
      view.edges = fn(view.draft, view.edges);
    }
  }

  function ensureEntryValid() {
    if (!view.entry_step_id || view.draft.indexOf(view.entry_step_id) < 0) {
      view.entry_step_id = view.draft[0] || null;
    }
  }

  function renderTransitions() {
    if (!transitionsPanel) return;
    clear(transitionsPanel);
    ensureEntryValid();

    const header = el("div", "flowTransHeader");
    header.appendChild(text("div", "flowTransTitle", "Transitions"));

    const entryWrap = el("div", "flowTransEntry");
    entryWrap.appendChild(text("label", "flowTransLabel", "Entry"));
    const entrySel = el("select", "flowTransSelect");
    view.draft.forEach((sid) => {
      const opt = el("option", null);
      opt.value = sid;
      opt.textContent = sid;
      if (sid === view.entry_step_id) opt.selected = true;
      entrySel.appendChild(opt);
    });
    entrySel.addEventListener("change", () => {
      view.entry_step_id = entrySel.value || null;
    emitChanged();
    });
    entryWrap.appendChild(entrySel);
    header.appendChild(entryWrap);

    const addWrap = el("div", "flowTransAdd");
    const fromSel = el("select", "flowTransSelect");
    const toSel = el("select", "flowTransSelect");
    const priInp = el("input", "flowTransPri");
    priInp.type = "number";
    priInp.min = "0";
    priInp.step = "1";
    priInp.value = "0";
    view.draft.forEach((sid) => {
      const a = el("option", null);
      a.value = sid;
      a.textContent = sid;
      fromSel.appendChild(a);
      const b = el("option", null);
      b.value = sid;
      b.textContent = sid;
      toSel.appendChild(b);
    });
    if (view.selected && view.draft.indexOf(view.selected) >= 0) fromSel.value = view.selected;

    addWrap.appendChild(text("label", "flowTransLabel", "From"));
    addWrap.appendChild(fromSel);
    addWrap.appendChild(text("label", "flowTransLabel", "To"));
    addWrap.appendChild(toSel);
    addWrap.appendChild(text("label", "flowTransLabel", "Priority"));
    addWrap.appendChild(priInp);

    const btnAddEdge = text("button", "btn", "Add transition");
    btnAddEdge.type = "button";
    btnAddEdge.addEventListener("click", () => {
      const frm = fromSel.value || "";
      const to = toSel.value || "";
      const prio = parseInt(String(priInp.value || "0"), 10);
      if (!frm || !to) return;
      if (frm === to) {
        pushLocalValidation("Self-loop transitions are not allowed.");
        return;
      }
      if (view.draft.indexOf(frm) < 0 || view.draft.indexOf(to) < 0) return;
      view.edges = view.edges.concat([
        {
          from_step_id: frm,
          to_step_id: to,
          priority: Number.isFinite(prio) ? prio : 0,
          when: null,
        },
      ]);
      normalizeEdges();
    emitChanged();
      renderTransitions();
    });
    addWrap.appendChild(btnAddEdge);

    transitionsPanel.appendChild(header);
    transitionsPanel.appendChild(addWrap);

    const table = el("div", "flowTransTable");
    const head = el("div", "flowTransRow flowTransHead");
    head.appendChild(text("div", "flowTransCellPri", "Pri"));
    head.appendChild(text("div", "flowTransCellFrom", "From"));
    head.appendChild(text("div", "flowTransCellTo", "To"));
    head.appendChild(text("div", "flowTransCellCond", "Condition"));
    head.appendChild(text("div", "flowTransCellAct", "Actions"));
    table.appendChild(head);

    normalizeEdges();

    function moveEdge(idx, dir) {
      const e = view.edges[idx];
      if (!e) return;
      const frm = e.from_step_id;
      const swap = idx + dir;
      const e2 = view.edges[swap];
      if (!e2 || e2.from_step_id !== frm) return;
      const next = view.edges.slice();
      next[idx] = e2;
      next[swap] = e;
      view.edges = next;
    emitChanged();
      renderTransitions();
    }

    view.edges.forEach((e, idx) => {
      const row = el("div", "flowTransRow");
      row.appendChild(text("div", "flowTransCellPri", String(e.priority || 0)));
      row.appendChild(text("div", "flowTransCellFrom", e.from_step_id));
      row.appendChild(text("div", "flowTransCellTo", e.to_step_id));

      const condCell = el("div", "flowTransCellCond");
      const condBtn = text("button", "flowTransCondBtn", condSummary(e.when));
      condBtn.type = "button";
      condBtn.addEventListener("click", () => {
        view.editingEdgeIdx = view.editingEdgeIdx === idx ? null : idx;
        renderTransitions();
      });
      condCell.appendChild(condBtn);
      row.appendChild(condCell);

      const act = el("div", "flowTransCellAct");
      const btnUpEdge = text("button", "btn", "Up");
      const btnDownEdge = text("button", "btn", "Down");
      const btnDel = text("button", "btn", "Delete");
      btnUpEdge.type = "button";
      btnDownEdge.type = "button";
      btnDel.type = "button";

      btnUpEdge.addEventListener("click", () => moveEdge(idx, -1));
      btnDownEdge.addEventListener("click", () => moveEdge(idx, +1));
      btnDel.addEventListener("click", () => {
        view.edges = view.edges.filter((_, i) => i !== idx);
        normalizeEdges();
        view.editingEdgeIdx = null;
    emitChanged();
        renderTransitions();
      });
      act.appendChild(btnUpEdge);
      act.appendChild(btnDownEdge);
      act.appendChild(btnDel);
      row.appendChild(act);

      table.appendChild(row);

      if (view.editingEdgeIdx === idx) {
        const ed = el("div", "flowTransEditor");
        const uiD = parseWhenToUI(e.when);

        const alwaysWrap = el("label", "flowTransAlways");
        const always = el("input", null);
        always.type = "checkbox";
        always.checked = !!uiD.always;
        alwaysWrap.appendChild(always);
        alwaysWrap.appendChild(text("span", null, "Always"));

        const opSel = el("select", "flowTransSelect");
        ["eq", "ne", "truthy", "falsy", "exists", "not_exists", "in"].forEach((k) => {
          const o = el("option", null);
          o.value = k;
          o.textContent = k;
          if (k === uiD.op) o.selected = true;
          opSel.appendChild(o);
        });

        const dlId = "flowPathDL";
        let dl = document.getElementById(dlId);
        if (!dl) {
          dl = el("datalist", null);
          dl.id = dlId;
          (view.draft || []).forEach((sid) => {
            const o = el("option", null);
            o.value = "$.inputs." + sid + ".<field>";
            dl.appendChild(o);
          });
          const o2 = el("option", null);
          o2.value = "$.view.<field>";
          dl.appendChild(o2);
          document.body.appendChild(dl);
        }

        const pathInp = el("input", "flowTransPath");
        pathInp.type = "text";
        pathInp.setAttribute("list", dlId);
        pathInp.value = uiD.path ? "$." + uiD.path : "";

        const valWrap = el("div", "flowTransVal");
        const valType = el("select", "flowTransSelect");
        ["text", "true", "false"].forEach((k) => {
          const o = el("option", null);
          o.value = k;
          o.textContent = k;
          if (k === uiD.valueType) o.selected = true;
          valType.appendChild(o);
        });
        const valText = el("input", "flowTransValText");
        valText.type = "text";
        valText.value = uiD.valueText || "";

        const inWrap = el("div", "flowTransIn");
        const inList = el("div", "flowTransInList");
        const btnAddIn = text("button", "btn", "Add item");
        btnAddIn.type = "button";

        function renderInList(items) {
          clear(inList);
          items.forEach((v, i) => {
            const r = el("div", "flowTransInRow");
            const t = el("input", "flowTransInText");
            t.type = "text";
            t.value = String(v || "");
            t.addEventListener("input", () => {
              items[i] = t.value;
            });
            const del = text("button", "btn", "Remove");
            del.type = "button";
            del.addEventListener("click", () => {
              items.splice(i, 1);
              renderInList(items);
            });
            r.appendChild(t);
            r.appendChild(del);
            inList.appendChild(r);
          });
        }

        const inItems = (uiD.inList || []).slice();
        renderInList(inItems);
        btnAddIn.addEventListener("click", () => {
          inItems.push("");
          renderInList(inItems);
        });
        inWrap.appendChild(inList);
        inWrap.appendChild(btnAddIn);

        const btnApply = text("button", "btn", "Apply");
        btnApply.type = "button";
        btnApply.addEventListener("click", () => {
          const d = {
            always: !!always.checked,
            op: opSel.value,
            path: pathInp.value,
            valueType: valType.value,
            valueText: valText.value,
            inList: inItems,
          };
          const when = buildWhenFromUI(d);
          const next = view.edges.slice();
          next[idx] = { from_step_id: e.from_step_id, to_step_id: e.to_step_id, when: when };
          view.edges = next;
    emitChanged();
          view.editingEdgeIdx = null;
          renderTransitions();
        });

        function applyVisibility() {
          const dis = !!always.checked;
          opSel.disabled = dis;
          pathInp.disabled = dis;

          const opv = opSel.value;
          const needsValue = opv === "eq" || opv === "ne";
          const needsIn = opv === "in";
          valWrap.classList.toggle("is-hidden", dis || !needsValue);
          inWrap.classList.toggle("is-hidden", dis || !needsIn);

          valType.disabled = dis || !needsValue;
          valText.disabled = dis || !needsValue || valType.value !== "text";
        }

        always.addEventListener("change", applyVisibility);
        opSel.addEventListener("change", applyVisibility);
        valType.addEventListener("change", applyVisibility);
        applyVisibility();

        ed.appendChild(alwaysWrap);
        ed.appendChild(text("div", "flowTransLabel", "op"));
        ed.appendChild(opSel);
        ed.appendChild(text("div", "flowTransLabel", "path"));
        ed.appendChild(pathInp);

        valWrap.appendChild(text("div", "flowTransLabel", "value"));
        valWrap.appendChild(valType);
        valWrap.appendChild(valText);
        ed.appendChild(valWrap);
        ed.appendChild(inWrap);
        ed.appendChild(btnApply);

        table.appendChild(ed);
      }
    });

    transitionsPanel.appendChild(table);
  }


  search.addEventListener("input", () => render());

  optToggle.addEventListener("change", () => {
    view.showOptional = !!optToggle.checked;
    render();
  });

  validationClear.addEventListener("click", () => {
    setValidation(false, [], view.validation.server);
  });

  btnRemove.addEventListener("click", () => {
    const sid = view.selected;
    if (!sid) return;
    if (!canRemove(sid)) {
      pushLocalValidation("Cannot remove locked or mandatory step: " + sid);
      return;
    }
    removeStep(sid);
  });

  btnUp.addEventListener("click", () => {
    const sid = view.selected;
    if (!sid) return;
    if (isPinned(sid)) return;
    const from = idxOf(sid);
    if (from <= 0) return;
    const target = view.draft[from - 1];
    moveStep(sid, target);
  });

  btnDown.addEventListener("click", () => {
    const sid = view.selected;
    if (!sid) return;
    if (isPinned(sid)) return;
    const from = idxOf(sid);
    if (from < 0 || from >= view.draft.length - 1) return;
    const target = view.draft[from + 2] || null;
    moveStep(sid, target);
  });

  btnAdd.addEventListener("click", () => {
    const q = String(search.value || "").toLowerCase();
    const matches = view.palette
      .filter((it) => it && it.step_id)
      .filter((it) => String(it.step_id).toLowerCase().includes(q));

    if (matches.length !== 1) {
      pushLocalValidation(
        "Add Step requires search to match exactly one palette item."
      );
      return;
    }
    addStep(matches[0].step_id);
  });

  ui.reload && ui.reload.addEventListener("click", reloadAll);
  ui.validate && ui.validate.addEventListener("click", validateDraft);
  ui.save && ui.save.addEventListener("click", saveDraft);
  ui.reset && ui.reset.addEventListener("click", resetDefinition);

  window.AM2WizardDefinitionEditor = {
    reloadAll: reloadAll,
    validateDraft: validateDraft,
    saveDraft: saveDraft,
    resetDefinition: resetDefinition,
  };

  

  const FE = window.AM2FlowEditorState;
  if (FE && FE.bindWizardEditorBridge) {
    FE.bindWizardEditorBridge({ renderRequested: render });
  }

reloadAll();
})();