async function fetchJSON(url, opts) {
  const r = await fetch(url, opts || {});
  if (!r.ok) {
    const t = await r.text();
    throw new Error(r.status + " " + r.statusText + ": " + t);
  }
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    return await r.json();
  }
  const t = await r.text();
  try { return JSON.parse(t); } catch { return { text: t }; }
}

window.__AM_APP_LOADED__ = true;

function _amFpKeyForBook(book) {
  // Backward/forward compatible fingerprint key extraction.
  // Prefer fingerprint if present; fall back to rel_path for legacy payloads.
  if (book && typeof book === "object") {
    if (typeof book.fingerprint === "string" && book.fingerprint) return book.fingerprint;
    if (typeof book.fp === "string" && book.fp) return book.fp;
    const meta = book.meta && typeof book.meta === "object" ? book.meta : null;
    if (meta && typeof meta.fingerprint === "string" && meta.fingerprint) return meta.fingerprint;
    if (typeof book.rel_path === "string" && book.rel_path) return book.rel_path;
    if (typeof book.path === "string" && book.path) return book.path;
  }
  return "";
}

function _amEnsureUiLogBuffer() {
  if (!window.__AM_UI_LOGS__ || !Array.isArray(window.__AM_UI_LOGS__)) {
    window.__AM_UI_LOGS__ = [];
  }
  return window.__AM_UI_LOGS__;
}

function _amPushUiLog(rec) {
  try {
    const buf = _amEnsureUiLogBuffer();
    buf.push(rec);
    if (buf.length > 4000) buf.splice(0, buf.length - 4000);
  } catch {
    // fail-safe
  }
}

function _amEnsureJsErrorBuffer() {
  if (!window.__AM_JS_ERRORS__ || !Array.isArray(window.__AM_JS_ERRORS__)) {
    window.__AM_JS_ERRORS__ = [];
  }
  return window.__AM_JS_ERRORS__;
}

function _amPushJsError(rec) {
  try {
    const buf = _amEnsureJsErrorBuffer();
    buf.push(rec);
    // Prevent unbounded growth.
    if (buf.length > 2000) buf.splice(0, buf.length - 2000);

    // Mirror into the unified UI debug log buffer.
    _amPushUiLog({ ...rec, channel: "js" });
  } catch (e) {
    // Error capture must be fail-safe.
  }
}


// Back-compat: older code used _amPushJSError (capital S).
window._amPushJsError = _amPushJsError;
window._amPushJSError = _amPushJsError;

function _amPushAnyJsError(rec) {
  try {
    const fn = typeof window._amPushJSError === "function"
      ? window._amPushJSError
      : (typeof window._amPushJsError === "function" ? window._amPushJsError : null);
    if (fn) fn(rec);
  } catch {
    // fail-safe
  }
}

function _amFormatHeaders(h) {
  try {
    const out = {};
    if (!h) return out;
    // Fast path for fetch Headers.
    if (typeof h.forEach === "function") {
      h.forEach((v, k) => { out[String(k)] = String(v); });
      return out;
    }
    // Plain object.
    if (typeof h === "object") {
      for (const [k, v] of Object.entries(h)) out[String(k)] = String(v);
    }
    return out;
  } catch {
    return {};
  }
}

function _amShowDebugModal(title, detailsText, notify) {
  try {
    const overlay = document.createElement("div");
    overlay.style.position = "fixed";
    overlay.style.left = "0";
    overlay.style.top = "0";
    overlay.style.right = "0";
    overlay.style.bottom = "0";
    overlay.style.background = "rgba(0,0,0,0.55)";
    overlay.style.display = "flex";
    overlay.style.alignItems = "center";
    overlay.style.justifyContent = "center";
    overlay.style.zIndex = "10000";

    const box = document.createElement("div");
    box.className = "modalBox";
    box.style.background = "#1b2230";
    box.style.border = "1px solid rgba(255,255,255,0.15)";
    box.style.borderRadius = "12px";
    box.style.padding = "16px";
    box.style.minWidth = "340px";
    box.style.maxWidth = "760px";
    box.style.color = "#fff";
    box.style.boxShadow = "0 10px 30px rgba(0,0,0,0.35)";

    const t = document.createElement("div");
    t.className = "subTitle";
    t.textContent = String(title || "Debug");
    box.appendChild(t);

    const pre = document.createElement("pre");
    pre.style.whiteSpace = "pre-wrap";
    pre.style.wordBreak = "break-word";
    pre.style.maxHeight = "360px";
    pre.style.overflow = "auto";
    pre.style.border = "1px solid rgba(255,255,255,0.08)";
    pre.style.borderRadius = "10px";
    pre.style.padding = "10px";
    pre.style.marginTop = "10px";
    pre.textContent = String(detailsText || "");
    box.appendChild(pre);

    const row = document.createElement("div");
    row.className = "buttonRow";
    row.style.gap = "8px";
    row.style.marginTop = "12px";

    const closeBtn = document.createElement("button");
    closeBtn.className = "btn";
    closeBtn.textContent = "Close";

    const copyBtn = document.createElement("button");
    copyBtn.className = "btn";
    copyBtn.textContent = "Copy";

    closeBtn.addEventListener("click", () => {
      try { document.body.removeChild(overlay); } catch {}
    });
    overlay.addEventListener("click", (ev) => {
      if (ev.target === overlay) {
        try { document.body.removeChild(overlay); } catch {}
      }
    });
    copyBtn.addEventListener("click", async () => {
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(String(detailsText || ""));
          if (typeof notify === "function") notify("Copied.");
          return;
        }
      } catch {
        // ignore
      }
      if (typeof notify === "function") notify("Copy failed.");
    });

    row.appendChild(copyBtn);
    row.appendChild(closeBtn);
    box.appendChild(row);

    overlay.appendChild(box);
    document.body.appendChild(overlay);
  } catch {
    // ignore
  }
}

function _amInstallDebugFetchCapture(notify) {
  if (window.__AM_FETCH_CAPTURE_INSTALLED__) return;
  window.__AM_FETCH_CAPTURE_INSTALLED__ = true;
  const orig = window.fetch;
  if (typeof orig !== "function") return;

  window.fetch = async function (input, init) {
    const ts = new Date().toISOString();
    let url = "";
    let method = "GET";
    let reqHeaders = {};
    let reqBody = null;
    try {
      if (typeof input === "string") url = input;
      else if (input && typeof input === "object" && "url" in input) url = String(input.url || "");
      if (init && typeof init === "object") {
        method = init.method ? String(init.method) : method;
        reqHeaders = _amFormatHeaders(init.headers);
        if (typeof init.body === "string") reqBody = init.body.slice(0, 4000);
      } else if (input && typeof input === "object" && "method" in input) {
        method = input.method ? String(input.method) : method;
      }
    } catch {
      // ignore
    }

    // Best-effort callsite capture.
    let stack = null;
    try { stack = String(new Error().stack || ""); } catch { stack = null; }

    try {
      const r = await orig(input, init);
      if (r && r.ok) return r;

      const status = r && typeof r.status === "number" ? r.status : 0;
      const statusText = r && typeof r.statusText === "string" ? r.statusText : "";
      const respHeaders = r && r.headers ? _amFormatHeaders(r.headers) : {};

      // Read response body from a clone so the caller can still consume it.
      let respText = "";
      try {
        const c = r && typeof r.clone === "function" ? r.clone() : null;
        if (c) respText = (await c.text()).slice(0, 8000);
      } catch {
        respText = "";
      }

      const rec = {
        ts,
        channel: "http",
        kind: "response_not_ok",
        method,
        url,
        status,
        status_text: statusText,
        request_headers: reqHeaders,
        request_body: reqBody,
        response_headers: respHeaders,
        response_text: (respText || "").trim(),
        stack,
      };
      rec.message = `${method} ${url} -> ${status} ${statusText}`.trim();
      _amPushUiLog(rec);

      if (typeof notify === "function") notify(`HTTP ${status} ${statusText}`.trim());
      _amShowDebugModal(`HTTP ${status} ${statusText}`.trim(), JSON.stringify(rec, null, 2), notify);
      return r;
    } catch (e) {
      const msg = e && typeof e === "object" && "message" in e ? String(e.message) : String(e);
      const rec = {
        ts,
        channel: "http",
        kind: "fetch_exception",
        method,
        url,
        message: msg,
        request_headers: reqHeaders,
        request_body: reqBody,
        stack,
      };
      _amPushUiLog(rec);
      if (typeof notify === "function") notify("HTTP request failed.");
      _amShowDebugModal("HTTP request failed", JSON.stringify(rec, null, 2), notify);
      throw e;
    }
  };
}

window.addEventListener("unhandledrejection", function (ev) {
  const r = ev ? ev.reason : null;
  const isErr = r && typeof r === "object" && "stack" in r;
  const msg = r && typeof r === "object" && "message" in r ? String(r.message) : String(r ?? "");
  _amPushAnyJsError({
    ts: new Date().toISOString(),
    kind: "unhandledrejection",
    message: msg,
    stack: isErr ? String(r.stack || "") : null,
    source: null,
    line: null,
    col: null,
  });
});

window.onerror = function (msg, src, line, col, err) {
  const e = err && typeof err === "object" ? err : null;
  _amPushAnyJsError({
    ts: new Date().toISOString(),
    kind: "error",
    message: String(msg ?? ""),
    stack: e && e.stack ? String(e.stack) : null,
    source: src ? String(src) : null,
    line: typeof line === "number" ? line : null,
    col: typeof col === "number" ? col : null,
  });
  return false;
};
(async function () {
  const API = {
    async _readErrorDetail(r) {
      const status = r && typeof r.status === "number" ? r.status : 0;
      let raw = "";
      try { raw = (await r.text()).slice(0, 800); } catch {}
      raw = (raw || "").trim();
      if (!raw) return `${status}`;
      // Prefer {"detail": "..."} or {"detail": {...}} from FastAPI
      try {
        const obj = JSON.parse(raw);
        if (obj && typeof obj === "object" && "detail" in obj) {
          const d = obj.detail;
          if (typeof d === "string") return `${status} ${d}`;
          return `${status} ${JSON.stringify(d)}`;
        }
      } catch {}
      return `${status} ${raw}`;
    },
    async getJson(path) {
      const r = await fetch(path, { headers: { "Accept": "application/json" } });
      if (!r.ok) {
        const d = await API._readErrorDetail(r);
        throw new Error(`GET ${path} -> ${d}`);
      }
      return await r.json();
    },
    async sendJson(method, path, body) {
      const r = await fetch(path, {
        method,
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!r.ok) {
        const d = await API._readErrorDetail(r);
        throw new Error(`${method} ${path} -> ${d}`);
      }
      const ct = r.headers.get("content-type") || "";
      if (ct.includes("application/json")) return await r.json();
      return { ok: true };
    },
  };

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (k === "class") node.className = v;
        else if (k === "text") node.textContent = String(v);
        else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v);
      }
    }
    (children || []).forEach((c) => node.appendChild(typeof c === "string" ? document.createTextNode(c) : c));
    return node;
  }

  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  function fmtTs(v) {
    if (typeof v !== "number") return String(v ?? "");
    // Accept seconds since epoch or already formatted
    if (v > 1e12) v = Math.floor(v / 1000);
    const d = new Date(v * 1000);
    if (isNaN(d.getTime())) return String(v);
    return d.toLocaleString();
  }

  function fpKeyForBook(book) {
    // Backward/forward compatible fingerprint key extraction.
    // Prefer fingerprint if present; fall back to rel_path for legacy payloads.
    if (book && typeof book === "object") {
      if (typeof book.fingerprint === "string" && book.fingerprint) return book.fingerprint;
      if (typeof book.fp === "string" && book.fp) return book.fp;
      const meta = book.meta && typeof book.meta === "object" ? book.meta : null;
      if (meta && typeof meta.fingerprint === "string" && meta.fingerprint) return meta.fingerprint;
      if (typeof book.rel_path === "string" && book.rel_path) return book.rel_path;
      if (typeof book.path === "string" && book.path) return book.path;
    }
    return "";
  }

  async function renderStatList(content) {
    const box = el("div", { class: "statList" });
    const src = content.source;
    const data = src && src.type === "api" ? await API.getJson(src.path) : {};
    for (const f of (content.fields || [])) {
      const key = f.key;
      let value = data && typeof data === "object" ? data[key] : "";
      if (key && key.endsWith("_ts")) value = fmtTs(value);
      box.appendChild(el("div", { class: "statRow" }, [
        el("div", { class: "statLabel", text: f.label || key }),
        el("div", { class: "statValue", text: value === undefined ? "" : String(value) }),
      ]));
    }
    return box;
  }

  async function renderTable(content) {
    const src = content.source;
    const data = src && src.type === "api" ? await API.getJson(src.path) : { items: [] };
    const items = Array.isArray(data.items) ? data.items : [];
    const cols = Array.isArray(content.columns) ? content.columns : [];
    const table = el("table", { class: "table" });
    const thead = el("thead");
    const trh = el("tr");
    cols.forEach((c) => trh.appendChild(el("th", { text: c.header || c.key })));
    thead.appendChild(trh);
    table.appendChild(thead);
    const tbody = el("tbody");
    items.forEach((row) => {
      const tr = el("tr");
      cols.forEach((c) => {
        let v = row ? row[c.key] : "";
        if (c.key && c.key.endsWith("_ts")) v = fmtTs(v);
        tr.appendChild(el("td", { text: v === undefined ? "" : String(v) }));
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    return el("div", { class: "tableWrap" }, [table]);
  }

  async function renderButtonRow(content, notify) {
    const wrap = el("div", { class: "buttonRow" });
    const buttons = Array.isArray(content.buttons) ? content.buttons : [];
    buttons.forEach((b) => {
      const btn = el("button", { class: "btn", text: b.label || "Action" });
      btn.addEventListener("click", async () => {
        try {
          const a = b.action || {};
          if (a.type === "api") {
            const method = (a.method || "POST").toUpperCase();
            const body = a.body;
            await API.sendJson(method, a.path, body);
            notify("Action executed.");
          } else if (a.type === "download" && a.href) {
            const r = await fetch(String(a.href));
            if (!r.ok) {
              const t = await r.text();
              throw new Error(r.status + " " + r.statusText + ": " + t);
            }
            const blob = await r.blob();
            let filename = "audiomason_debug_bundle.zip";
            const cd = r.headers.get("Content-Disposition") || "";
            const m = cd.match(/filename=\"([^\"]+)\"/);
            if (m && m[1]) filename = m[1];
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          } else {
            notify("Unsupported action type.");
          }
        } catch (e) {
          notify(String(e));
        }
      });
      wrap.appendChild(btn);
    });
    return wrap;
  }

  async function renderJsonEditor(content, notify) {
    const src = content.source;
    const data = src && src.type === "api" ? await API.getJson(src.path) : { data: {}, info: "" };
    const textarea = el("textarea", { class: "jsonEditor" });
    textarea.value = JSON.stringify(data.data || {}, null, 2) + "\n";
    const info = el("div", { class: "hint", text: `Source: ${data.info || ""}` });

    const saveBtn = el("button", { class: "btn", text: "Save" });
    saveBtn.addEventListener("click", async () => {
      try {
        const payload = JSON.parse(textarea.value || "{}");
        const a = content.save_action || {};
        if (a.type !== "api") throw new Error("save_action must be api");
        await API.sendJson((a.method || "PUT").toUpperCase(), a.path, payload);
        notify("Saved.");
      } catch (e) {
        notify(String(e));
      }
    });

    return el("div", { class: "jsonEditorWrap" }, [info, textarea, el("div", { class: "buttonRow" }, [saveBtn])]);
  }

  async function renderYamlEditor(content, notify) {
    const info = el("div", { class: "hint", text: "" });
    const textarea = el("textarea", { class: "jsonEditor" }); // reuse styling
    const saveBtn = el("button", { class: "btn", text: "Save" });

    async function load() {
      try {
        const src = content.source || {};
        if (src.type !== "api") throw new Error("source must be api");
        const data = await API.getJson(src.path);
        if (data && typeof data.info === "string") info.textContent = `Source: ${data.info}`;
        textarea.value = (data && typeof data.yaml === "string") ? data.yaml : "";
        if (!textarea.value.endsWith("\n")) textarea.value += "\n";
      } catch (e) {
        info.textContent = String(e);
      }
    }

    saveBtn.addEventListener("click", async () => {
      try {
        const a = content.save_action || {};
        if (a.type !== "api") throw new Error("save_action must be api");
        await API.sendJson((a.method || "PUT").toUpperCase(), a.path, { yaml: String(textarea.value || "") });
        notify("Saved.");
        await load();
      } catch (e) {
        notify(String(e));
      }
    });

    await load();
    return el("div", { class: "jsonEditorWrap" }, [info, textarea, el("div", { class: "buttonRow" }, [saveBtn])]);
  }


  async function renderLogStream(content) {
    const wrap = el("div", { class: "logWrap" });
    const pre = el("pre", { class: "logBox" });
    wrap.appendChild(pre);

    // Tail first
    try {
      if (content.tail_source && content.tail_source.type === "api") {
        const t = await API.getJson(content.tail_source.path);
        if (t && typeof t.text === "string") pre.textContent = t.text + "\n";
      }
    } catch {
      // ignore
    }

    const src = content.source;
    if (src && src.type === "sse") {
      const es = new EventSource(src.path);
      es.onmessage = (ev) => {
        pre.textContent += ev.data + "\n";
        pre.scrollTop = pre.scrollHeight;
      };
      es.onerror = () => {
        // keep box, EventSource retries automatically
      };
    } else {
      pre.textContent += "(log stream source not configured)\n";
    }

    return wrap;
  }


async function renderJsErrorFeed(content, notify) {
  // UI-only, in-memory view over window.__AM_JS_ERRORS__.
  _amEnsureJsErrorBuffer();

  let paused = false;
  let filterText = "";

  const root = el("div");

  const controls = el("div", { class: "row" });
  const filterInput = el("input", { class: "input", type: "text", placeholder: "Filter..." });
  filterInput.style.maxWidth = "420px";
  const pauseBtn = el("button", { class: "btn", text: "Pause" });
  const clearBtn = el("button", { class: "btn danger", text: "Clear" });
  const exportBtn = el("button", { class: "btn", text: "Export JSONL" });
  controls.appendChild(filterInput);
  controls.appendChild(pauseBtn);
  controls.appendChild(clearBtn);
  controls.appendChild(exportBtn);
  root.appendChild(controls);

  const hint = el("div", { class: "hint", text: "Captures window.onerror and unhandledrejection (session-local)." });
  root.appendChild(hint);

  const box = el("div", { class: "logBox" });
  box.style.height = "420px";
  box.style.whiteSpace = "normal";
  root.appendChild(box);

  function recordMatches(rec, f) {
    if (!f) return true;
    const hay = [
      rec && typeof rec.ts === "string" ? rec.ts : "",
      rec && typeof rec.kind === "string" ? rec.kind : "",
      rec && typeof rec.message === "string" ? rec.message : "",
      rec && typeof rec.stack === "string" ? rec.stack : "",
      rec && typeof rec.source === "string" ? rec.source : "",
    ].join("\n").toLowerCase();
    return hay.includes(f);
  }

  function snapshotFiltered() {
    const buf = _amEnsureJsErrorBuffer();
    const f = String(filterText || "").trim().toLowerCase();
    const out = [];
    for (let i = buf.length - 1; i >= 0; i--) {
      const rec = buf[i];
      if (recordMatches(rec, f)) out.push(rec);
    }
    return out;
  }

  async function copyText(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch {
      // ignore
    }
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-1000px";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch {
      return false;
    }
  }

  function renderOnce() {
    const items = snapshotFiltered();
    clear(box);
    if (!items.length) {
      box.appendChild(el("div", { class: "hint", text: "No errors captured." }));
      return;
    }

    for (const rec of items) {
      const row = el("div");
      row.style.borderBottom = "1px solid rgba(255,255,255,0.06)";
      row.style.padding = "8px 0";

      const top = el("div", { class: "row" });
      top.style.margin = "0 0 6px 0";
      const meta = el("div", { class: "hint", text: `${rec.ts || ""}  ${rec.kind || ""}` });
      meta.style.flex = "1";
      const copyBtn = el("button", { class: "btn", text: "Copy" });
      copyBtn.addEventListener("click", async () => {
        const txt = JSON.stringify(rec, null, 2);
        const ok = await copyText(txt);
        notify(ok ? "Copied." : "Copy failed.");
      });
      top.appendChild(meta);
      top.appendChild(copyBtn);

      const pre = el("pre");
      pre.style.margin = "0";
      pre.style.whiteSpace = "pre-wrap";
      pre.style.fontFamily = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace";
      pre.style.fontSize = "12px";
      const parts = [];
      if (rec.message) parts.push(String(rec.message));
      if (rec.source) parts.push(`source: ${rec.source}`);
      if (rec.line !== null || rec.col !== null) parts.push(`loc: ${rec.line ?? ""}:${rec.col ?? ""}`);
      if (rec.stack) parts.push(String(rec.stack));
      pre.textContent = parts.join("\n");

      row.appendChild(top);
      row.appendChild(pre);
      box.appendChild(row);
    }
  }

  filterInput.addEventListener("input", () => {
    filterText = String(filterInput.value || "");
    renderOnce();
  });

  pauseBtn.addEventListener("click", () => {
    paused = !paused;
    pauseBtn.textContent = paused ? "Resume" : "Pause";
    if (!paused) renderOnce();
  });

  clearBtn.addEventListener("click", () => {
    try {
      const buf = _amEnsureJsErrorBuffer();
      buf.length = 0;
    } catch {
      // ignore
    }
    renderOnce();
  });

  exportBtn.addEventListener("click", () => {
    try {
      const items = snapshotFiltered();
      const jsonl = items.map((r) => JSON.stringify(r)).join("\n") + "\n";
      const blob = new Blob([jsonl], { type: "application/x-ndjson" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "am_js_errors.jsonl";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      notify(String(e));
    }
  });

  renderOnce();
  const timer = setInterval(() => {
    if (!paused) renderOnce();
  }, 500);
  // Best-effort cleanup when route changes.
  window.addEventListener("popstate", () => clearInterval(timer), { once: true });

  return root;
}


async function renderUiDebugFeed(content, notify) {
  // UI-only unified view over window.__AM_UI_LOGS__ (debug mode).
  _amEnsureUiLogBuffer();

  let paused = false;
  let filterText = "";

  const root = el("div");

  const controls = el("div", { class: "row" });
  const filterInput = el("input", { class: "input", type: "text", placeholder: "Filter..." });
  filterInput.style.maxWidth = "420px";
  const pauseBtn = el("button", { class: "btn", text: "Pause" });
  const clearBtn = el("button", { class: "btn danger", text: "Clear" });
  const exportBtn = el("button", { class: "btn", text: "Export JSONL" });
  controls.appendChild(filterInput);
  controls.appendChild(pauseBtn);
  controls.appendChild(clearBtn);
  controls.appendChild(exportBtn);
  root.appendChild(controls);

  const hint = el("div", { class: "hint", text: "Debug mode: browser-side errors and HTTP failures (session-local)." });
  root.appendChild(hint);

  const box = el("div", { class: "logBox" });
  box.style.height = "520px";
  box.style.whiteSpace = "normal";
  root.appendChild(box);

  function recordMatches(rec, f) {
    if (!f) return true;
    const hay = [
      rec && typeof rec.ts === "string" ? rec.ts : "",
      rec && typeof rec.channel === "string" ? rec.channel : "",
      rec && typeof rec.kind === "string" ? rec.kind : "",
      rec && typeof rec.message === "string" ? rec.message : "",
      rec && typeof rec.url === "string" ? rec.url : "",
      rec && typeof rec.method === "string" ? rec.method : "",
      rec && typeof rec.response_text === "string" ? rec.response_text : "",
    ].join("\n").toLowerCase();
    return hay.includes(f);
  }

  function snapshotFiltered() {
    const buf = _amEnsureUiLogBuffer();
    const f = String(filterText || "").trim().toLowerCase();
    const out = [];
    for (let i = buf.length - 1; i >= 0; i--) {
      const rec = buf[i];
      if (recordMatches(rec, f)) out.push(rec);
    }
    return out;
  }

  async function copyText(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch {
      // ignore
    }
    return false;
  }

  function renderOnce() {
    const items = snapshotFiltered();
    clear(box);
    if (!items.length) {
      box.appendChild(el("div", { class: "hint", text: "No debug records captured." }));
      return;
    }

    for (const rec of items) {
      const row = el("div");
      row.style.borderBottom = "1px solid rgba(255,255,255,0.06)";
      row.style.padding = "8px 0";

      const top = el("div", { class: "row" });
      top.style.margin = "0 0 6px 0";
      const channel = rec.channel || "";
      const kind = rec.kind || "";
      const meta = el("div", { class: "hint", text: `${rec.ts || ""}  ${channel} ${kind}`.trim() });
      meta.style.flex = "1";
      const detailsBtn = el("button", { class: "btn", text: "Details" });
      const copyBtn = el("button", { class: "btn", text: "Copy" });
      detailsBtn.addEventListener("click", () => {
        _amShowDebugModal(`${channel} ${kind}`.trim(), JSON.stringify(rec, null, 2), notify);
      });
      copyBtn.addEventListener("click", async () => {
        const txt = JSON.stringify(rec, null, 2);
        const ok = await copyText(txt);
        if (typeof notify === "function") notify(ok ? "Copied." : "Copy failed.");
      });
      top.appendChild(meta);
      top.appendChild(detailsBtn);
      top.appendChild(copyBtn);
      row.appendChild(top);

      const msg = rec.message || (rec.status ? `${rec.method || ""} ${rec.url || ""} -> ${rec.status}` : "");
      row.appendChild(el("div", { class: "mono", text: String(msg || "") }));

      if (rec.response_text) {
        const pre = el("pre");
        pre.style.marginTop = "6px";
        pre.style.whiteSpace = "pre-wrap";
        pre.style.wordBreak = "break-word";
        pre.textContent = String(rec.response_text);
        row.appendChild(pre);
      }

      box.appendChild(row);
    }

    // Auto-scroll to end.
    try { box.scrollTop = box.scrollHeight; } catch {}
  }

  filterInput.addEventListener("input", () => {
    filterText = String(filterInput.value || "");
    if (!paused) renderOnce();
  });
  pauseBtn.addEventListener("click", () => {
    paused = !paused;
    pauseBtn.textContent = paused ? "Resume" : "Pause";
    if (!paused) renderOnce();
  });
  clearBtn.addEventListener("click", () => {
    const buf = _amEnsureUiLogBuffer();
    buf.splice(0, buf.length);
    renderOnce();
  });
  exportBtn.addEventListener("click", () => {
    const buf = _amEnsureUiLogBuffer();
    const lines = buf.map((r) => JSON.stringify(r));
    const blob = new Blob([lines.join("\n") + "\n"], { type: "application/x-ndjson" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "audiomason_ui_debug.jsonl";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2500);
  });

  // Live refresh.
  renderOnce();
  const timer = setInterval(() => {
    if (!paused) renderOnce();
  }, 500);
  root.addEventListener("DOMNodeRemoved", () => { try { clearInterval(timer); } catch {} });

  return root;
}


async function renderJobsLogViewer(content, notify) {
  const root = el("div", { class: "jobsLog" });
  const header = el("div", { class: "row" });
  const refreshBtn = el("button", { class: "btn", text: "Refresh jobs" });
  header.appendChild(refreshBtn);
  root.appendChild(header);

  const grid = el("div", { class: "jobsGrid" });
  const left = el("div", { class: "jobsCol" });
  const right = el("div", { class: "jobsColWide" });
  grid.appendChild(left);
  grid.appendChild(right);
  root.appendChild(grid);

  const jobsBox = el("div");
  left.appendChild(jobsBox);

  const logHeader = el("div", { class: "row" });
  const followChk = el("input", { type: "checkbox" });
  const followLbl = el("label", { class: "hint", text: "Follow" });
  followLbl.prepend(followChk);
  const clearBtn = el("button", { class: "btn", text: "Clear" });
  logHeader.appendChild(followLbl);
  logHeader.appendChild(clearBtn);
  right.appendChild(logHeader);

  const pre = el("pre", { class: "logBox", text: "Select a job." });
  right.appendChild(pre);

  let currentJobId = null;
  let offset = 0;
  let followTimer = null;

  async function loadJobs() {
    jobsBox.innerHTML = "";
    let data;
    try {
      data = await API.getJson("/api/jobs");
    } catch (e) {
      jobsBox.appendChild(el("div", { class: "hint", text: String(e) }));
      return;
    }
    const items = Array.isArray(data.items) ? data.items : [];
    if (!items.length) {
      jobsBox.appendChild(el("div", { class: "hint", text: "No jobs." }));
      return;
    }

    const table = el("table", { class: "table" });
    const thead = el("thead");
    const trh = el("tr");
    ["job_id", "type", "state"].forEach((h) => trh.appendChild(el("th", { text: h })));
    thead.appendChild(trh);
    table.appendChild(thead);
    const tbody = el("tbody");

    for (const j of items) {
      const jid = j.job_id || j.id || "";
      const tr = el("tr");
      tr.appendChild(el("td", { text: String(jid) }));
      tr.appendChild(el("td", { text: String(j.type || "") }));
      tr.appendChild(el("td", { text: String(j.state || "") }));
      tr.addEventListener("click", async () => {
        currentJobId = String(jid);
        offset = 0;
        pre.textContent = "";
        await loadMore();
      });
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    jobsBox.appendChild(table);
  }

  async function loadMore() {
    if (!currentJobId) {
      pre.textContent = "Select a job.";
      return;
    }
    try {
      const data = await API.getJson(`/api/jobs/${encodeURIComponent(currentJobId)}/log?offset=${offset}`);
      const txt = data && typeof data.text === "string" ? data.text : "";
      pre.textContent += txt;
      offset = (data && typeof data.next_offset === "number") ? data.next_offset : offset;
      pre.scrollTop = pre.scrollHeight;
    } catch (e) {
      notify(String(e));
    }
  }

  function stopFollow() {
    if (followTimer) {
      clearInterval(followTimer);
      followTimer = null;
    }
  }

  followChk.addEventListener("change", () => {
    stopFollow();
    if (followChk.checked) {
      followTimer = setInterval(loadMore, 1500);
    }
  });

  clearBtn.addEventListener("click", () => {
    pre.textContent = "";
    offset = 0;
  });

  refreshBtn.addEventListener("click", loadJobs);

  await loadJobs();
  return root;
}


async function renderImportWizard(content, notify) {
  const root = el("div", { class: "importWizard" });

  // Optional actions declared in UI schema (e.g., debug bundle download).
  if (content && Array.isArray(content.actions) && content.actions.length) {
    const actionsRow = el("div", { class: "row" });
    content.actions.forEach((a) => {
      if (!a || a.type !== "download" || !a.href) return;
      const btn = el("button", { class: "btn", text: String(a.label || "Download") });
      btn.addEventListener("click", async () => {
        try {
          const r = await fetch(String(a.href));
          if (!r.ok) {
            const t = await r.text();
            throw new Error(r.status + " " + r.statusText + ": " + t);
          }
          const blob = await r.blob();
          let filename = "audiomason_debug_bundle.zip";
          const cd = r.headers.get("Content-Disposition") || "";
          const m = cd.match(/filename="([^"]+)"/);
          if (m && m[1]) filename = m[1];
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = filename;
          document.body.appendChild(link);
          link.click();
          link.remove();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (e) {
          notify(String(e));
        }
      });
      actionsRow.appendChild(btn);
    });
    root.appendChild(actionsRow);
  }

  const row1 = el("div", { class: "row" });
  const rootLbl = el("span", { class: "hint", text: "Root:" });
  const rootSel = el("select");
  const pathLbl = el("span", { class: "hint", text: "Path:" });
  const pathInp = el("input", { type: "text", value: ".", style: "min-width:220px" });
  const loadBtn = el("button", { class: "btn", text: "Refresh index" });
  const spinner = el("span", { class: "hint", text: "" });
  row1.appendChild(rootLbl);
  row1.appendChild(rootSel);
  row1.appendChild(pathLbl);
  row1.appendChild(pathInp);
  row1.appendChild(loadBtn);
  row1.appendChild(spinner);
  root.appendChild(row1);

  const grid = el("div", { class: "jobsGrid" });
  const left = el("div", { class: "jobsCol" });
  const mid = el("div", { class: "jobsCol" });
  const right = el("div", { class: "jobsColWide" });
  grid.appendChild(left);
  grid.appendChild(mid);
  grid.appendChild(right);
  root.appendChild(grid);

  left.appendChild(el("div", { class: "hint", text: "Authors" }));
  const authorsBox = el("div");
  left.appendChild(authorsBox);

  mid.appendChild(el("div", { class: "hint", text: "Books" }));
  const booksBox = el("div");
  mid.appendChild(booksBox);

  const actionsRow = el("div", { class: "row" });
  const modeSel = el("select");
  ["stage", "inplace", "hybrid"].forEach((m) => modeSel.appendChild(el("option", { value: m, text: m })));
  const run1Btn = el("button", { class: "btn", text: "Run 1 pending" });
  const run5Btn = el("button", { class: "btn", text: "Run 5 pending" });
  actionsRow.appendChild(el("span", { class: "hint", text: "Mode:" }));
  actionsRow.appendChild(modeSel);
  actionsRow.appendChild(run1Btn);
  actionsRow.appendChild(run5Btn);
  right.appendChild(actionsRow);

  // PHASE 1 audio processing decisions (Issue 504).
  const audioBox = el("div", { class: "row" });
  audioBox.style.flexWrap = "wrap";
  audioBox.style.gap = "10px";

  const loudCb = el("input", { type: "checkbox" });
  const loudLbl = el("label", { class: "hint", text: "Loudnorm" });
  loudLbl.style.display = "flex";
  loudLbl.style.alignItems = "center";
  loudLbl.style.gap = "6px";
  loudLbl.prepend(loudCb);

  const brCb = el("input", { type: "checkbox" });
  const brLbl = el("label", { class: "hint", text: "Bitrate" });
  brLbl.style.display = "flex";
  brLbl.style.alignItems = "center";
  brLbl.style.gap = "6px";
  brLbl.prepend(brCb);

  const brInp = el("input", { type: "number", value: "96", min: "8", max: "512" });
  brInp.style.width = "90px";
  const brUnit = el("span", { class: "hint", text: "kbps" });

  const brModeSel = el("select");
  ["cbr", "vbr"].forEach((m) => brModeSel.appendChild(el("option", { value: m, text: m.toUpperCase() })));

  audioBox.appendChild(el("span", { class: "hint", text: "Audio:" }));
  audioBox.appendChild(loudLbl);
  audioBox.appendChild(brLbl);
  audioBox.appendChild(brInp);
  audioBox.appendChild(brUnit);
  audioBox.appendChild(brModeSel);
  right.appendChild(audioBox);

  const statusBox = el("div", { class: "hint", text: "No jobs started." });
  const jobsTableWrap = el("div");
  right.appendChild(statusBox);
  right.appendChild(jobsTableWrap);

  let indexData = null;
  let selectedAuthor = "";
  let jobIds = [];
  let pollTimer = null;
  let dotsTimer = null;
  const BOOK_ONLY_LABEL = "<book-only>";
  let indexTimer = null;
  let enrichTimer = null;
  let lastEnrichKey = "";
  let enrichRefreshCounter = 0;
  let processedKeys = new Set();

  async function loadProcessedRegistry() {
    try {
      const r = await API.getJson("/api/import_wizard/processed_registry");
      const keys = (r && Array.isArray(r.keys)) ? r.keys : [];
      processedKeys = new Set(keys.filter((k) => typeof k === "string" && k));
    } catch {
      processedKeys = new Set();
    }
  }


function showConflictPolicyModal() {
  return new Promise((resolve) => {
    const overlay = el("div", { class: "modalOverlay" });
    overlay.style.position = "fixed";
    overlay.style.left = "0";
    overlay.style.top = "0";
    overlay.style.right = "0";
    overlay.style.bottom = "0";
    overlay.style.background = "rgba(0,0,0,0.55)";
    overlay.style.display = "flex";
    overlay.style.alignItems = "center";
    overlay.style.justifyContent = "center";
    overlay.style.zIndex = "9999";

    const box = el("div", { class: "modalBox" });
    box.style.background = "#1b2230";
    box.style.border = "1px solid rgba(255,255,255,0.15)";
    box.style.borderRadius = "12px";
    box.style.padding = "16px";
    box.style.minWidth = "320px";
    box.style.maxWidth = "520px";
    box.style.color = "#fff";
    box.style.boxShadow = "0 10px 30px rgba(0,0,0,0.35)";

    box.appendChild(el("div", { class: "subTitle", text: "Conflict detected" }));
    box.appendChild(el("div", {
      class: "hint",
      text: "Import requires conflict resolution. Choose how to continue:",
    }));

    const row = el("div", { class: "buttonRow" });
    row.style.gap = "8px";

    const skipBtn = el("button", { class: "btn", text: "Skip" });
    const overBtn = el("button", { class: "btn", text: "Overwrite" });
    const cancelBtn = el("button", { class: "btn danger", text: "Cancel" });

    function close(v) {
      try { document.body.removeChild(overlay); } catch {}
      resolve(v);
    }

    skipBtn.addEventListener("click", () => close("skip"));
    overBtn.addEventListener("click", () => close("overwrite"));
    cancelBtn.addEventListener("click", () => close(null));
    overlay.addEventListener("click", (ev) => {
      if (ev.target === overlay) close(null);
    });

    row.appendChild(skipBtn);
    row.appendChild(overBtn);
    row.appendChild(cancelBtn);
    box.appendChild(row);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
  });
}


function showAudioProcessingConfirmModal(ap) {
  return new Promise((resolve) => {
    const overlay = el("div", { class: "modalOverlay" });
    overlay.style.position = "fixed";
    overlay.style.left = "0";
    overlay.style.top = "0";
    overlay.style.right = "0";
    overlay.style.bottom = "0";
    overlay.style.background = "rgba(0,0,0,0.55)";
    overlay.style.display = "flex";
    overlay.style.alignItems = "center";
    overlay.style.justifyContent = "center";
    overlay.style.zIndex = "9999";

    const box = el("div", { class: "modalBox" });
    box.style.background = "#1b2230";
    box.style.border = "1px solid rgba(255,255,255,0.15)";
    box.style.borderRadius = "12px";
    box.style.padding = "16px";
    box.style.minWidth = "340px";
    box.style.maxWidth = "560px";
    box.style.color = "#fff";
    box.style.boxShadow = "0 10px 30px rgba(0,0,0,0.35)";

    box.appendChild(el("div", { class: "subTitle", text: "Confirm audio processing" }));
    const lines = [];
    if (ap && ap.loudnorm) lines.push("Loudness normalization (loudnorm)");
    if (ap && ap.bitrate_kbps) {
      const mode = (ap.bitrate_mode || "cbr").toUpperCase();
      lines.push(`Re-encode MP3 at ${ap.bitrate_kbps} kbps (${mode})`);
    }
    if (!lines.length) lines.push("No audio processing selected.");
    box.appendChild(el("div", { class: "hint", text: lines.join("\n") }));

    const row = el("div", { class: "buttonRow" });
    row.style.gap = "8px";

    const okBtn = el("button", { class: "btn", text: "Confirm" });
    const cancelBtn = el("button", { class: "btn danger", text: "Cancel" });

    function close(v) {
      try { document.body.removeChild(overlay); } catch {}
      resolve(v);
    }

    okBtn.addEventListener("click", () => close(true));
    cancelBtn.addEventListener("click", () => close(false));
    overlay.addEventListener("click", (ev) => {
      if (ev.target === overlay) close(false);
    });

    row.appendChild(okBtn);
    row.appendChild(cancelBtn);
    box.appendChild(row);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
  });
}

async function startImportWithConflictAsk(body) {
  const path = "/api/import_wizard/start";

  async function doPost(payload) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(payload),
    });
    if (r.ok) {
      return { ok: true, data: await r.json() };
    }
    const status = r.status;
    let text = "";
    try { text = (await r.text()).slice(0, 1200); } catch {}
    text = (text || "").trim();
    let obj = null;
    try { obj = text ? JSON.parse(text) : null; } catch { obj = null; }
    return { ok: false, status, text, obj };
  }

  let res = await doPost(body);
  if (res.ok) return res.data;

  const detail = (res.obj && typeof res.obj === "object" && res.obj !== null && "detail" in res.obj)
    ? res.obj.detail
    : res.obj;

  if (res.status === 409 && detail && typeof detail === "object" && detail.error === "conflict_policy_unresolved") {
    const pol = detail.conflict_policy || {};
    if (pol && pol.mode === "ask") {
      const choice = await showConflictPolicyModal();
      if (!choice) {
        throw new Error("POST /api/import_wizard/start -> 409 conflict unresolved (canceled)");
      }
      const body2 = Object.assign({}, body, { conflict_policy: { mode: choice } });
      res = await doPost(body2);
      if (res.ok) return res.data;
    }
  }

  const suffix = res.text ? ` ${res.text}` : "";
  throw new Error(`POST ${path} -> ${res.status}${suffix}`);
}


  function stopEnrichmentPolling() {
    if (enrichTimer) { clearInterval(enrichTimer); enrichTimer = null; }
  }


  async function loadRoots() {
    const data = await API.getJson("/api/roots");
    const items = Array.isArray(data.items) ? data.items : [];
    clear(rootSel);
    items.forEach((it) => {
      if (it && it.id) {
        rootSel.appendChild(el("option", { value: it.id, text: it.label || it.id }));
      }
    });
    if (!rootSel.value) rootSel.value = "inbox";
    // Prefer Inbox if present.
    const optInbox = Array.from(rootSel.options).find((o) => o.value === "inbox");
    if (optInbox) rootSel.value = "inbox";
  }

  function setBusy(on) {
    loadBtn.disabled = !!on;
    rootSel.disabled = !!on;
    pathInp.disabled = !!on;
    if (dotsTimer) { clearInterval(dotsTimer); dotsTimer = null; }
    if (!on) { spinner.textContent = ""; return; }
    let n = 0;
    dotsTimer = setInterval(() => {
      n = (n + 1) % 4;
      spinner.textContent = "Working" + ".".repeat(n);
    }, 250);
  }

  function renderAuthors() {
    clear(authorsBox);
    const authors = indexData && Array.isArray(indexData.authors) ? indexData.authors : [];
    if (!authors.length) {
      authorsBox.appendChild(el("div", { class: "hint", text: "No authors found." }));
      return;
    }
    authors.forEach((a) => {
      const btn = el("button", { class: "btn", text: String(a) });
      btn.style.width = "100%";
      btn.addEventListener("click", () => {
        selectedAuthor = String(a);
        renderBooks();
        // Auto-next: scroll books list into view.
        try { booksBox.scrollIntoView({ block: "nearest" }); } catch {}
      });
      authorsBox.appendChild(btn);
    });
  }

  function renderBooks() {
    clear(booksBox);
    const books = indexData && Array.isArray(indexData.books) ? indexData.books : [];
    const isBookOnly = selectedAuthor === BOOK_ONLY_LABEL;
    const filtered = selectedAuthor
      ? books.filter((b) => {
          const a = b && typeof b.author === "string" ? b.author : "";
          if (isBookOnly) return !a;
          return a === selectedAuthor;
        })
      : [];
    if (!selectedAuthor) {
      booksBox.appendChild(el("div", { class: "hint", text: "Select an author." }));
      return;
    }
    if (!filtered.length) {
      booksBox.appendChild(el("div", { class: "hint", text: "No books found." }));
      return;
    }

    filtered.forEach((b) => {
      const title = (b && b.book) ? String(b.book) : (b && b.rel_path ? String(b.rel_path) : "(book)");
      const relPath = String((b && b.rel_path) ? b.rel_path : "");
      const key = _amFpKeyForBook(b);
      const isProcessed = !!(key && processedKeys && processedKeys.has(key));

      const row = el("div", { class: "row", style: "gap:8px;align-items:center" });
      const btn = el("button", { class: "btn", text: title });
      btn.style.flex = "1";
      btn.style.width = "100%";
      if (isProcessed) {
        btn.disabled = true;
        btn.style.opacity = "0.55";
        btn.title = "Already processed.";
      }

      btn.addEventListener("click", async () => {
        if (isProcessed) return;
        try {
          setBusy(true);
          statusBox.textContent = "Starting import...";
          jobsTableWrap.textContent = "";
          jobIds = [];

          // Collect PHASE 1 options.
          const audioEnabled = !!(loudCb.checked || brCb.checked);
          const options = {};
          if (audioEnabled) {
            let kbps = 96;
            try { kbps = parseInt(String(brInp.value || "96"), 10); } catch {}
            if (!isFinite(kbps) || kbps <= 0) kbps = 96;
            const ap = {
              enabled: true,
              loudnorm: !!loudCb.checked,
              bitrate_kbps: kbps,
              bitrate_mode: String(brModeSel.value || "cbr").toLowerCase(),
            };
            const ok = await showAudioProcessingConfirmModal(ap);
            if (!ok) {
              statusBox.textContent = "Canceled.";
              return;
            }
            ap.confirmed = true;
            options.audio_processing = ap;
          }

          const body = {
            root: rootSel.value,
            path: pathInp.value,
            book_rel_path: relPath,
            mode: modeSel.value,
            options: options,
          };
          const r = await startImportWithConflictAsk(body);
          jobIds = Array.isArray(r.job_ids) ? r.job_ids : [];
          if (!jobIds.length) {
            statusBox.textContent = "No jobs created.";
          } else {
            statusBox.textContent = `Jobs created: ${jobIds.join(", ")}`;
            startPolling();
          }
        } catch (e) {
          notify(String(e));
          statusBox.textContent = String(e);
        } finally {
          setBusy(false);
        }
      });

      row.appendChild(btn);

      if (isProcessed) {
        const unmarkBtn = el("button", { class: "btn danger", text: "Unmark" });
        unmarkBtn.addEventListener("click", async (ev) => {
          try { ev && ev.preventDefault && ev.preventDefault(); } catch {}
          try {
            if (!key) throw new Error("Missing fingerprint key.");
            await API.sendJson("POST", "/api/import_wizard/unmark_processed", { key: key });
            await loadProcessedRegistry();
            renderBooks();
            statusBox.textContent = "Unmarked. You can start again.";
          } catch (e) {
            notify(String(e));
          }
        });
        row.appendChild(unmarkBtn);
      }

      booksBox.appendChild(row);
    });

    // Auto-next: if there is only one unprocessed book, start it immediately.
    const unprocessed = filtered.filter((b) => {
      const k = _amFpKeyForBook(b);
      return !(k && processedKeys && processedKeys.has(k));
    });
    if (unprocessed.length === 1) {
      try {
        const buttons = booksBox.querySelectorAll("button");
        // first button in the row is the start button
        if (buttons && buttons[0]) buttons[0].click();
      } catch {}
    }
  }

  function renderJobsTable(items) {
    const table = el("table", { class: "table" });
    const thead = el("thead");
    const trh = el("tr");
    ["job_id", "state", "type", "error"].forEach((h) => trh.appendChild(el("th", { text: h })));
    thead.appendChild(trh);
    table.appendChild(thead);
    const tbody = el("tbody");
    (items || []).forEach((it) => {
      const tr = el("tr");
      tr.appendChild(el("td", { text: String(it.job_id || "") }));
      tr.appendChild(el("td", { text: String(it.state || "") }));
      tr.appendChild(el("td", { text: String(it.type || "") }));
      tr.appendChild(el("td", { text: String(it.error || "") }));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    clear(jobsTableWrap);
    jobsTableWrap.appendChild(el("div", { class: "tableWrap" }, [table]));
  }

  async function pollOnce() {
    if (!jobIds.length) return;
    const items = [];
    for (const id of jobIds) {
      try {
        const r = await API.getJson(`/api/jobs/${encodeURIComponent(id)}`);
        const it = r && r.item ? r.item : {};
        items.push({
          job_id: it.job_id || id,
          state: it.state || "",
          type: it.type || "",
          error: it.error || "",
        });
      } catch (e) {
        items.push({ job_id: id, state: "(missing)", type: "", error: String(e) });
      }
    }
    renderJobsTable(items);
  }

  function startPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    void pollOnce();
    pollTimer = setInterval(() => { void pollOnce(); }, 1000);
  }

  async function doRunPending(limit) {
    try {
      const r = await API.sendJson("POST", "/api/import_wizard/run_pending", { limit: limit });
      const ran = r && Array.isArray(r.ran) ? r.ran : [];
      if (ran.length) notify("Ran: " + ran.join(", "));
      await pollOnce();
    } catch (e) {
      notify(String(e));
    }
  }


  function startEnrichmentPolling() {
    stopEnrichmentPolling();
    enrichRefreshCounter = 0;
    const rootV = rootSel.value;
    const pathV = pathInp.value;
    const key = rootV + ":" + pathV;
    lastEnrichKey = key;
    async function tick() {
      if (!lastEnrichKey || lastEnrichKey !== key) return;
      try {
        const url = `/api/import_wizard/enrichment_status?root=${encodeURIComponent(rootV)}&path=${encodeURIComponent(pathV)}`;
        const st = await API.getJson(url);
        if (st && st.state && st.state !== "idle" && st.state !== "done") {
          const total = Number(st.total_items || 0);
          const scanned = Number(st.scanned_items || 0);
          statusBox.textContent = `Index loaded. Background scan: ${st.state} (${scanned}/${total}).`;
        } else if (st && st.last_error) {
          statusBox.textContent = `Index loaded. Background scan failed: ${st.last_error}`;
        } else {
          // done/idle: keep a stable message
          if (statusBox.textContent.indexOf("Background scan") !== -1) {
            statusBox.textContent = "Index loaded. Select author.";
          }
        }

        // When running, refresh index occasionally to show progressive enrichment.
        if (st && st.state === "running") {
          enrichRefreshCounter += 1;
          if (enrichRefreshCounter >= 5) {
            enrichRefreshCounter = 0;
            await loadIndex("poll");
          }
        } else if (st && st.state === "done") {
          // Done: stop polling and do one final refresh to show enriched data.
          stopEnrichmentPolling();
          await loadIndex("done");
          return;
        } else if (st && st.state === "idle") {
          // Idle: nothing to poll.
          stopEnrichmentPolling();
          return;
        }
      } catch (e) {
        // Do not spam notifications; keep UI responsive.
        return;
      }
    }
    void tick();
    enrichTimer = setInterval(() => { void tick(); }, 1000);
  }
  run1Btn.addEventListener("click", () => { void doRunPending(1); });
  run5Btn.addEventListener("click", () => { void doRunPending(5); });

  
  async function loadIndex(trigger) {
    try {
      setBusy(true);
      const rootV = rootSel.value;
      const pathV = pathInp.value;
      const url = `/api/import_wizard/index?root=${encodeURIComponent(rootV)}&path=${encodeURIComponent(pathV)}`;
      indexData = await API.getJson(url);
      await loadProcessedRegistry();
      selectedAuthor = "";
      jobIds = [];
      clear(jobsTableWrap);
      renderAuthors();
      renderBooks();
      const deep = indexData && indexData.deep_scan_state ? indexData.deep_scan_state : null;
      if (deep && deep.state && deep.state !== "idle" && deep.state !== "done") {
        statusBox.textContent = `Index loaded. Background scan: ${deep.state}.`;
      } else {
        statusBox.textContent = "Index loaded. Select author.";
      }
      if (deep && deep.state === "running") {
        startEnrichmentPolling();
      } else {
        stopEnrichmentPolling();
      }
    } catch (e) {
      notify(String(e));
      statusBox.textContent = String(e);
    } finally {
      setBusy(false);
    }
  }

  function scheduleIndex() {
    if (indexTimer) { clearTimeout(indexTimer); indexTimer = null; }
    indexTimer = setTimeout(() => { void loadIndex("auto"); }, 350);
  }

  rootSel.addEventListener("change", scheduleIndex);
  pathInp.addEventListener("input", scheduleIndex);

  loadBtn.addEventListener("click", () => { void loadIndex("manual"); });

  await loadRoots();
  void loadIndex("auto");
  return root;
}

  
async function renderPluginManager(content, notify) {
  const wrap = el("div");
  const header = el("div", { class: "row" });
  const refreshBtn = el("button", { class: "btn", text: "Refresh" });
  header.appendChild(refreshBtn);
  // upload
  const up = el("input", { type: "file" });
  up.multiple = true;
  up.setAttribute("webkitdirectory", "");
  up.setAttribute("directory", "");
  header.appendChild(up);
  const uploadBtn = el("button", { class: "btn", text: "Upload .zip" });
  header.appendChild(uploadBtn);
  wrap.appendChild(header);

  const tableBox = el("div");
  wrap.appendChild(tableBox);

  async function load() {
    tableBox.innerHTML = "";
    let data;
    try {
      data = await API.getJson(content.source?.path || "/api/plugins");
    } catch (e) {
      tableBox.appendChild(el("div", { class: "hint", text: String(e) }));
      return;
    }
    const items = Array.isArray(data.items) ? data.items : [];
    const table = el("table", { class: "table" });
    const thead = el("thead");
    const trh = el("tr");
    ["name","version","source","enabled","interfaces","actions"].forEach((h)=>trh.appendChild(el("th",{text:h})));
    thead.appendChild(trh);
    table.appendChild(thead);
    const tbody = el("tbody");
    for (const p of items) {
      const tr = el("tr");
      tr.appendChild(el("td",{text:p.name||""}));
      tr.appendChild(el("td",{text:p.version||""}));
      tr.appendChild(el("td",{text:p.source||""}));
      tr.appendChild(el("td",{text:String(!!p.enabled)}));
      tr.appendChild(el("td",{text:Array.isArray(p.interfaces)?p.interfaces.join(", "):""}));
      const actions = el("td");
      const enBtn = el("button",{class:"btn", text: p.enabled ? "Disable" : "Enable"});
      enBtn.addEventListener("click", async ()=>{
        try{
          await API.sendJson("POST", `/api/plugins/${encodeURIComponent(p.name)}/${p.enabled ? "disable" : "enable"}`, {});
          await load();
        } catch(e){ notify(String(e)); }
      });
      const delBtn = el("button",{class:"btn danger", text:"Delete"});
      if (p.source !== "user") {
        delBtn.disabled = true;
      } else {
        delBtn.addEventListener("click", async ()=>{
          if (!confirm(`Delete plugin '${p.name}'?`)) return;
          try{
            await API.sendJson("DELETE", `/api/plugins/${encodeURIComponent(p.name)}`, undefined);
            await load();
          } catch(e){ notify(String(e)); }
        });
      }
      actions.appendChild(enBtn);
      actions.appendChild(delBtn);
      tr.appendChild(actions);
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    tableBox.appendChild(table);
  }

  refreshBtn.addEventListener("click", load);
  uploadBtn.addEventListener("click", async ()=>{
    if (!up.files || !up.files[0]) { notify("Select a zip file."); return; }
    const fd = new FormData();
    fd.append("file", up.files[0], up.files[0].name);
    try{
      const r = await fetch(content.upload?.path || "/api/plugins/upload", { method:"POST", body: fd });
      if (!r.ok) throw new Error(`Upload failed: ${r.status}`);
      notify("Uploaded.");
      up.value = "";
      await load();
    } catch(e){ notify(String(e)); }
  });

  await load();
  return wrap;
}

async function renderStageManager(content, notify) {
  const wrap = el("div");
  const header = el("div", { class: "row" });
  const refreshBtn = el("button", { class: "btn", text: "Refresh" });
  header.appendChild(refreshBtn);
  const up = el("input", { type: "file" });
  up.multiple = true;
  up.setAttribute("webkitdirectory", "");
  up.setAttribute("directory", "");
  header.appendChild(up);
  const uploadBtn = el("button", { class: "btn", text: "Upload" });
  header.appendChild(uploadBtn);
  wrap.appendChild(header);

  const info = el("div", { class: "hint" });
  wrap.appendChild(info);

  const tableBox = el("div");
  wrap.appendChild(tableBox);

  async function load() {
    tableBox.innerHTML = "";
    let data;
    try{
      data = await API.getJson(content.list_path || "/api/stage");
    } catch(e){ tableBox.appendChild(el("div",{class:"hint", text:String(e)})); return; }
    if (data.dir) {
      info.textContent = data.dir ? `Dir: ${data.dir}` : "";
      info.style.display = "block";
    } else {
      info.textContent = "";
      info.style.display = "none";
    }
    const items = Array.isArray(data.items)?data.items:[];
    const table = el("table", { class: "table" });
    const thead = el("thead");
    const trh = el("tr");
    ["name","size","mtime_ts","actions"].forEach((h)=>trh.appendChild(el("th",{text:h})));
    thead.appendChild(trh);
    table.appendChild(thead);
    const tbody = el("tbody");
    for (const f of items) {
      const tr = el("tr");
      tr.appendChild(el("td",{text:f.name||""}));
      tr.appendChild(el("td",{text:String(f.size||0)}));
      tr.appendChild(el("td",{text:fmtTs(f.mtime_ts)}));
      const actions = el("td");
      const delBtn = el("button",{class:"btn danger", text:"Delete"});
      delBtn.addEventListener("click", async ()=>{
        if (!confirm(`Delete '${f.name}'?`)) return;
        try{
          await API.sendJson("DELETE", `/api/stage/${encodeURIComponent(f.name)}`, undefined);
          await load();
        } catch(e){ notify(String(e)); }
      });
      actions.appendChild(delBtn);
      tr.appendChild(actions);
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    tableBox.appendChild(table);
  }

  refreshBtn.addEventListener("click", load);
  uploadBtn.addEventListener("click", async ()=>{
  if (!up.files || up.files.length === 0) { notify("Select files or a directory."); return; }
  const fd = new FormData();
  for (const f of up.files) {
    const rel = (f.webkitRelativePath && f.webkitRelativePath.length > 0) ? f.webkitRelativePath : f.name;
    fd.append("files", f, f.name);
    fd.append("relpaths", rel);
  }
  try{
    const r = await fetch(content.upload_path || "/api/stage/upload", { method:"POST", body: fd });
    if (!r.ok) throw new Error(`Upload failed: ${r.status}`);
    notify("Uploaded.");
    up.value = "";
    await load();
  } catch(e){ notify(String(e)); }
});


  await load();
  return wrap;
}

async function renderAmConfig(content, notify) {
  const wrap = el("div");

  const BASIC_FIELDS = [
    { key: "web.host", label: "Web host" },
    { key: "web.port", label: "Web port" },
    { key: "web.upload_dir", label: "Web upload dir" },
    { key: "inbox_dir", label: "Inbox dir" },
    { key: "outbox_dir", label: "Outbox dir" },
    { key: "stage_dir", label: "Stage dir" },
    { key: "logging.level", label: "Logging level" },
  ];

  function formatValue(v, pretty) {
    if (v === null) return "null";
    if (v === undefined) return "";
    try {
      if (typeof v === "string") return v;
      if (typeof v === "number") return String(v);
      if (typeof v === "boolean") return v ? "true" : "false";
      if (typeof v === "object") return JSON.stringify(v, null, pretty ? 2 : 0);
      return String(v);
    } catch {
      return String(v);
    }
  }

  function parseInputValue(raw) {
    const text = String(raw || "");
    try {
      return JSON.parse(text);
    } catch {
      // Allow plain strings without forcing JSON quoting.
      return text;
    }
  }

  function getEntry(snap, keyPath) {
    if (!snap || typeof snap !== "object") return { value: undefined, source: "" };
    const e = snap[keyPath];
    if (!e || typeof e !== "object") return { value: undefined, source: "" };
    return { value: e.value, source: String(e.source || "") };
  }

  async function apiSet(keyPath, rawValue) {
    const value = parseInputValue(rawValue);
    await API.sendJson("POST", "/api/am/config/set", { key_path: keyPath, value });
  }

  async function apiReset(keyPath) {
    await API.sendJson("POST", "/api/am/config/unset", { key_path: keyPath });
  }

  function sourceBadge(source) {
    const cls = source === "user_config" ? "badge badgeUser" : "badge badgeOther";
    const text = source || "(unknown)";
    return el("span", { class: cls, text });
  }

  function buildRow(keyPath, label, entry, onActionDone) {
    const valueText = formatValue(entry.value, false);
    const valueBox = el("div", { class: "configValue", text: valueText });

    const sourceBox = el("div", { class: "configSource" }, [sourceBadge(entry.source)]);

    const input = el("input", { class: "input", placeholder: "new value (JSON or string)" });

    const setBtn = el("button", { class: "btnPrimary", text: "Set" });
    const resetBtn = el("button", { class: "btn", text: "Reset" });

    setBtn.addEventListener("click", async () => {
      try {
        await apiSet(keyPath, input.value);
        notify("Saved.");
        input.value = "";
        await onActionDone();
      } catch (e) {
        notify(String(e));
      }
    });

    resetBtn.addEventListener("click", async () => {
      try {
        await apiReset(keyPath);
        notify("Reset.");
        input.value = "";
        await onActionDone();
      } catch (e) {
        notify(String(e));
      }
    });

    const actions = el("div", { class: "toolbar" }, [setBtn, resetBtn]);

    const left = el("div", { class: "configColKey" }, [
      el("div", { class: "configKey", text: keyPath }),
      el("div", { class: "configLabel", text: label || "" }),
    ]);

    const mid = el("div", { class: "configColValue" }, [valueBox, sourceBox]);
    const right = el("div", { class: "configColEdit" }, [input, actions]);

    return el("div", { class: "configRow" }, [left, mid, right]);
  }

  function groupByPrefix(keys) {
    const out = {};
    for (const k of keys) {
      const idx = k.indexOf(".");
      const prefix = idx > 0 ? k.slice(0, idx) : "(root)";
      if (!out[prefix]) out[prefix] = [];
      out[prefix].push(k);
    }
    for (const p of Object.keys(out)) out[p].sort();
    return out;
  }

  const topRow = el("div", { class: "toolbar" });
  const refreshBtn = el("button", { class: "btn", text: "Refresh" });
  topRow.appendChild(refreshBtn);
  wrap.appendChild(topRow);

  const basicTitle = el("div", { class: "subTitle", text: "Basic configuration" });
  const basicBox = el("div", { class: "configBox" });
  wrap.appendChild(basicTitle);
  wrap.appendChild(basicBox);

  const advTitleRow = el("div", { class: "toolbar" }, [
    el("div", { class: "subTitle", text: "Advanced configuration" }),
  ]);
  wrap.appendChild(advTitleRow);

  const advControls = el("div", { class: "toolbar" });
  const searchIn = el("input", { class: "input", placeholder: "Search key_path" });
  const overridesOnly = el("input", { type: "checkbox" });
  const overridesLabel = el("label", { class: "toggle" }, [
    overridesOnly,
    el("span", { text: "Show overrides only" }),
  ]);
  advControls.appendChild(searchIn);
  advControls.appendChild(overridesLabel);
  wrap.appendChild(advControls);

  const advBox = el("div", { class: "configBox" });
  wrap.appendChild(advBox);

  const rawTitle = el("div", { class: "subTitle", text: "Raw effective_snapshot" });
  const rawPre = el("pre", { class: "codeBlock", text: "" });
  const rawDetails = el("details", { class: "configDetails" }, [
    el("summary", { text: "Show raw snapshot" }),
    rawPre,
  ]);
  wrap.appendChild(rawDetails);

  let lastSnap = {};

  function renderBasic(snap) {
    clear(basicBox);
    const hint = el("div", {
      class: "hint",
      text: "Set writes a user override. Reset removes the user override (inherit).",
    });
    basicBox.appendChild(hint);

    for (const f of BASIC_FIELDS) {
      const entry = getEntry(snap, f.key);
      basicBox.appendChild(buildRow(f.key, f.label, entry, async () => { await load(); }));
    }
  }

  function renderAdvanced(snap) {
    clear(advBox);

    const allKeys = Object.keys(snap || {}).sort();
    const query = (searchIn.value || "").trim().toLowerCase();
    const onlyOverrides = !!overridesOnly.checked;

    let keys = allKeys;
    if (query) {
      keys = keys.filter((k) => k.toLowerCase().includes(query));
    }
    if (onlyOverrides) {
      keys = keys.filter((k) => {
        const e = getEntry(snap, k);
        return e.source === "user_config";
      });
    }

    if (!keys.length) {
      advBox.appendChild(el("div", { class: "hint", text: "(no entries)" }));
      return;
    }

    const grouped = groupByPrefix(keys);
    const prefixes = Object.keys(grouped).sort();

    for (const prefix of prefixes) {
      const section = el("details", { class: "configGroup" });
      section.open = true;
      section.appendChild(el("summary", { text: prefix }));
      const body = el("div");
      for (const k of grouped[prefix]) {
        const e = getEntry(snap, k);
        body.appendChild(buildRow(k, "", e, async () => { await load(); }));
      }
      section.appendChild(body);
      advBox.appendChild(section);
    }
  }

  async function load() {
    const data = await API.getJson("/api/am/config");
    const snap = data ? data.effective_snapshot : undefined;
    if (!snap || typeof snap !== "object") {
      throw new Error("effective_snapshot must be an object");
    }
    lastSnap = snap;
    rawPre.textContent = JSON.stringify(snap, null, 2) + "\n";
    renderBasic(snap);
    renderAdvanced(snap);
  }

  refreshBtn.addEventListener("click", async () => {
    try { await load(); } catch (e) { notify(String(e)); }
  });

  searchIn.addEventListener("input", () => {
    try { renderAdvanced(lastSnap); } catch { /* ignore */ }
  });

  overridesOnly.addEventListener("change", () => {
    try { renderAdvanced(lastSnap); } catch { /* ignore */ }
  });

  await load();
  return wrap;
}


async function renderJobsLogViewer(content, notify) {
  const root = el("div", { class: "wizardManager" });

  const header = el("div", { class: "toolbar" }, [
    el("button", { class: "btn", text: "Refresh" }),
  ]);

  const listPane = el("div", { class: "wizardList" });
  const detailPane = el("div", { class: "wizardDetail" });
  const logPane = el("div", { class: "wizardYaml" });
  const main = el("div", { class: "wizardGrid" }, [
    el("div", { class: "wizardCol" }, [listPane]),
    el("div", { class: "wizardColWide" }, [detailPane, logPane]),
  ]);

  root.appendChild(header);
  root.appendChild(main);

  let currentJobId = null;
  let currentOffset = 0;

  function renderJobList(items) {
    clear(listPane);
    if (!items.length) {
      listPane.appendChild(el("div", { class: "hint", text: "No jobs." }));
      return;
    }
    for (const j of items) {
      const jid = j.job_id || j.id || "";
      const label = `${jid} (${j.state || ""})`;
      const row = el("div", { class: "stepRow", text: label });
      row.addEventListener("click", async ()=>{
        currentJobId = jid;
        currentOffset = 0;
        await loadJob();
      });
      listPane.appendChild(row);
    }
  }

  async function loadList() {
    const data = await API.getJson("/api/jobs");
    const items = Array.isArray(data.items) ? data.items : [];
    renderJobList(items);
  }

  async function loadJob() {
    clear(detailPane);
    clear(logPane);
    if (!currentJobId) {
      detailPane.appendChild(el("div", { class: "hint", text: "Select a job." }));
      return;
    }
    const job = await API.getJson(`/api/jobs/${encodeURIComponent(currentJobId)}`);
    const item = job.item || {};
    detailPane.appendChild(el("div", { class: "subTitle", text: "Job" }));
    detailPane.appendChild(el("pre", { class: "codeBlock", text: JSON.stringify(item, null, 2) }));

    const logHdr = el("div", { class: "toolbar" });
    const moreBtn = el("button", { class: "btn", text: "Load more" });
    logHdr.appendChild(moreBtn);
    logPane.appendChild(logHdr);
    const pre = el("pre", { class: "logBox", text: "" });
    logPane.appendChild(pre);

    async function appendLog() {
      const r = await API.getJson(`/api/jobs/${encodeURIComponent(currentJobId)}/log?offset=${currentOffset}`);
      pre.textContent += (r.text || "");
      currentOffset = r.next_offset || currentOffset;
      pre.scrollTop = pre.scrollHeight;
    }

    moreBtn.addEventListener("click", async ()=>{
      try { await appendLog(); } catch(e){ notify(String(e)); }
    });

    await appendLog();
  }

  header.firstChild.addEventListener("click", async ()=>{
    try {
      await loadList();
      await loadJob();
    } catch(e) {
      notify(String(e));
    }
  });

  await loadList();
  await loadJob();
  return root;
}

async function renderWizardManager(content, notify) {
  // content is the card body element provided by the layout renderer
  const root = el("div", { class: "wizardManager" });

  const header = el("div", { class: "toolbar" }, [
    el("button", { class: "btn", text: "Refresh" }),
    el("button", { class: "btn", text: "New wizard" }),
  ]);

  const listPane = el("div", { class: "wizardList" });
  const detailPane = el("div", { class: "wizardDetail" });
  const editorPane = el("div", { class: "wizardEditor" });
  const yamlPane = el("div", { class: "wizardYaml" });

  const main = el("div", { class: "wizardGrid" }, [
    el("div", { class: "wizardCol" }, [listPane]),
    el("div", { class: "wizardColWide" }, [detailPane, editorPane, yamlPane]),
  ]);

  root.appendChild(header);
  root.appendChild(main);

  let currentName = null;
  let currentModel = null;

  function setYamlText(txt) {
    clear(yamlPane);
    yamlPane.appendChild(el("div", { class: "subTitle", text: "YAML preview" }));
    yamlPane.appendChild(el("pre", { class: "codeBlock", text: txt || "" }));
  }

  async function refreshYamlPreview() {
    if (!currentModel) return;
    try {
      const r = await API.sendJson("POST", "/api/wizards/preview", { model: currentModel });
      setYamlText(r.yaml || "");
    } catch (e) {
      setYamlText("Preview failed: " + String(e));
    }
  }

  function renderStepEditor(stepIndex) {
    clear(editorPane);
    if (!currentModel || !currentModel.wizard) return;

    const steps = currentModel.wizard.steps || [];
    const s = steps[stepIndex];
    if (!s) return;

    editorPane.appendChild(el("div", { class: "subTitle", text: `Step ${stepIndex + 1}` }));

    const idIn = el("input", { class: "input", value: String(s.id || "") });
    const typeIn = el("input", { class: "input", value: String(s.type || "") });
    const promptIn = el("input", { class: "input", value: String(s.prompt || s.label || "") });

    const enabledIn = el("input", { type: "checkbox" });
    enabledIn.checked = (s.enabled !== false);

    // Templates are stored under wizard._ui.templates (dict: name -> step partial).
    const tmplSel = el("select", { class: "input" });
    tmplSel.appendChild(el("option", { value: "", text: "(no template)" }));
    const wiz = currentModel && currentModel.wizard ? currentModel.wizard : null;
    const tmplMap = (wiz && wiz._ui && wiz._ui.templates && typeof wiz._ui.templates === "object") ? wiz._ui.templates : {};
    Object.keys(tmplMap || {}).sort().forEach((k) => {
      tmplSel.appendChild(el("option", { value: k, text: k }));
    });
    tmplSel.value = String(s.template || "");

    const defaultsTa = el("textarea", { class: "textarea", text: JSON.stringify(s.defaults || {}, null, 2) });
    const whenTa = el("textarea", { class: "textarea", text: s.when != null ? JSON.stringify(s.when, null, 2) : "" });

    const mkRow = (label, inputEl) =>
      el("div", { class: "formRow" }, [el("div", { class: "formLabel", text: label }), inputEl]);

    editorPane.appendChild(mkRow("id", idIn));
    editorPane.appendChild(mkRow("type", typeIn));
    editorPane.appendChild(mkRow("prompt/label", promptIn));
    editorPane.appendChild(mkRow("enabled", enabledIn));
    editorPane.appendChild(mkRow("template", tmplSel));

    editorPane.appendChild(el("div", { class: "subTitle", text: "defaults (JSON)" }));
    editorPane.appendChild(defaultsTa);
    editorPane.appendChild(el("div", { class: "subTitle", text: "when/conditions (JSON)" }));
    editorPane.appendChild(whenTa);

    const tmplBar = el("div", { class: "toolbar" });
    const applyTmplBtn = el("button", { class: "btn", text: "Apply template" });
    const saveTmplBtn = el("button", { class: "btn", text: "Save as template" });
    tmplBar.appendChild(applyTmplBtn);
    tmplBar.appendChild(saveTmplBtn);
    editorPane.appendChild(tmplBar);

    idIn.addEventListener("input", () => { s.id = idIn.value; refreshYamlPreview(); });
    typeIn.addEventListener("input", () => { s.type = typeIn.value; refreshYamlPreview(); });
    promptIn.addEventListener("input", () => { s.prompt = promptIn.value; s.label = promptIn.value; refreshYamlPreview(); });
    enabledIn.addEventListener("change", () => { s.enabled = !!enabledIn.checked; refreshYamlPreview(); });
    tmplSel.addEventListener("change", () => { s.template = tmplSel.value || ""; refreshYamlPreview(); });

    function parseJsonOrEmpty(txt, label) {
      const t = String(txt || "").trim();
      if (!t) return null;
      try { return JSON.parse(t); } catch (e) { throw new Error(`Invalid JSON for ${label}`); }
    }

    defaultsTa.addEventListener("input", () => {
      try {
        const v = parseJsonOrEmpty(defaultsTa.value, "defaults");
        s.defaults = (v === null) ? {} : v;
        refreshYamlPreview();
      } catch (e) { /* ignore while typing */ }
    });
    whenTa.addEventListener("input", () => {
      try {
        const v = parseJsonOrEmpty(whenTa.value, "when");
        if (v === null) delete s.when;
        else s.when = v;
        refreshYamlPreview();
      } catch (e) { /* ignore while typing */ }
    });

    applyTmplBtn.addEventListener("click", () => {
      const key = tmplSel.value;
      if (!key) return;
      const tpl = tmplMap && tmplMap[key] ? tmplMap[key] : null;
      if (!tpl) return;
      Object.keys(tpl).forEach((k) => {
        if (k === "id") return;
        s[k] = tpl[k];
      });
      // Refresh inputs from model
      renderStepEditor(stepIndex);
      refreshYamlPreview();
    });

    saveTmplBtn.addEventListener("click", () => {
      const key = (s.template && String(s.template).trim()) || prompt("Template name?");
      if (!key) return;
      currentModel.wizard._ui = currentModel.wizard._ui || {};
      currentModel.wizard._ui.templates = currentModel.wizard._ui.templates || {};
      const tpl = {};
      Object.keys(s).forEach((k) => {
        if (k === "id") return;
        if (k === "_ui") return;
        tpl[k] = s[k];
      });
      currentModel.wizard._ui.templates[key] = tpl;
      s.template = key;
      renderStepEditor(stepIndex);
      refreshYamlPreview();
    });

    const actions = el("div", { class: "toolbar" });
    const upBtn = el("button", { class: "btn", text: "Up" });
    const downBtn = el("button", { class: "btn", text: "Down" });
    const delBtn = el("button", { class: "btnDanger", text: "Delete step" });
    actions.appendChild(upBtn);
    actions.appendChild(downBtn);
    actions.appendChild(delBtn);
    editorPane.appendChild(actions);

    upBtn.addEventListener("click", () => {
      if (stepIndex <= 0) return;
      [steps[stepIndex - 1], steps[stepIndex]] = [steps[stepIndex], steps[stepIndex - 1]];
      renderDetail();
      renderStepEditor(stepIndex - 1);
      refreshYamlPreview();
    });
    downBtn.addEventListener("click", () => {
      if (stepIndex >= steps.length - 1) return;
      [steps[stepIndex + 1], steps[stepIndex]] = [steps[stepIndex], steps[stepIndex + 1]];
      renderDetail();
      renderStepEditor(stepIndex + 1);
      refreshYamlPreview();
    });
    delBtn.addEventListener("click", () => {
      steps.splice(stepIndex, 1);
      renderDetail();
      refreshYamlPreview();
    });
  }

  function renderDetail() {
    clear(detailPane);
    clear(editorPane);
    clear(yamlPane);

    if (!currentModel || !currentModel.wizard) {
      detailPane.appendChild(el("div", { class: "hint", text: "Select a wizard." }));
      return;
    }

    const wiz = currentModel.wizard;

    detailPane.appendChild(el("div", { class: "subTitle", text: "Wizard" }));
    const nameIn = el("input", { class: "input", value: String(wiz.name || "") });
    const descIn = el("textarea", { class: "textarea", text: String(wiz.description || "") });

    const mkRow = (label, inputEl) =>
      el("div", { class: "formRow" }, [el("div", { class: "formLabel", text: label }), inputEl]);

    detailPane.appendChild(mkRow("Display name", nameIn));
    detailPane.appendChild(mkRow("Description", descIn));

    // defaults memory is stored under wizard._ui.defaults_memory
    wiz._ui = wiz._ui || {};
    if (!wiz._ui.defaults_memory) wiz._ui.defaults_memory = {};
    const dmTa = el("textarea", { class: "textarea", text: JSON.stringify(wiz._ui.defaults_memory || {}, null, 2) });
    detailPane.appendChild(el("div", { class: "subTitle", text: "Defaults memory (JSON)" }));
    detailPane.appendChild(dmTa);
    dmTa.addEventListener("input", () => {
      try {
        const t = String(dmTa.value || "").trim();
        wiz._ui.defaults_memory = t ? JSON.parse(t) : {};
        refreshYamlPreview();
      } catch (e) {
        // ignore while typing
      }
    });

    nameIn.addEventListener("input", () => { wiz.name = nameIn.value; refreshYamlPreview(); });
    descIn.addEventListener("input", () => { wiz.description = descIn.value; refreshYamlPreview(); });

    const stepsBox = el("div", { class: "stepsBox" });
    stepsBox.appendChild(el("div", { class: "subTitle", text: `Steps (${(wiz.steps || []).length})` }));

    const addBtn = el("button", { class: "btn", text: "Add step" });
    addBtn.addEventListener("click", () => {
      wiz.steps = wiz.steps || [];
      wiz.steps.push({ id: `step_${wiz.steps.length + 1}`, type: "text", prompt: "" });
      renderDetail();
      refreshYamlPreview();
    });
    stepsBox.appendChild(addBtn);

    (wiz.steps || []).forEach((s, idx) => {
      const label = `${s.id || ("step_" + (idx + 1))} : ${s.type || "unknown"}${(s.enabled === false) ? " [disabled]" : ""}`;
      const row = el("div", { class: "stepRow", text: label });
      row.dataset.stepIndex = String(idx);
      row.draggable = true;
      row.addEventListener("click", () => renderStepEditor(idx));

      row.addEventListener("dragstart", (ev) => {
        ev.dataTransfer.setData("text/plain", String(idx));
        ev.dataTransfer.effectAllowed = "move";
      });
      row.addEventListener("dragover", (ev) => {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
      });
      row.addEventListener("drop", (ev) => {
        ev.preventDefault();
        const from = parseInt(ev.dataTransfer.getData("text/plain") || "-1", 10);
        const to = idx;
        if (Number.isNaN(from) || from < 0 || from >= (wiz.steps || []).length) return;
        if (from === to) return;
        const arr = wiz.steps || [];
        const [it] = arr.splice(from, 1);
        arr.splice(to, 0, it);
        renderDetail();
        renderStepEditor(to);
        refreshYamlPreview();
      });

      stepsBox.appendChild(row);
    });

    detailPane.appendChild(stepsBox);

    const saveBar = el("div", { class: "toolbar" });
    const saveBtn = el("button", { class: "btnPrimary", text: "Save" });
    const delBtn = el("button", { class: "btnDanger", text: "Delete wizard" });
    saveBar.appendChild(saveBtn);
    saveBar.appendChild(delBtn);
    detailPane.appendChild(saveBar);

    saveBtn.addEventListener("click", async () => {
      if (!currentName) return;
      try {
        // Validate on server before saving (safe-save contract).
        await API.sendJson("POST", "/api/wizards/validate", { model: currentModel });

        await API.sendJson("PUT", `/api/wizards/${encodeURIComponent(currentName)}`, { model: currentModel });
        notify(`Saved wizard: ${currentName}`);
        await loadList();
      } catch (e) {
        notify(`Save failed: ${String(e)}`);
      }
    });

    delBtn.addEventListener("click", async () => {
      if (!currentName) return;
      try {
        await API.sendJson("DELETE", `/api/wizards/${encodeURIComponent(currentName)}`);
        notify(`Deleted wizard: ${currentName}`);
        currentName = null;
        currentModel = null;
        await loadList();
        renderDetail();
      } catch (e) {
        notify(`Delete failed: ${String(e)}`);
      }
    });

    refreshYamlPreview();
  }

  async function loadDetail(name) {
    currentName = name;
    try {
      const w = await API.getJson(`/api/wizards/${encodeURIComponent(name)}`);
      currentModel = w.model || null;
      if (!currentModel) currentModel = { wizard: { name: name, description: "", steps: [] } };
      renderDetail();
    } catch (e) {
      currentModel = null;
      clear(detailPane);
      detailPane.appendChild(el("div", { class: "error", text: String(e) }));
    }
  }

  async function loadList() {
    clear(listPane);
    listPane.appendChild(el("div", { class: "hint", text: "Loading..." }));
    const r = await API.getJson("/api/wizards");
    const items = r.items || [];
    clear(listPane);

    items.forEach((w) => {
      const wizName = (w && (w.name || w.filename || w.id || w.title)) || "";
      const count = (w && (w.step_count != null ? w.step_count : "?")) ?? "?";
      const row = el("div", { class: "wizardItem", text: `${wizName} (${count})` });
      row.addEventListener("click", () => loadDetail(wizName));
      listPane.appendChild(row);
    });
  }

  header.children[0].addEventListener("click", () => loadList());
  header.children[1].addEventListener("click", async () => {
    const name = prompt("New wizard name (filename without .yaml):");
    if (!name) return;
    const yaml = "wizard:\n  name: \"" + name + "\"\n  description: \"\"\n  steps:\n    - id: step_1\n      type: text\n      prompt: \"\"\n";
    try {
      await API.sendJson("POST", "/api/wizards", { name: name, yaml: yaml });
      await loadList();
      await loadDetail(name);
    } catch (e) {
      notify(`Create failed: ${String(e)}`);
    }
  });

  await loadList();
  renderDetail();  return root;
}

async function renderRootBrowser(content, notify) {
  const root = el("div", { class: "rootBrowser" });

  const header = el("div", { class: "row" });
  const rootsSel = el("select");
  const pathInp = el("input", { type: "text", value: ".", placeholder: "path" });
  const upBtn = el("button", { class: "btn", text: "Up" });
  const refreshBtn = el("button", { class: "btn", text: "Refresh" });
  header.appendChild(rootsSel);
  header.appendChild(pathInp);
  header.appendChild(upBtn);
  header.appendChild(refreshBtn);
  root.appendChild(header);

  const listBox = el("div", { class: "fileList" });
  root.appendChild(listBox);

  const wizRow = el("div", { class: "row" });
  const wizSel = el("select");
  const modeSel = el("select");
  modeSel.appendChild(el("option", { value: "per", text: "Job per selection" }));
  modeSel.appendChild(el("option", { value: "batch", text: "Single batch job" }));
  const runBtn = el("button", { class: "btn", text: "Run" });
  wizRow.appendChild(wizSel);
  wizRow.appendChild(modeSel);
  wizRow.appendChild(runBtn);
  root.appendChild(wizRow);

  const formBox = el("div", { class: "wizardForm" });
  root.appendChild(formBox);

  let currentRoot = "";
  let currentPath = ".";
  let selected = new Set();
  let wizardModel = null;

  async function loadRoots() {
    const data = await API.getJson("/api/roots");
    const items = Array.isArray(data.items) ? data.items : [];
    clear(rootsSel);
    items.forEach((it) => {
      const id = it && (it.id ?? it.name ?? "");
      const label = it && (it.label ?? it.name ?? it.id ?? "");
      rootsSel.appendChild(el("option", { value: id, text: label }));
    });
    const first = items[0] || null;
    currentRoot = first ? (first.id ?? first.name ?? "") : "";
    rootsSel.value = currentRoot;
  }

  async function loadWizards() {
    const data = await API.getJson("/api/wizards");
    const items = Array.isArray(data.items) ? data.items : [];
    clear(wizSel);
    wizSel.appendChild(el("option", { value: "", text: "Select wizard" }));
    items.forEach((it) => {
      const label = it.display_name || it.name;
      wizSel.appendChild(el("option", { value: it.name, text: label }));
    });
  }

  function normPath(p) {
    p = String(p || ".").trim();
    if (!p) return ".";
    p = p.replace(/^\/+/, "");
    const parts = p.split("/").filter((x) => x && x !== ".");
    if (parts.some((x) => x === "..")) throw new Error("invalid path");
    return parts.length ? parts.join("/") : ".";
  }

  async function loadDir() {
    if (!currentRoot) return;
    currentPath = normPath(pathInp.value);
    pathInp.value = currentPath;
    selected = new Set();
    const url = `/api/fs/list?root=${encodeURIComponent(currentRoot)}&path=${encodeURIComponent(currentPath)}&recursive=0`;
    const data = await API.getJson(url);
    const items = Array.isArray(data.items) ? data.items : [];
    items.sort((a, b) => {
      const ad = a.is_dir ? 0 : 1;
      const bd = b.is_dir ? 0 : 1;
      if (ad !== bd) return ad - bd;
      return String(a.path).localeCompare(String(b.path));
    });
    clear(listBox);

    const curRow = el("div", { class: "fileRow" });
    const curChk = el("input", { type: "checkbox" });
    curChk.addEventListener("change", () => {
      const key = currentPath;
      if (curChk.checked) selected.add(key);
      else selected.delete(key);
    });
    curRow.appendChild(curChk);
    curRow.appendChild(el("span", { class: "fileName", text: "[current directory]" }));
    listBox.appendChild(curRow);

    items.forEach((it) => {
      const row = el("div", { class: "fileRow" });
      const chk = el("input", { type: "checkbox" });
      chk.addEventListener("change", () => {
        if (chk.checked) selected.add(it.path);
        else selected.delete(it.path);
      });
      const name = it.path.split("/").pop();
      const nameEl = el("span", { class: "fileName", text: name });
      if (it.is_dir) {
        nameEl.classList.add("isDir");
        nameEl.style.cursor = "pointer";
        nameEl.addEventListener("click", async () => {
          pathInp.value = it.path;
          await loadDir();
        });
      }
      row.appendChild(chk);
      row.appendChild(nameEl);
      listBox.appendChild(row);
    });
  }

  async function loadWizardModel() {
    wizardModel = null;
    clear(formBox);
    const id = wizSel.value;
    if (!id) return;
    const data = await API.getJson(`/api/wizards/${encodeURIComponent(id)}`);
    wizardModel = data && data.model ? data.model : null;
    const wiz = wizardModel && wizardModel.wizard ? wizardModel.wizard : null;
    const steps = wiz && Array.isArray(wiz.steps) ? wiz.steps : [];

    const title = (wiz && wiz.name) ? String(wiz.name) : id;
    formBox.appendChild(el("div", { class: "hint", text: `Wizard: ${title}` }));
    steps.forEach((s) => {
      const sid = s.id || s.key || "";
      if (!sid) return;
      const st = String(s.type || "input");
      const row = el("div", { class: "formRow" });
      row.appendChild(el("div", { class: "formLabel", text: sid }));
      if (st === "text") {
        row.appendChild(el("div", { class: "hint", text: String(s.prompt || "") }));
      } else if (st === "confirm") {
        const inp = el("input", { type: "checkbox" });
        inp.dataset.stepId = sid;
        row.appendChild(inp);
        row.appendChild(el("span", { class: "hint", text: String(s.prompt || "") }));
      } else if (st === "choice" || st === "select") {
        const sel = el("select");
        sel.dataset.stepId = sid;
        const opts = Array.isArray(s.options) ? s.options : [];
        opts.forEach((o) => {
          const v = (typeof o === "string") ? o : String(o && o.value !== undefined ? o.value : "");
          const lbl = (typeof o === "string") ? o : String(o && o.label !== undefined ? o.label : v);
          sel.appendChild(el("option", { value: v, text: lbl }));
        });
        row.appendChild(sel);
      } else {
        const inp = el("input", { type: "text" });
        inp.dataset.stepId = sid;
        row.appendChild(inp);
        if (s.prompt) row.appendChild(el("span", { class: "hint", text: String(s.prompt) }));
      }
      formBox.appendChild(row);
    });
  }

  function collectPayload() {
    const payload = {};
    Array.from(formBox.querySelectorAll("input,select")).forEach((n) => {
      const sid = n.dataset.stepId;
      if (!sid) return;
      if (n.tagName.toLowerCase() === "input" && n.getAttribute("type") === "checkbox") {
        payload[sid] = !!n.checked;
      } else {
        payload[sid] = n.value;
      }
    });
    return payload;
  }

  rootsSel.addEventListener("change", async () => {
    currentRoot = rootsSel.value;
    pathInp.value = ".";
    await loadDir();
  });
  refreshBtn.addEventListener("click", () => loadDir());
  upBtn.addEventListener("click", async () => {
    const p = normPath(pathInp.value);
    if (p === ".") return;
    const parts = p.split("/");
    parts.pop();
    pathInp.value = parts.length ? parts.join("/") : ".";
    await loadDir();
  });
  pathInp.addEventListener("keydown", async (ev) => {
    if (ev.key === "Enter") await loadDir();
  });
  wizSel.addEventListener("change", () => loadWizardModel());

  runBtn.addEventListener("click", async () => {
    try {
      const wid = wizSel.value;
      if (!wid) throw new Error("select a wizard");
      if (!selected.size) throw new Error("select at least one target");
      const paths = Array.from(selected.values());
      const payload = collectPayload();
      const mode = modeSel.value;
      const jobIds = [];
      if (mode === "batch") {
        const body = {
          wizard_id: wid,
          targets: paths.map((p) => ({ root: currentRoot, path: p })),
          payload: payload,
        };
        const r = await API.sendJson("POST", "/api/jobs/wizard", body);
        await API.sendJson("POST", `/api/jobs/${encodeURIComponent(r.job_id)}/run`, {});
        jobIds.push(r.job_id);
      } else {
        for (const p of paths) {
          const body = { wizard_id: wid, target_root: currentRoot, target_path: p, payload: payload };
          const r = await API.sendJson("POST", "/api/jobs/wizard", body);
          await API.sendJson("POST", `/api/jobs/${encodeURIComponent(r.job_id)}/run`, {});
          jobIds.push(r.job_id);
        }
      }
      notify(`Started: ${jobIds.join(", ")}`);
    } catch (e) {
      notify(String(e));
    }
  });

  await loadRoots();
  await loadWizards();
  await loadDir();
  return root;
}

async function renderContent(content, notify) {
    const t = content.type;
    if (t === "stat_list") return await renderStatList(content);
    if (t === "table") return await renderTable(content);
    if (t === "log_stream") return await renderLogStream(content);
    if (t === "js_error_feed") return await renderJsErrorFeed(content, notify);
    if (t === "ui_debug_feed") return await renderUiDebugFeed(content, notify);
    if (t === "button_row") return await renderButtonRow(content, notify);
    if (t === "json_editor") return await renderJsonEditor(content, notify);
    if (t === "yaml_editor") return await renderYamlEditor(content, notify);
    if (t === "plugin_manager") return await renderPluginManager(content, notify);
    if (t === "stage_manager") return await renderStageManager(content, notify);
    if (t === "wizard_manager") return await renderWizardManager(content, notify);
    if (t === "root_browser") return await renderRootBrowser(content, notify);
    if (t === "am_config") return await renderAmConfig(content, notify);
    if (t === "jobs_log_viewer") return await renderJobsLogViewer(content, notify);
    if (t === "import_wizard") return await renderImportWizard(content, notify);
    return el("div", { class: "hint", text: `Unsupported content type: ${t}` });
  }

  async function renderLayout(layout, notify) {
  if (!layout || layout.type !== "grid") {
    return el("div", { class: "hint", text: "Unsupported layout." });
  }
  const cols = layout.cols || 12;
  const gap = layout.gap || 12;
  const grid = el("div", { class: "grid" });
  grid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
  grid.style.gap = `${gap}px`;

  const children = Array.isArray(layout.children) ? layout.children : [];
  for (const node of children) {
    const colSpan = node.colSpan || cols;

    const card = el("div", { class: "card" });
    card.style.gridColumn = `span ${colSpan}`;

    // Always render a title row (even if empty) to keep card padding/borders consistent.
    const titleText = (node.type === "card")
      ? (node.title || "")
      : (node.title || node.type || "");
    card.appendChild(el("div", { class: "cardTitle", text: titleText }));

    const body = el("div", { class: "cardBody" }, [
      el("div", { class: "hint", text: "Loading..." }),
    ]);
    card.appendChild(body);
    grid.appendChild(card);

    try {
      clear(body);
      const contentObj = (node.type === "card") ? (node.content || {}) : node;
      body.appendChild(await renderContent(contentObj, notify));
    } catch (e) {
      clear(body);
      body.appendChild(el("div", { class: "error", text: String(e) }));
    }
  }

  if (!children.length) {
    grid.appendChild(el("div", { class: "hint", text: "No layout children." }));
  }
  return grid;
}

async function loadNav() {
    try {
      const nav = await API.getJson("/api/ui/nav");
      return Array.isArray(nav.items) ? nav.items : [];
    } catch (e) {
      console.error(e);
      return [
        { title: "Dashboard", route: "/", page_id: "dashboard" },
      ];
    }
  }

  function routeToPageId(pathname, navItems) {
    const hit = navItems.find((i) => i.route === pathname);
    if (hit) return hit.page_id;
    // fallback: / -> dashboard
    if (pathname === "/") return "dashboard";
    // fallback to first item
    return navItems[0] ? navItems[0].page_id : "dashboard";
  }

  async function renderApp() {
    const root = document.getElementById("app");
    const toast = document.getElementById("toast");
    const notify = (msg) => {
      toast.textContent = msg;
      toast.classList.add("show");
      setTimeout(() => toast.classList.remove("show"), 2500);
    };

    const navItems = await loadNav();

    // Debug mode should expose everything through the UI (no DevTools required).
    const debugEnabled = Array.isArray(navItems) && navItems.some((i) => i && (i.page_id === "debug_js" || i.route === "/debug-js"));
    if (debugEnabled) {
      _amInstallDebugFetchCapture(notify);
    }

    const sidebar = el("div", { class: "sidebar" });
    sidebar.appendChild(el("div", { class: "brand", text: "AudioMason" }));
    const nav = el("div", { class: "nav" });
    navItems.forEach((item) => {
      const a = el("a", { class: "navItem", href: item.route, text: item.title });
      a.addEventListener("click", (ev) => {
        ev.preventDefault();
        history.pushState({}, "", item.route);
        renderRoute();
      });
      nav.appendChild(a);
    });
    sidebar.appendChild(nav);

    const main = el("div", { class: "main" });
    const header = el("div", { class: "header" }, [
      el("div", { class: "headerTitle", text: "" }),
      el("div", { class: "headerRight" }, [
        el("a", { class: "link", href: "/api/ui/schema", text: "schema" }),
      ]),
    ]);
    main.appendChild(header);
    const content = el("div", { class: "content" }, []);
    main.appendChild(content);

    clear(root);
    root.appendChild(sidebar);
    root.appendChild(main);

    async function renderRoute() {
      const pathname = window.location.pathname.replace(/\/+$/, "") || "/";
      // update active
      Array.from(nav.querySelectorAll(".navItem")).forEach((n) => {
        n.classList.toggle("active", n.getAttribute("href") === pathname);
      });

      const pageId = routeToPageId(pathname, navItems);
      let page;
      try {
        page = await API.getJson(`/api/ui/page/${encodeURIComponent(pageId)}`);
      } catch (e) {
        notify(String(e));
        page = { title: "Error", layout: { type: "grid", cols: 12, gap: 12, children: [] } };
      }

      header.querySelector(".headerTitle").textContent = page.title || pageId;
      clear(content);
      content.appendChild(await renderLayout(page.layout, notify));
    }

    window.addEventListener("popstate", () => { void renderRoute(); });
    await renderRoute();
  }

  try {
    await renderApp();
  } catch (e) {
    console.error(e);
    const root = document.getElementById('app') || document.body;
    root.innerHTML = '';
    const pre = document.createElement('pre');
    pre.style.whiteSpace = 'pre-wrap';
    pre.textContent = 'UI failed to start: ' + String(e);
    root.appendChild(pre);
  }
})();