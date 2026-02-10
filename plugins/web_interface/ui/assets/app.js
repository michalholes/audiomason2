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
window.addEventListener('unhandledrejection', function(ev){
  try{
    var el=document.getElementById('app')||document.body;
    el.innerHTML='<pre style="white-space:pre-wrap;color:#fff;background:#600;padding:12px;font-family:monospace">PROMISE REJECTION: '+(ev.reason?String(ev.reason):'')+'</pre>';
  }catch(e){}
});
window.onerror = function(msg, src, line, col, err){
  try{
    var el=document.getElementById('app')||document.body;
    el.innerHTML='<pre style="white-space:pre-wrap;color:#fff;background:#600;padding:12px;font-family:monospace">JS ERROR: '+msg+'\n'+(err&&err.stack?err.stack:'')+'</pre>';
  }catch(e){}
};
(async function () {
  const API = {
    async getJson(path) {
      const r = await fetch(path, { headers: { "Accept": "application/json" } });
      if (!r.ok) throw new Error(`GET ${path} -> ${r.status}`);
      return await r.json();
    },
    async sendJson(method, path, body) {
      const r = await fetch(path, {
        method,
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!r.ok) {
        let detail = "";
        try { detail = (await r.text()).slice(0, 400); } catch {}
        throw new Error(`${method} ${path} -> ${r.status} ${detail}`);
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

    const mkRow = (label, inputEl) =>
      el("div", { class: "formRow" }, [el("div", { class: "formLabel", text: label }), inputEl]);

    editorPane.appendChild(mkRow("id", idIn));
    editorPane.appendChild(mkRow("type", typeIn));
    editorPane.appendChild(mkRow("prompt/label", promptIn));

    idIn.addEventListener("input", () => { s.id = idIn.value; refreshYamlPreview(); });
    typeIn.addEventListener("input", () => { s.type = typeIn.value; refreshYamlPreview(); });
    promptIn.addEventListener("input", () => { s.prompt = promptIn.value; s.label = promptIn.value; refreshYamlPreview(); });

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
      const label = `${s.id || ("step_" + (idx + 1))} : ${s.type || "unknown"}`;
      const row = el("div", { class: "stepRow", text: label });
      row.addEventListener("click", () => renderStepEditor(idx));
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

async function renderContent(content, notify) {
    const t = content.type;
    if (t === "stat_list") return await renderStatList(content);
    if (t === "table") return await renderTable(content);
    if (t === "log_stream") return await renderLogStream(content);
    if (t === "button_row") return await renderButtonRow(content, notify);
    if (t === "json_editor") return await renderJsonEditor(content, notify);
    if (t === "yaml_editor") return await renderYamlEditor(content, notify);
    if (t === "plugin_manager") return await renderPluginManager(content, notify);
    if (t === "stage_manager") return await renderStageManager(content, notify);
    if (t === "wizard_manager") return await renderWizardManager(content, notify);
    if (t === "am_config") return await renderAmConfig(content, notify);
    if (t === "jobs_log_viewer") return await renderJobsLogViewer(content, notify);
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