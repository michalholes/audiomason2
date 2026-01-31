/* Minimal no-build renderer for server-driven pages.
   It renders a nav + a page schema from /api/ui/* . */

function qs(sel){ return document.querySelector(sel); }
function ce(tag, cls){ const el=document.createElement(tag); if(cls) el.className=cls; return el; }

async function fetchJson(path){
  const r = await fetch(path, {headers: {"Accept":"application/json"}});
  if(!r.ok) throw new Error(`HTTP ${r.status} for ${path}`);
  return await r.json();
}

function setActiveNav(route){
  document.querySelectorAll("#nav a").forEach(a=>{
    a.classList.toggle("active", a.getAttribute("data-route")===route);
  });
}

function renderStatList(container, data, fields){
  const wrap=ce("div","kv");
  for(const f of fields||[]){
    const item=ce("div","item");
    const label=ce("div","label"); label.textContent=f.label||f.key;
    const value=ce("div","value"); value.textContent = (data && f.key in data) ? String(data[f.key]) : "";
    item.appendChild(label); item.appendChild(value);
    wrap.appendChild(item);
  }
  container.appendChild(wrap);
}

function renderTable(container, rows, columns){
  const table=ce("table","table");
  const thead=ce("thead");
  const trh=ce("tr");
  for(const c of columns||[]){
    const th=ce("th"); th.textContent=c.header||c.key;
    trh.appendChild(th);
  }
  thead.appendChild(trh);
  table.appendChild(thead);

  const tbody=ce("tbody");
  for(const row of rows||[]){
    const tr=ce("tr");
    for(const c of columns||[]){
      const td=ce("td");
      td.textContent = (row && c.key in row) ? String(row[c.key]) : "";
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  container.appendChild(table);
}

async function renderContent(container, content){
  if(!content) return;
  const ctype = content.type;
  const src = content.source;

  if(ctype==="stat_list"){
    const data = src && src.type==="api" ? await fetchJson(src.path) : {};
    renderStatList(container, data, content.fields || []);
    return;
  }

  if(ctype==="table"){
    const data = src && src.type==="api" ? await fetchJson(src.path) : [];
    const rows = Array.isArray(data) ? data : (data.items || []);
    renderTable(container, rows, content.columns || []);
    return;
  }

  const p=ce("div","small");
  p.textContent = `Unsupported content type: ${ctype}`;
  container.appendChild(p);
}

async function renderNode(container, node){
  if(!node) return;
  if(node.type==="card"){
    const card=ce("section","card");
    const h=ce("h3"); h.textContent = node.title || "";
    card.appendChild(h);
    await renderContent(card, node.content);
    container.appendChild(card);
    return;
  }

  const p=ce("div","small");
  p.textContent = `Unsupported node type: ${node.type}`;
  container.appendChild(p);
}

async function renderPage(page){
  const main=qs("#main");
  main.innerHTML="";
  const title=ce("h2"); title.textContent = page.title || page.id || "";
  title.style.margin = "0 0 12px 0";
  main.appendChild(title);

  const layout = page.layout || {};
  const grid=ce("div","grid");
  // naive grid: single column; keep simple for MVP
  for(const child of (layout.children||[])){
    await renderNode(grid, child);
  }
  main.appendChild(grid);
}

async function loadNav(){
  const navData = await fetchJson("/api/ui/nav");
  const navEl=qs("#nav");
  navEl.innerHTML="";
  for(const item of navData.items||[]){
    const a=ce("a");
    a.href = item.route;
    a.setAttribute("data-route", item.route);
    a.textContent = item.title;
    a.addEventListener("click", (e)=>{
      e.preventDefault();
      history.pushState({}, "", item.route);
      route();
    });
    navEl.appendChild(a);
  }
}

async function route(){
  const path = location.pathname;
  // map route -> page_id using nav
  const navData = await fetchJson("/api/ui/nav");
  const match = (navData.items||[]).find(i=>i.route===path) || (navData.items||[])[0];
  if(!match){
    qs("#main").textContent = "No pages configured.";
    return;
  }
  setActiveNav(match.route);
  const page = await fetchJson(`/api/ui/page/${encodeURIComponent(match.page_id)}`);
  await renderPage(page);
}

async function init(){
  try{
    await loadNav();
    qs("#status").textContent = "ready";
    await route();
    window.addEventListener("popstate", route);
  }catch(e){
    qs("#status").textContent = "error";
    const main=qs("#main");
    main.innerHTML="";
    const pre=ce("pre");
    pre.textContent = String(e && e.stack ? e.stack : e);
    main.appendChild(pre);
  }
}
init();
