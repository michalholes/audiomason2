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
    let dragStepId = null;
    let dropBeforeId = null;

    function renderAll() {
      clear(body);
      Object.keys(rowById).forEach((k) => delete rowById[k]);
      const wd = state.getWizardDraft ? state.getWizardDraft() : {};
      const g = stableGraph(wd);
      const nodes = Array.isArray(g.nodes) ? g.nodes : [];
      const selected = state.getSelectedStepId ? state.getSelectedStepId() : null;

      dragStepId = null;
      dropBeforeId = null;

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

        const btnUp = text("button", "btn btnSmall", "Up");
        btnUp.type = "button";
        btnUp.disabled = idx === 0 || !(state.moveStepUp && typeof state.moveStepUp === "function");
        btnUp.classList.toggle("is-disabled", btnUp.disabled);
        btnUp.addEventListener("click", function () {
          state.moveStepUp && state.moveStepUp(sid);
        });

        const btnDown = text("button", "btn btnSmall", "Down");
        btnDown.type = "button";
        btnDown.disabled =
        btnDown.disabled =
          idx === nodes.length - 1 ||
          !(state.moveStepDown && typeof state.moveStepDown === "function");
        btnDown.classList.toggle("is-disabled", btnDown.disabled);
        btnDown.addEventListener("click", function () {
          state.moveStepDown && state.moveStepDown(sid);
        });

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

        cellActions.appendChild(btnUp);
        cellActions.appendChild(btnDown);
        cellActions.appendChild(btnSelect);
        cellActions.appendChild(btnRemove);

        if (state.reorderStep && typeof state.reorderStep === "function") {
          row.draggable = true;

          row.addEventListener("dragstart", function (e) {
            dragStepId = String(sid || "");
            row.classList.add("is-dragging");
            try {
              e.dataTransfer.effectAllowed = "move";
              e.dataTransfer.setData("text/plain", dragStepId);
            } catch (err) {
            }
          });

          row.addEventListener("dragover", function (e) {
            e.preventDefault();
            dropBeforeId = String(sid || "");
            row.classList.add("is-drop-target");
            try {
              e.dataTransfer.dropEffect = "move";
            } catch (err) {
            }
          });

          row.addEventListener("dragleave", function () {
            row.classList.remove("is-drop-target");
          });

          row.addEventListener("drop", function (e) {
            e.preventDefault();
            const targetId = String(sid || "");
            let dragId = dragStepId;
            try {
              dragId = e.dataTransfer.getData("text/plain") || dragId;
            } catch (err) {
            }
            row.classList.remove("is-drop-target");
            if (!dragId || dragId === targetId) return;
            state.reorderStep && state.reorderStep(dragId, targetId);
          });

          row.addEventListener("dragend", function () {
            dragStepId = null;
            dropBeforeId = null;
            row.classList.remove("is-dragging");
            Object.keys(rowById).forEach((k) => {
              const r = rowById[k];
              r && r.classList && r.classList.remove("is-drop-target");
            });
          });
        }

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
