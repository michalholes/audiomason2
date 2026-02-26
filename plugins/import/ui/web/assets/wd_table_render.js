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

  function initTable(opts) {
    const body = opts && opts.body;
    const el = (opts && opts.el) || function () {};
    const text = (opts && opts.text) || function () {};
    const state = (opts && opts.state) || {};
    if (!body) return null;

    const rowById = {};

    function renderAll() {
      clear(body);
      const wd = state.getWizardDraft ? state.getWizardDraft() : {};
      const g = stableGraph(wd);
      const nodes = Array.isArray(g.nodes) ? g.nodes : [];
      const selected = state.getSelectedStepId ? state.getSelectedStepId() : null;

      nodes.forEach((sid, idx) => {
        const row = el("div", "wdRow");
        row.dataset.stepId = String(sid || "");
        row.classList.toggle("is-selected", String(selected || "") === String(sid || ""));

        const cellOrder = text("div", "wdCellOrder", String(idx + 1));
        const cellId = text("div", "wdCellId", String(sid || ""));
        const cellType = text(
          "div",
          "wdCellType",
          state.isOptional && state.isOptional(sid) ? "optional" : "mandatory"
        );
        const cellReq = text(
          "div",
          "wdCellReq",
          state.isOptional && state.isOptional(sid) ? "no" : "yes"
        );
        const cellActions = el("div", "wdCellActions");

        const btnSelect = text("button", "btn btnSmall", "Select");
        btnSelect.type = "button";
        btnSelect.addEventListener("click", function () {
          state.setSelectedStep && state.setSelectedStep(sid);
        });

        const btnRemove = text("button", "btn btnSmall", "Remove");
        btnRemove.type = "button";
        btnRemove.disabled = !(state.canRemove && state.canRemove(sid));
        btnRemove.classList.toggle("is-disabled", btnRemove.disabled);
        btnRemove.addEventListener("click", function () {
          state.removeStep && state.removeStep(sid);
        });

        cellActions.appendChild(btnSelect);
        cellActions.appendChild(btnRemove);

        row.appendChild(cellOrder);
        row.appendChild(cellId);
        row.appendChild(cellType);
        row.appendChild(cellReq);
        row.appendChild(cellActions);
        body.appendChild(row);
        rowById[String(sid || "")] = row;
      });
    }

    function updateSelection() {
      const selected = state.getSelectedStepId ? state.getSelectedStepId() : null;
      Object.keys(rowById).forEach((sid) => {
        const row = rowById[sid];
        if (!row) return;
        row.classList.toggle("is-selected", String(selected || "") === sid);
      });
    }

    return {
      renderAll: renderAll,
      updateSelection: updateSelection,
    };
  }

  window.AM2WDTableRender = {
    initTable: initTable,
  };
})();
