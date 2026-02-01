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
      if (key && (key.endsWith("_ts") || key.includes("time"))) value = fmtTs(value);
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
        if (c.key && (c.key.endsWith("_ts") || c.key.includes("time"))) v = fmtTs(v);
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
        if (data && typeof data.path === "string") info.textContent = `Source: ${data.path}`;
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
    ["name","version","enabled","interfaces","actions"].forEach((h)=>trh.appendChild(el("th",{text:h})));
    thead.appendChild(trh);
    table.appendChild(thead);
    const tbody = el("tbody");
    for (const p of items) {
      const tr = el("tr");
      tr.appendChild(el("td",{text:p.name||""}));
      tr.appendChild(el("td",{text:p.version||""}));
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
      delBtn.addEventListener("click", async ()=>{
        if (!confirm(`Delete plugin '${p.name}'?`)) return;
        try{
          await API.sendJson("DELETE", `/api/plugins/${encodeURIComponent(p.name)}`, undefined);
          await load();
        } catch(e){ notify(String(e)); }
      });
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
    info.textContent = `Dir: ${data.dir || ""}`;
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

async function renderWizardManager(content, notify) {
  const wrap = el("div", { class: "wizardMgr" });
  const top = el("div", { class: "row" });
  const refreshBtn = el("button", { class: "btn", text: "Refresh" });
  top.appendChild(refreshBtn);
  const newBtn = el("button", { class: "btn", text: "New wizard" });
  top.appendChild(newBtn);
  wrap.appendChild(top);

  const body = el("div", { class: "wizardSplit" });
  const listBox = el("div", { class: "wizardList" });
  const editorBox = el("div", { class: "wizardEditor" });
  const stepsBox = el("div", { class: "wizardSteps" });
  body.appendChild(listBox);
  body.appendChild(editorBox);
  wrap.appendChild(body);

  const textarea = el("textarea", { class: "jsonEditor" });
  editorBox.appendChild(stepsBox);
  editorBox.appendChild(textarea);
  const saveRow = el("div", { class: "row" });
  const saveBtn = el("button", { class: "btn", text: "Save" });
  const delBtn = el("button", { class: "btn danger", text: "Delete" });
  saveRow.appendChild(saveBtn);
  saveRow.appendChild(delBtn);
  editorBox.appendChild(saveRow);

  let currentName = null;

  async function loadList() {
    listBox.innerHTML = "";
    let data;
    try { data = await API.getJson(content.list_path || "/api/wizards"); }
    catch(e){ listBox.appendChild(el("div",{class:"hint", text:String(e)})); return; }
    const items = Array.isArray(data.items)?data.items:[];
    for (const w of items) {
      const btn = el("div", { class: "wizardItem", text: `${w.filename} (${w.steps||0})` });
      btn.addEventListener("click", async ()=>{
        const name = (w.filename || "").replace(/\.yaml$/,"");
        currentName = name;
        try{
          const g = await API.getJson((content.get_path_tmpl||"/api/wizards/{name}").replace("{name}", encodeURIComponent(name)));
          textarea.value = (g.yaml || "") + (String(g.yaml||"").endsWith("\n") ? "" : "\n");
          stepsBox.innerHTML = "";
          try {
            const p = await API.getJson((content.parsed_path_tmpl||"/api/wizards/{name}/parsed").replace("{name}", encodeURIComponent(name)));
            const w = p && p.wizard ? p.wizard : null;
            let steps = (w && Array.isArray(w.steps)) ? w.steps : [];
            if (steps.length === 0 && p && Array.isArray(p.steps)) steps = p.steps;
            if (steps.length === 0) {
              stepsBox.appendChild(el("div", { class: "hint", text: "No steps (or unable to parse YAML)." }));
            } else {
              const h = el("div", { class: "hint", text: `Steps: ${steps.length}` });
              stepsBox.appendChild(h);
              for (let i=0;i<steps.length;i++) {
                const st = steps[i] || {};
                const label = st.name || st.title || st.type || `step_${i+1}`;
                stepsBox.appendChild(el("div", { class: "wizardStepItem", text: `${i+1}. ${label}` }));
              }
            }
          } catch(e) {
            stepsBox.appendChild(el("div", { class: "hint", text: String(e) }));
          }
        } catch(e){ notify(String(e)); }
      });
      listBox.appendChild(btn);
    }
  }

  refreshBtn.addEventListener("click", loadList);
  newBtn.addEventListener("click", ()=>{
    currentName = null;
    stepsBox.innerHTML = "";
    textarea.value = "# New wizard\nname: New Wizard\ndescription: \"\"\nsteps: []\n";
  });

  saveBtn.addEventListener("click", async ()=>{
    const text = String(textarea.value || "");
    try{
      if (currentName) {
        const path = (content.update_path_tmpl||"/api/wizards/{name}").replace("{name}", encodeURIComponent(currentName));
        await API.sendJson("PUT", path, { yaml: text });
        notify("Saved.");
      } else {
        const name = prompt("Wizard name (filename):", "new_wizard");
        if (!name) return;
        const r = await API.sendJson("POST", content.create_path||"/api/wizards", { name: name, yaml: text });
        notify("Created.");
        currentName = r.name || currentName;
      }
      await loadList();
    } catch(e){ notify(String(e)); }
  });
  });

  delBtn.addEventListener("click", async ()=>{
    if (!currentName) { notify("Select a wizard first."); return; }
    if (!confirm(`Delete wizard '${currentName}'?`)) return;
    try{
      const path = (content.delete_path_tmpl||"/api/wizards/{name}").replace("{name}", encodeURIComponent(currentName));
      await API.sendJson("DELETE", path, undefined);
      currentName = null;
      textarea.value = "";
      await loadList();
    } catch(e){ notify(String(e)); }
  });

  await loadList();
  return wrap;
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

    for (const node of (layout.children || [])) {
      if (node.type === "card") {
        const colSpan = node.colSpan || cols;
        const card = el("div", { class: "card" });
        card.style.gridColumn = `span ${colSpan}`;
        card.appendChild(el("div", { class: "cardTitle", text: node.title || "" }));
        const body = el("div", { class: "cardBody" }, [el("div", { class: "hint", text: "Loading..." })]);
        card.appendChild(body);
        grid.appendChild(card);

        try {
          clear(body);
          body.appendChild(await renderContent(node.content || {}, notify));
        } catch (e) {
          clear(body);
          body.appendChild(el("div", { class: "error", text: String(e) }));
        }
      }
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
        el("a", { class: "link", href: "/api/ui/page/dashboard", text: "schema" }),
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

    window.addEventListener("popstate", () => renderRoute());
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