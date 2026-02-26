(function () {
  "use strict";

  const stableGraph =
    window.AM2WDGraphStable && window.AM2WDGraphStable.stableGraph
      ? window.AM2WDGraphStable.stableGraph
      : function () {
          return { version: 1, nodes: [], edges: [], entry: null };
        };

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function _summarizeWhen(whenVal) {
    if (whenVal === null || whenVal === undefined) return "<unconditional>";
    if (typeof whenVal === "boolean") return whenVal ? "true" : "false";
    if (typeof whenVal === "object") {
      const op = whenVal.op;
      const path = whenVal.path;
      if (typeof op === "string" && op && typeof path === "string" && path) {
        return op + ":" + path;
      }
      if (typeof op === "string" && op) return op;
    }
    return "<cond>";
  }

  function renderTransitions(opts) {
    const mount = opts && opts.mount;
    const el = (opts && opts.el) || function () {};
    const text = (opts && opts.text) || function () {};
    const state = (opts && opts.state) || {};
    if (!mount) return;

    clear(mount);

    const wd = state.getWizardDraft ? state.getWizardDraft() : {};
    const g = stableGraph(wd);
    const selected = state.getSelectedStepId ? state.getSelectedStepId() : null;
    const nodes = Array.isArray(g.nodes) ? g.nodes : [];
    const edges = Array.isArray(g.edges) ? g.edges : [];

    const panel = el("div", "flowTransPanel");
    const header = el("div", "flowTransHeader");
    header.appendChild(text("div", "flowTransTitle", "Transitions"));
    panel.appendChild(header);

    const body = el("div", "flowTransBody");
    panel.appendChild(body);
    mount.appendChild(panel);

    if (!selected) {
      body.appendChild(text("div", "flowTransEmpty", "Select a step to edit transitions."));
      return;
    }

    const outgoing = edges.filter(function (e) {
      return String(e.from_step_id || "") === String(selected);
    });

    const addWrap = el("div", "flowTransAdd");
    const toSel = el("select", "flowTransSelect");
    nodes.forEach(function (sid) {
      const opt = el("option", "");
      opt.value = String(sid || "");
      opt.textContent = String(sid || "");
      toSel.appendChild(opt);
    });
    const prio = el("input", "flowTransPrio");
    prio.type = "number";
    prio.value = "0";
    prio.min = "-99999";
    prio.max = "99999";
    const when = el("input", "flowTransWhen");
    when.type = "text";
    when.placeholder = "when JSON (optional)";
    const btnAdd = text("button", "btn btnSmall", "Add");
    btnAdd.type = "button";

    btnAdd.addEventListener("click", function () {
      const toId = String(toSel.value || "");
      const p = Number(prio.value || 0);
      let whenVal = null;
      const wtxt = String(when.value || "").trim();
      if (wtxt) {
        try {
          whenVal = JSON.parse(wtxt);
        } catch (e) {
          window.alert("Invalid when JSON");
          return;
        }
      }
      state.addEdge && state.addEdge(String(selected), toId, p, whenVal);
    });

    addWrap.appendChild(toSel);
    addWrap.appendChild(prio);
    addWrap.appendChild(when);
    addWrap.appendChild(btnAdd);
    body.appendChild(addWrap);

    if (!outgoing.length) {
      body.appendChild(text("div", "flowTransEmpty", "No outgoing transitions."));
      return;
    }

    outgoing
      .slice(0)
      .sort(function (a, b) {
        return Number(a.priority || 0) - Number(b.priority || 0);
      })
      .forEach(function (e, idx) {
        const row = el("div", "flowTransRow");
        row.appendChild(text("div", "flowTransTo", "to: " + String(e.to_step_id || "")));
        row.appendChild(text("div", "flowTransMeta", "prio: " + String(e.priority || 0)));
        row.appendChild(text("div", "flowTransMeta", _summarizeWhen(e.when)));

        const btnDel = text("button", "btn btnSmall", "Remove");
        btnDel.type = "button";
        btnDel.addEventListener("click", function () {
          state.removeEdge && state.removeEdge(String(selected), idx);
        });
        row.appendChild(btnDel);
        body.appendChild(row);
      });
  }

  window.AM2WDTransitionsRender = {
    renderTransitions: renderTransitions,
  };
})();
