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

  function svgIcon(name, cls, title) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "16");
    svg.setAttribute("height", "16");
    svg.setAttribute("aria-hidden", "true");
    if (cls) svg.setAttribute("class", cls);

    if (title) {
      const t = document.createElementNS(ns, "title");
      t.textContent = String(title);
      svg.appendChild(t);
    }

    const p = document.createElementNS(ns, "path");

    if (name === "lock") {
      p.setAttribute(
        "d",
        "M17 10V8a5 5 0 0 0-10 0v2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2h-1Zm-8 0V8a3 3 0 0 1 6 0v2H9Z"
      );
    } else if (name === "trash") {
      p.setAttribute(
        "d",
        "M9 3h6l1 2h4v2h-2l-1 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L6 7H4V5h4l1-2Zm0 4 1 14h4l1-14H9Zm2 2h2v10h-2V9Z"
      );
    } else if (name === "check") {
      p.setAttribute("d", "M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z");
    } else if (name === "search") {
      p.setAttribute(
        "d",
        "M10 2a8 8 0 1 0 4.9 14.3l4.4 4.4 1.4-1.4-4.4-4.4A8 8 0 0 0 10 2Zm0 2a6 6 0 1 1 0 12 6 6 0 0 1 0-12Z"
      );
    } else if (name === "grip") {
      p.setAttribute(
        "d",
        "M9 5a1 1 0 1 1-2 0 1 1 0 0 1 2 0Zm0 7a1 1 0 1 1-2 0 1 1 0 0 1 2 0Zm0 7a1 1 0 1 1-2 0 1 1 0 0 1 2 0Zm8-14a1 1 0 1 1-2 0 1 1 0 0 1 2 0Zm0 7a1 1 0 1 1-2 0 1 1 0 0 1 2 0Zm0 7a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z"
      );
    } else if (name === "required") {
      p.setAttribute(
        "d",
        "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm1 5v6h-2V7h2Zm0 8v2h-2v-2h2Z"
      );
    }

    svg.appendChild(p);
    return svg;
  }

  function stableGraph(defn) {
    const root = defn && typeof defn === "object" ? defn : {};
    const vAny = root.version;
    const version = typeof vAny === "number" ? vAny : 1;

    if (version === 2 && root.graph && typeof root.graph === "object") {
      const g = root.graph;
      const entry = typeof g.entry_step_id === "string" ? g.entry_step_id : null;

      const nodesAny = Array.isArray(g.nodes) ? g.nodes : [];
      const nodes = nodesAny
        .map((n) => (n && typeof n.step_id === "string" ? n.step_id : ""))
        .filter((x) => x);

      const edgesAny = Array.isArray(g.edges) ? g.edges : [];
      const edges = edgesAny
        .map((e) => (e && typeof e === "object" ? e : null))
        .filter((e) => e)
        .map((e) => ({
          from_step_id: typeof e.from_step_id === "string" ? e.from_step_id : "",
          to_step_id: typeof e.to_step_id === "string" ? e.to_step_id : "",
          when: e.when === undefined ? null : e.when,
        }))
        .filter((e) => e.from_step_id && e.to_step_id);

      return { version: 2, entry: entry || (nodes[0] || null), nodes: nodes, edges: edges };
    }

    const steps = root && Array.isArray(root.steps) ? root.steps : [];
    const nodes = steps
      .map((x) => (x && typeof x.step_id === "string" ? x.step_id : ""))
      .filter((x) => x);

    const edges = [];
    for (let i = 0; i < nodes.length - 1; i += 1) {
      edges.push({ from_step_id: nodes[i], to_step_id: nodes[i + 1], when: null });
    }
    return { version: 1, entry: nodes[0] || null, nodes: nodes, edges: edges };
  }

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
          when: e.when === undefined ? null : e.when,
        })),
      },
    };
  }

  function defFromSteps(stepIds) {
    return defFromGraph(stepIds || [], state.entry_step_id, state.edges || []);
  }

  const state = {
    loaded: [],
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

  const layout = el("div", "wdLayout");
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
  layout.appendChild(rightCol);

  ui.ta.parentNode.insertBefore(layout, ui.ta);
  ui.ta.classList.add("wdHidden");


  // Unified right-side panel: Step Details (existing) + Transitions
  const flowRight = document.querySelector(".flowRight");
  const stepPanel = document.getElementById("flowStepPanel");
  const transitionsPanel = el("div", "flowTransPanel");

  function buildFlowRightTabs() {
    if (!flowRight || !stepPanel) return;

    const tabBar = el("div", "flowRightTabs");
    const btnDetails = text("button", "flowRightTab", "Step Details");
    const btnTrans = text("button", "flowRightTab", "Transitions");
    btnDetails.type = "button";
    btnTrans.type = "button";

    const panelDetails = el("div", "flowRightPanel");
    panelDetails.dataset.tab = "details";
    const panelTrans = el("div", "flowRightPanel");
    panelTrans.dataset.tab = "transitions";

    panelDetails.appendChild(stepPanel);
    panelTrans.appendChild(transitionsPanel);

    tabBar.appendChild(btnDetails);
    tabBar.appendChild(btnTrans);

    clear(flowRight);
    flowRight.appendChild(tabBar);
    flowRight.appendChild(panelDetails);
    flowRight.appendChild(panelTrans);

    function setTab(name) {
      state.rightTab = name;
      btnDetails.classList.toggle("is-active", name === "details");
      btnTrans.classList.toggle("is-active", name === "transitions");
      panelDetails.classList.toggle("is-active", name === "details");
      panelTrans.classList.toggle("is-active", name === "transitions");
      if (name === "transitions") renderTransitions();
    }

    btnDetails.addEventListener("click", () => setTab("details"));
    btnTrans.addEventListener("click", () => setTab("transitions"));

    setTab(state.rightTab || "details");
  }

  buildFlowRightTabs();

  function setupRawErrorPanel() {
    if (!ui.err || !ui.err.parentNode) return;
    const parent = ui.err.parentNode;

    const wrap = el("div", "wdErrWrap");
    const bar = el("div", "wdErrBar");
    const title = text("div", "wdErrTitle", "Raw Error");
    const toggle = text("button", "btn wdErrToggle", "Details");
    toggle.type = "button";

    bar.appendChild(title);
    bar.appendChild(toggle);
    wrap.appendChild(bar);

    parent.insertBefore(wrap, ui.err);
    wrap.appendChild(ui.err);

    ui.err.classList.add("wdRawError");
    ui.err.classList.add("is-collapsed");

    toggle.addEventListener("click", () => {
      setRawErrorVisible(!state.showRawError);
    });

    state.showRawError = false;
    state.hasErrorDetails = false;
    setRawErrorVisible(false);
  }

  function setRawErrorVisible(on) {
    state.showRawError = !!on;
    if (!ui.err) return;
    ui.err.classList.toggle("is-collapsed", !state.showRawError);

    const btn = document.querySelector(".wdErrToggle");
    if (btn) btn.textContent = state.showRawError ? "Hide Details" : "Details";
  }

  function renderError(data, collapseByDefault) {
    H.renderError(ui.err, data);
    state.hasErrorDetails = !!data;
    if (!data) {
      setRawErrorVisible(false);
      return;
    }
    setRawErrorVisible(!collapseByDefault);
  }


  setupRawErrorPanel();

  function isDirty() {
    return JSON.stringify(state.loaded) !== JSON.stringify(state.draft);
  }

  function confirmIfDirty(actionName) {
    if (!isDirty()) return true;
    return window.confirm("Unsaved changes. Continue: " + actionName + "?");
  }

  function kindOf(stepId) {
    const item = state.palette.find((x) => x && x.step_id === stepId);
    return item && item.kind ? String(item.kind) : "optional";
  }

  function pinnedOf(stepId) {
    const item = state.palette.find((x) => x && x.step_id === stepId);
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
    return state.draft.indexOf(stepId);
  }

  function clampDropIndex(idx) {
    const first = idxOf("select_authors");
    const last = idxOf("processing");
    const min = first >= 0 ? first + 1 : 0;
    const max = last >= 0 ? last : state.draft.length;
    if (idx < min) return min;
    if (idx > max) return max;
    return idx;
  }

  function syncTextarea() {
    ui.ta.value = H.pretty(defFromGraph(state.draft, state.entry_step_id, state.edges));
  }

  function setSelected(stepId) {
    state.selected = stepId || null;
    try {
      window.dispatchEvent(
        new CustomEvent("am2:wd:selected", {
          detail: { step_id: state.selected },
        })
      );
    } catch (e) {
      // ignore
    }
    render();
  }

  function emitChanged() {
    try {
      window.dispatchEvent(new CustomEvent("am2:wd:changed", { detail: {} }));
    } catch (e) {
      // ignore
    }
  }

  function setValidation(ok, localItems, serverItems) {
    state.validation = {
      ok: typeof ok === "boolean" ? ok : null,
      local: Array.isArray(localItems) ? localItems.slice() : [],
      server: Array.isArray(serverItems) ? serverItems.slice() : [],
    };
    renderValidation();
  }

  function pushLocalValidation(msgText) {
    const next = state.validation.local.slice();
    next.push(String(msgText || ""));
    setValidation(false, next, state.validation.server);
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
    state.draft = state.draft.filter((x) => x !== stepId);
    if (state.selected === stepId) setSelected(null);
    syncTextarea();
    emitChanged();
    render();
  }

  function addStep(stepId) {
    const sid = String(stepId || "");
    if (!sid) return;
    if (state.draft.includes(sid)) {
      pushLocalValidation("Step already present: " + sid);
      return;
    }

    let insertAt = state.draft.length;
    const sel = state.selected;
    if (sel && state.draft.includes(sel)) {
      insertAt = idxOf(sel) + 1;
    } else {
      const last = idxOf("processing");
      insertAt = last >= 0 ? last : state.draft.length;
    }

    insertAt = clampDropIndex(insertAt);

    const next = state.draft.slice();
    next.splice(insertAt, 0, sid);
    state.draft = next;
    normalizeEdges();
    syncTextarea();
    emitChanged();
    render();
  }

  function moveStep(dragId, beforeId) {
    const from = idxOf(dragId);
    if (from < 0) return;
    if (isPinned(dragId)) return;

    const filtered = state.draft.filter((x) => x !== dragId);

    let to = filtered.length;
    if (beforeId) {
      const bi = filtered.indexOf(beforeId);
      to = bi >= 0 ? bi : filtered.length;
    }

    to = clampDropIndex(to);

    filtered.splice(to, 0, dragId);
    state.draft = filtered;
    normalizeEdges();
    syncTextarea();
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
    state.palette = Array.isArray(items) ? items : [];
    return true;
  }

  async function loadDefinition() {
    const out = await H.requestJSON("/import/ui/wizard-definition");
    if (!out.ok) {
      renderError(out.data, false);
      return false;
    }
    const defn = out.data && out.data.definition ? out.data.definition : {};
    const g = stableGraph(defn);

    state.loaded = g.nodes.slice();
    state.draft = g.nodes.slice();
    state.edges = Array.isArray(g.edges) ? g.edges.slice() : [];
    state.entry_step_id = g.entry || null;
    setSelected(null);

    normalizeEdges();

    ui.ta.value = H.pretty(defFromGraph(state.draft, state.entry_step_id, state.edges));
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
      definition: defFromGraph(state.draft, state.entry_step_id, state.edges),
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
    const g = stableGraph(defn);
    state.draft = g.nodes.slice();
    state.edges = g.edges.slice();
    normalizeEdges();
    state.entry_step_id = g.entry || null;
    ui.ta.value = H.pretty(defFromGraph(state.draft, state.entry_step_id, state.edges));
    setValidation(true, [], []);
    render();
    return true;
  }

  async function saveDraft() {
    if (!(await validateDraft())) return false;

    const payload = {
      definition: defFromGraph(state.draft, state.entry_step_id, state.edges),
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
    const g = stableGraph(defn);
    state.loaded = g.nodes.slice();
    state.draft = g.nodes.slice();
    state.edges = g.edges.slice();
    normalizeEdges();
    state.entry_step_id = g.entry || null;
    setSelected(null);
    ui.ta.value = H.pretty(defFromGraph(state.draft, state.entry_step_id, state.edges));
    await loadHistory();
    render();
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
    const g = stableGraph(defn);
    state.loaded = g.nodes.slice();
    state.draft = g.nodes.slice();
    state.edges = g.edges.slice();
    normalizeEdges();
    state.entry_step_id = g.entry || null;
    setSelected(null);
    ui.ta.value = H.pretty(defFromGraph(state.draft, state.entry_step_id, state.edges));
    await loadHistory();
    render();
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
    const g = stableGraph(defn);
    state.loaded = g.nodes.slice();
    state.draft = g.nodes.slice();
    state.edges = g.edges.slice();
    normalizeEdges();
    state.entry_step_id = g.entry || null;
    setSelected(null);
    ui.ta.value = H.pretty(defFromGraph(state.draft, state.entry_step_id, state.edges));
    await loadHistory();
    render();
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
    if (state.selected === stepId) row.classList.add("is-selected");

    const orderCell = el("div", "wdCellOrder");
    const handle = el("span", "wdDragHandle");
    handle.appendChild(svgIcon("grip", "wdSvg wdGrip", "Drag"));
    handle.title = isPinned(stepId) ? "Locked" : "Drag to reorder";

    if (!isPinned(stepId)) {
      handle.draggable = true;
      handle.addEventListener("dragstart", (e) => {
        state.dragId = stepId;
        state.dropBeforeId = stepId;
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
      if (!state.dragId) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      state.dropBeforeId = stepId;
    });

    row.addEventListener("drop", (e) => {
      if (!state.dragId) return;
      e.preventDefault();
      const dragId = state.dragId;
      const beforeId = state.dropBeforeId;
      state.dragId = null;
      state.dropBeforeId = null;
      dropHint.classList.remove("is-visible");
      moveStep(dragId, beforeId);
    });

    row.addEventListener("dragend", () => {
      state.dragId = null;
      state.dropBeforeId = null;
      dropHint.classList.remove("is-visible");
    });

    return row;
  }

  function paletteButton(sid) {
    const already = state.draft.includes(sid);

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
      if (!state.showOptional && kind !== "mandatory") return;

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

    const ok = state.validation.ok;
    const localItems = state.validation.local;
    const serverItems = state.validation.server;
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
    btnRemove.disabled = !state.selected || !canRemove(state.selected);
    btnUp.disabled = !state.selected || isPinned(state.selected);
    btnDown.disabled = !state.selected || isPinned(state.selected);

    clear(body);
    state.draft.forEach((sid, idx) => {
      body.appendChild(renderStepRow(sid, idx));
    });

    clear(paletteGroups);
    const q = String(search.value || "").toLowerCase();
    const filtered = state.palette
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
    const byFrom = {};
    (state.edges || []).forEach((e) => {
      if (!e || typeof e !== "object") return;
      const frm = typeof e.from_step_id === "string" ? e.from_step_id : "";
      const to = typeof e.to_step_id === "string" ? e.to_step_id : "";
      if (!frm || !to) return;
      if (!byFrom[frm]) byFrom[frm] = [];
      byFrom[frm].push({
        from_step_id: frm,
        to_step_id: to,
        when: e.when === undefined ? null : e.when,
      });
    });

    const out = [];
    (state.draft || []).forEach((sid) => {
      (byFrom[sid] || []).forEach((e) => out.push(e));
    });
    Object.keys(byFrom)
      .filter((k) => (state.draft || []).indexOf(k) < 0)
      .sort()
      .forEach((k) => {
        (byFrom[k] || []).forEach((e) => out.push(e));
      });
    state.edges = out;
  }

  function ensureEntryValid() {
    if (!state.entry_step_id || state.draft.indexOf(state.entry_step_id) < 0) {
      state.entry_step_id = state.draft[0] || null;
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
    state.draft.forEach((sid) => {
      const opt = el("option", null);
      opt.value = sid;
      opt.textContent = sid;
      if (sid === state.entry_step_id) opt.selected = true;
      entrySel.appendChild(opt);
    });
    entrySel.addEventListener("change", () => {
      state.entry_step_id = entrySel.value || null;
      syncTextarea();
      emitChanged();
    });
    entryWrap.appendChild(entrySel);
    header.appendChild(entryWrap);

    const addWrap = el("div", "flowTransAdd");
    const fromSel = el("select", "flowTransSelect");
    const toSel = el("select", "flowTransSelect");
    state.draft.forEach((sid) => {
      const a = el("option", null);
      a.value = sid;
      a.textContent = sid;
      fromSel.appendChild(a);
      const b = el("option", null);
      b.value = sid;
      b.textContent = sid;
      toSel.appendChild(b);
    });
    if (state.selected && state.draft.indexOf(state.selected) >= 0) fromSel.value = state.selected;

    addWrap.appendChild(text("label", "flowTransLabel", "From"));
    addWrap.appendChild(fromSel);
    addWrap.appendChild(text("label", "flowTransLabel", "To"));
    addWrap.appendChild(toSel);

    const btnAddEdge = text("button", "btn", "Add transition");
    btnAddEdge.type = "button";
    btnAddEdge.addEventListener("click", () => {
      const frm = fromSel.value || "";
      const to = toSel.value || "";
      if (!frm || !to) return;
      if (frm === to) {
        pushLocalValidation("Self-loop transitions are not allowed.");
        return;
      }
      if (state.draft.indexOf(frm) < 0 || state.draft.indexOf(to) < 0) return;
      state.edges = state.edges.concat([
        { from_step_id: frm, to_step_id: to, when: null },
      ]);
      normalizeEdges();
      syncTextarea();
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

    function priForEdgeAt(idx) {
      const e = state.edges[idx];
      if (!e) return 0;
      const frm = e.from_step_id;
      let n = 0;
      for (let i = 0; i <= idx; i += 1) {
        if (state.edges[i] && state.edges[i].from_step_id === frm) n += 1;
      }
      return n;
    }

    function moveEdge(idx, dir) {
      const e = state.edges[idx];
      if (!e) return;
      const frm = e.from_step_id;
      const swap = idx + dir;
      const e2 = state.edges[swap];
      if (!e2 || e2.from_step_id !== frm) return;
      const next = state.edges.slice();
      next[idx] = e2;
      next[swap] = e;
      state.edges = next;
      syncTextarea();
      emitChanged();
      renderTransitions();
    }

    state.edges.forEach((e, idx) => {
      const row = el("div", "flowTransRow");
      row.appendChild(text("div", "flowTransCellPri", String(priForEdgeAt(idx))));
      row.appendChild(text("div", "flowTransCellFrom", e.from_step_id));
      row.appendChild(text("div", "flowTransCellTo", e.to_step_id));

      const condCell = el("div", "flowTransCellCond");
      const condBtn = text("button", "flowTransCondBtn", condSummary(e.when));
      condBtn.type = "button";
      condBtn.addEventListener("click", () => {
        state.editingEdgeIdx = state.editingEdgeIdx === idx ? null : idx;
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
        state.edges = state.edges.filter((_, i) => i !== idx);
        normalizeEdges();
        state.editingEdgeIdx = null;
        syncTextarea();
        emitChanged();
        renderTransitions();
      });
      act.appendChild(btnUpEdge);
      act.appendChild(btnDownEdge);
      act.appendChild(btnDel);
      row.appendChild(act);

      table.appendChild(row);

      if (state.editingEdgeIdx === idx) {
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
          (state.draft || []).forEach((sid) => {
            const o = el("option", null);
            o.value = "$.inputs." + sid + ".<field>";
            dl.appendChild(o);
          });
          const o2 = el("option", null);
          o2.value = "$.state.<field>";
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
          const next = state.edges.slice();
          next[idx] = { from_step_id: e.from_step_id, to_step_id: e.to_step_id, when: when };
          state.edges = next;
          syncTextarea();
          emitChanged();
          state.editingEdgeIdx = null;
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
    state.showOptional = !!optToggle.checked;
    render();
  });

  validationClear.addEventListener("click", () => {
    setValidation(false, [], state.validation.server);
  });

  btnRemove.addEventListener("click", () => {
    const sid = state.selected;
    if (!sid) return;
    if (!canRemove(sid)) {
      pushLocalValidation("Cannot remove locked or mandatory step: " + sid);
      return;
    }
    removeStep(sid);
  });

  btnUp.addEventListener("click", () => {
    const sid = state.selected;
    if (!sid) return;
    if (isPinned(sid)) return;
    const from = idxOf(sid);
    if (from <= 0) return;
    const target = state.draft[from - 1];
    moveStep(sid, target);
  });

  btnDown.addEventListener("click", () => {
    const sid = state.selected;
    if (!sid) return;
    if (isPinned(sid)) return;
    const from = idxOf(sid);
    if (from < 0 || from >= state.draft.length - 1) return;
    const target = state.draft[from + 2] || null;
    moveStep(sid, target);
  });

  btnAdd.addEventListener("click", () => {
    const q = String(search.value || "").toLowerCase();
    const matches = state.palette
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

  reloadAll();
})();
