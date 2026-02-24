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
  };

  if (!ui.ta) return;

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
      return;
    }
    const cfg = out.data && out.data.config ? out.data.config : {};
    ui.ta.value = H.pretty(cfg);
    await loadHistory();
  }

  function parseJSON() {
    try {
      return { ok: true, data: JSON.parse(ui.ta.value || "{}")} ;
    } catch (e) {
      return { ok: false, err: String(e || "parse error") };
    }
  }

  async function validateOnly() {
    H.renderError(ui.err, null);
    const parsed = parseJSON();
    if (!parsed.ok) {
      ui.err.textContent = parsed.err;
      return;
    }
    const out = await H.requestJSON("/import/ui/config/validate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ config: parsed.data }),
    });
    if (!out.ok) {
      H.renderError(ui.err, out.data);
      return;
    }
    ui.ta.value = H.pretty(out.data.config || {});
  }

  async function save() {
    H.renderError(ui.err, null);
    const parsed = parseJSON();
    if (!parsed.ok) {
      ui.err.textContent = parsed.err;
      return;
    }
    const out = await H.requestJSON("/import/ui/config", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ config: parsed.data }),
    });
    if (!out.ok) {
      H.renderError(ui.err, out.data);
      return;
    }
    ui.ta.value = H.pretty(out.data.config || {});
    await loadHistory();
  }

  async function reset() {
    H.renderError(ui.err, null);
    const out = await H.requestJSON("/import/ui/config/reset", { method: "POST" });
    if (!out.ok) {
      H.renderError(ui.err, out.data);
      return;
    }
    ui.ta.value = H.pretty(out.data.config || {});
    await loadHistory();
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
    await loadHistory();
  }

  ui.reload && ui.reload.addEventListener("click", reload);
  ui.validate && ui.validate.addEventListener("click", validateOnly);
  ui.save && ui.save.addEventListener("click", save);
  ui.reset && ui.reset.addEventListener("click", reset);

  reload();
})();
