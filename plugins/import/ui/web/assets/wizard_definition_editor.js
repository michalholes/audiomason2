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
    lastMsg: null,
    dragId: null,
  };

  const root = el("div", "wizardDefEditor");
  const bar = el("div", "wdBar");
  const msg = el("div", "wdMsg");
  const cols = el("div", "wdCols");
  const left = el("div", "wdLeft");
  const right = el("div", "wdRight");

  const stepsTitle = text("div", "wdSectionTitle", "Wizard Steps");
  const stepsList = el("div", "wdSteps");

  const palTitle = text("div", "wdSectionTitle", "Available Steps");
  const searchRow = el("div", "wdSearch");
  const search = el("input", "wdSearchInput");
  search.type = "search";
  search.placeholder = "Search";
  searchRow.appendChild(search);
  const palBody = el("div", "wdPalette");

  left.appendChild(stepsTitle);
  left.appendChild(stepsList);
  right.appendChild(palTitle);
  right.appendChild(searchRow);
  right.appendChild(palBody);

  cols.appendChild(left);
  cols.appendChild(right);
  root.appendChild(bar);
  root.appendChild(msg);
  root.appendChild(cols);

  ui.ta.parentNode.insertBefore(root, ui.ta);
  ui.ta.style.display = "none";

  function showMsg(s) {
    state.lastMsg = s ? String(s) : null;
    msg.textContent = state.lastMsg || "";
    msg.style.display = state.lastMsg ? "block" : "none";
  }

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
      showMsg("Step already present: " + sid);
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
    showMsg(null);
    const ok1 = await loadPalette();
    const ok2 = await loadDefinition();
    if (ok1 && ok2) {
      await loadHistory();
      render();
    }
  }

  async function validateDraft() {
    H.renderError(ui.err, null);
    showMsg(null);
    const payload = { definition: defFromSteps(state.draft) };
    const out = await H.requestJSON("/import/ui/wizard-definition/validate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!out.ok) {
      H.renderError(ui.err, out.data);
      return false;
    }
    const defn = out.data && out.data.definition ? out.data.definition : {};
    const steps = stableSteps(defn);
    state.draft = steps.slice();
    ui.ta.value = H.pretty(defn);
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
    showMsg(null);
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
    showMsg(null);
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

  function renderStepRow(stepId) {
    const row = el("div", "wdStepRow");
    row.dataset.stepId = stepId;

    const sel = state.selected === stepId;
    row.style.border = sel ? "1px solid #999" : "1px solid transparent";
    row.style.padding = "4px";
    row.style.margin = "2px 0";
    row.style.display = "flex";
    row.style.gap = "8px";
    row.style.alignItems = "center";

    const handle = text("span", "wdDrag", "::");
    handle.style.cursor = isPinned(stepId) ? "default" : "grab";

    const lock = text("span", "wdLock", isPinned(stepId) || isMandatory(stepId) ? "L" : "");
    lock.title = isPinned(stepId) ? "Pinned" : isMandatory(stepId) ? "Mandatory" : "";

    const label = text("span", "wdStepId", stepId);
    label.style.flex = "1";

    const rm = text("button", "btn", "Del");
    rm.disabled = !canRemove(stepId);

    row.appendChild(handle);
    row.appendChild(lock);
    row.appendChild(label);
    row.appendChild(rm);

    row.addEventListener("click", () => setSelected(stepId));
    rm.addEventListener("click", (e) => {
      e.stopPropagation();
      removeStep(stepId);
    });

    if (!isPinned(stepId)) {
      row.draggable = true;
      row.addEventListener("dragstart", (e) => {
        state.dragId = stepId;
        e.dataTransfer.effectAllowed = "move";
      });
    }

    row.addEventListener("dragover", (e) => {
      if (!state.dragId) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
    });

    row.addEventListener("drop", (e) => {
      if (!state.dragId) return;
      e.preventDefault();
      const dragId = state.dragId;
      state.dragId = null;
      moveStep(dragId, stepId);
    });

    return row;
  }

  function renderPaletteGroup(titleText, items) {
    const g = el("div", "wdPalGroup");
    const t = text("div", "wdPalTitle", titleText);
    t.style.marginTop = "8px";
    t.style.fontWeight = "bold";
    g.appendChild(t);

    items.forEach((it) => {
      const sid = String(it.step_id || "");
      if (!sid) return;

      const row = el("div", "wdPalRow");
      row.style.display = "flex";
      row.style.gap = "8px";
      row.style.alignItems = "center";
      row.style.margin = "2px 0";

      const add = text("button", "btn", "+");
      const lab = text("span", null, sid);
      lab.style.flex = "1";

      add.addEventListener("click", () => addStep(sid));

      row.appendChild(add);
      row.appendChild(lab);
      g.appendChild(row);
    });

    return g;
  }

  function render() {
    clear(bar);
    const dirty = isDirty();
    const d = text("span", "wdDirty", dirty ? "* unsaved" : "");
    d.style.fontWeight = "bold";
    bar.appendChild(d);

    clear(stepsList);
    state.draft.forEach((sid) => {
      stepsList.appendChild(renderStepRow(sid));
    });

    clear(palBody);
    const q = String(search.value || "").toLowerCase();
    const filtered = state.palette
      .filter((it) => it && it.step_id)
      .filter((it) => String(it.step_id).toLowerCase().includes(q));

    const mandatory = filtered.filter((it) => String(it.kind) === "mandatory");
    const optional = filtered.filter((it) => String(it.kind) === "optional");
    const conditional = filtered.filter((it) => String(it.kind) === "conditional");

    palBody.appendChild(renderPaletteGroup("Mandatory", mandatory));
    palBody.appendChild(renderPaletteGroup("Optional", optional));
    palBody.appendChild(renderPaletteGroup("Conditional", conditional));
  }

  search.addEventListener("input", () => render());

  ui.reload && ui.reload.addEventListener("click", reloadAll);
  ui.validate && ui.validate.addEventListener("click", validateDraft);
  ui.save && ui.save.addEventListener("click", saveDraft);
  ui.reset && ui.reset.addEventListener("click", resetDefinition);

  reloadAll();
})();
