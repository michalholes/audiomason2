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

  function stableSteps(defn) {
    const steps = defn && Array.isArray(defn.steps) ? defn.steps : [];
    return steps
      .map((x) => (x && typeof x.step_id === "string" ? x.step_id : ""))
      .filter((x) => x);
  }

  function defFromSteps(stepIds) {
    return { steps: stepIds.map((sid) => ({ step_id: sid })) };
  }

  const state = {
    loaded: [],
    draft: [],
    palette: [],
    selected: null,
    dragId: null,
    dropBeforeId: null,
    showOptional: true,
    validation: { ok: null, items: [] },
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
  const validationTitle = text("div", "wdValidationTitle", "Validation");
  const validationCount = text("div", "wdValidationCount", "");
  const validationList = el("div", "wdValidationList");
  validationHeader.appendChild(validationTitle);
  validationHeader.appendChild(validationCount);
  validation.appendChild(validationHeader);
  validation.appendChild(validationList);

  table.appendChild(head);
  table.appendChild(body);

  const paletteSearch = el("div", "wdPaletteSearch");
  const search = el("input", "wdPaletteSearchInput");
  search.type = "search";
  search.placeholder = "Search";
  paletteSearch.appendChild(search);

  const paletteGroups = el("div", "wdPaletteGroups");
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

  function setSelected(stepId) {
    state.selected = stepId || null;
    render();
  }

  function setValidation(ok, items) {
    state.validation = {
      ok: typeof ok === "boolean" ? ok : null,
      items: Array.isArray(items) ? items.slice() : [],
    };
    renderValidation();
  }

  function pushValidation(msgText) {
    const items = state.validation.items.slice();
    items.push(String(msgText || ""));
    setValidation(false, items);
  }

  function removeStep(stepId) {
    if (!canRemove(stepId)) return;
    state.draft = state.draft.filter((x) => x !== stepId);
    if (state.selected === stepId) state.selected = null;
    render();
  }

  function addStep(stepId) {
    const sid = String(stepId || "");
    if (!sid) return;
    if (state.draft.includes(sid)) {
      pushValidation("Step already present: " + sid);
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
      H.renderError(ui.err, out.data);
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
      H.renderError(ui.err, out.data);
      return false;
    }
    const items = out.data && out.data.items ? out.data.items : [];
    state.palette = Array.isArray(items) ? items : [];
    return true;
  }

  async function loadDefinition() {
    const out = await H.requestJSON("/import/ui/wizard-definition");
    if (!out.ok) {
      H.renderError(ui.err, out.data);
      return false;
    }
    const defn = out.data && out.data.definition ? out.data.definition : {};
    const steps = stableSteps(defn);
    state.loaded = steps.slice();
    state.draft = steps.slice();
    state.selected = null;
    ui.ta.value = H.pretty(defn);
    return true;
  }

  async function reloadAll() {
    if (!confirmIfDirty("Reload")) return;
    H.renderError(ui.err, null);
    setValidation(null, []);
    const ok1 = await loadPalette();
    const ok2 = await loadDefinition();
    if (ok1 && ok2) {
      await loadHistory();
      render();
    }
  }

  async function validateDraft() {
    H.renderError(ui.err, null);
    setValidation(null, []);
    const payload = { definition: defFromSteps(state.draft) };
    const out = await H.requestJSON("/import/ui/wizard-definition/validate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!out.ok) {
      H.renderError(ui.err, out.data);
      pushValidation("Validation failed. See error details above.");
      return false;
    }
    const defn = out.data && out.data.definition ? out.data.definition : {};
    const steps = stableSteps(defn);
    state.draft = steps.slice();
    ui.ta.value = H.pretty(defn);
    setValidation(true, []);
    render();
    return true;
  }

  async function saveDraft() {
    if (!(await validateDraft())) return;

    const payload = { definition: defFromSteps(state.draft) };
    const out = await H.requestJSON("/import/ui/wizard-definition", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!out.ok) {
      H.renderError(ui.err, out.data);
      return;
    }
    const defn = out.data && out.data.definition ? out.data.definition : {};
    const steps = stableSteps(defn);
    state.loaded = steps.slice();
    state.draft = steps.slice();
    state.selected = null;
    ui.ta.value = H.pretty(defn);
    await loadHistory();
    render();
  }

  async function resetDefinition() {
    if (!confirmIfDirty("Reset")) return;

    H.renderError(ui.err, null);
    setValidation(null, []);
    const out = await H.requestJSON("/import/ui/wizard-definition/reset", {
      method: "POST",
    });
    if (!out.ok) {
      H.renderError(ui.err, out.data);
      return;
    }
    const defn = out.data && out.data.definition ? out.data.definition : {};
    const steps = stableSteps(defn);
    state.loaded = steps.slice();
    state.draft = steps.slice();
    state.selected = null;
    ui.ta.value = H.pretty(defn);
    await loadHistory();
    render();
  }

  async function rollback(id) {
    if (!confirmIfDirty("Rollback")) return;

    H.renderError(ui.err, null);
    setValidation(null, []);
    const out = await H.requestJSON("/import/ui/wizard-definition/rollback", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: id }),
    });
    if (!out.ok) {
      H.renderError(ui.err, out.data);
      return;
    }
    const defn = out.data && out.data.definition ? out.data.definition : {};
    const steps = stableSteps(defn);
    state.loaded = steps.slice();
    state.draft = steps.slice();
    state.selected = null;
    ui.ta.value = H.pretty(defn);
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
    const handle = text("span", "wdDragHandle", "::");
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
    typeCell.appendChild(text("span", "wdTypeBadge", kind));

    const reqCell = el("div", "wdCellReq");
    reqCell.appendChild(
      text(
        "span",
        "wdReqIcon",
        isPinned(stepId) || isMandatory(stepId) ? "L" : ""
      )
    );

    const actCell = el("div", "wdCellActions");
    const rm = text("button", "btn", "Del");
    rm.disabled = !canRemove(stepId);
    rm.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!canRemove(stepId)) {
        pushValidation("Cannot remove locked or mandatory step: " + stepId);
        return;
      }
      removeStep(stepId);
    });
    actCell.appendChild(rm);

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

      const add = text("button", "btn wdPaletteAdd", "+ Add");
      add.addEventListener("click", () => addStep(sid));
      item.appendChild(add);
      g.appendChild(item);
    });
    return g;
  }

  function renderValidation() {
    clear(validationList);
    validation.classList.remove("is-ok");
    validation.classList.remove("is-error");

    const items = state.validation.items;
    const ok = state.validation.ok;

    if (ok === true) {
      validation.classList.add("is-ok");
      validationCount.textContent = "OK";
      validationList.appendChild(text("div", "wdValidationItem", "No validation errors."));
      return;
    }

    if (items.length) {
      validation.classList.add("is-error");
      validationCount.textContent = String(items.length);
      items.forEach((s) => {
        validationList.appendChild(text("div", "wdValidationItem", s));
      });
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

    paletteGroups.appendChild(renderPaletteGroup("Mandatory", "mandatory", mandatory));
    paletteGroups.appendChild(renderPaletteGroup("Optional", "optional", optional));
    paletteGroups.appendChild(renderPaletteGroup("Conditional", "conditional", conditional));
  }

  search.addEventListener("input", () => render());

  optToggle.addEventListener("change", () => {
    state.showOptional = !!optToggle.checked;
    render();
  });

  btnRemove.addEventListener("click", () => {
    const sid = state.selected;
    if (!sid) return;
    if (!canRemove(sid)) {
      pushValidation("Cannot remove locked or mandatory step: " + sid);
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
      pushValidation("Add Step requires search to match exactly one palette item.");
      return;
    }
    addStep(matches[0].step_id);
  });

  ui.reload && ui.reload.addEventListener("click", reloadAll);
  ui.validate && ui.validate.addEventListener("click", validateDraft);
  ui.save && ui.save.addEventListener("click", saveDraft);
  ui.reset && ui.reset.addEventListener("click", resetDefinition);

  reloadAll();
})();
