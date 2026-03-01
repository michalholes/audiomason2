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

		function clearDropTargets() {
			Object.keys(rowById).forEach((k) => {
				const r = rowById[k];
				r && r.classList && r.classList.remove("is-drop-target");
			});
		}

		if (state.reorderStep && typeof state.reorderStep === "function") {
			body.addEventListener("dragover", function (e) {
				e.preventDefault();
				dropBeforeId = null;
				try {
					e.dataTransfer.dropEffect = "move";
				} catch (err) {}
			});

			body.addEventListener("drop", function (e) {
				e.preventDefault();
				let dragId = dragStepId;
				try {
					dragId = e.dataTransfer.getData("text/plain") || dragId;
				} catch (err) {}
				clearDropTargets();
				if (!dragId) return;
				state.reorderStep && state.reorderStep(dragId, null);
			});
		}

		function renderAll() {
			clear(body);
			Object.keys(rowById).forEach((k) => {
				delete rowById[k];
			});
			const wd = state.getWizardDraft ? state.getWizardDraft() : {};
			const g = stableGraph(wd);
			const nodes = Array.isArray(g.nodes) ? g.nodes : [];
			const selected = state.getSelectedStepId
				? state.getSelectedStepId()
				: null;

			dragStepId = null;
			dropBeforeId = null;

			nodes.forEach((sid, idx) => {
				const row = el("div", "wdRow");
				row.dataset.stepId = String(sid || "");
				row.classList.toggle(
					"is-selected",
					String(selected || "") === String(sid || ""),
				);

				const cellOrder = el("div", "wdCellOrder");
				const handle = el("span", "wdDragHandle");
				const gripSvg =
					window.AM2WDDomIcons && window.AM2WDDomIcons.svgIcon
						? window.AM2WDDomIcons.svgIcon("grip", "wdGrip", "Reorder")
						: null;
				if (gripSvg) {
					handle.appendChild(gripSvg);
				} else {
					handle.appendChild(text("span", null, "==="));
				}
				const orderText = text("span", null, String(idx + 1));
				cellOrder.appendChild(handle);
				cellOrder.appendChild(orderText);

				const cellId = text("div", "wdCellId", String(sid || ""));
				const cellType = text(
					"div",
					"wdCellType",
					state.isOptional && state.isOptional(sid) ? "optional" : "mandatory",
				);
				const cellReq = text(
					"div",
					"wdCellReq",
					state.isOptional && state.isOptional(sid) ? "no" : "yes",
				);
				const cellActions = el("div", "wdCellActions");

				const btnRemove = el("button", "btn btnSmall wdDeleteBtn");
				btnRemove.type = "button";
				btnRemove.title = "Remove";
				const trashSvg =
					window.AM2WDDomIcons && window.AM2WDDomIcons.svgIcon
						? window.AM2WDDomIcons.svgIcon("trash", null, "Remove")
						: null;
				if (trashSvg) {
					btnRemove.appendChild(trashSvg);
				} else {
					btnRemove.appendChild(text("span", null, "X"));
				}
				btnRemove.disabled = !(state.canRemove && state.canRemove(sid));
				btnRemove.classList.toggle("is-disabled", btnRemove.disabled);
				btnRemove.addEventListener("click", function (e) {
					e.stopPropagation();
					state.removeStep && state.removeStep(sid);
				});

				cellActions.appendChild(btnRemove);

				row.addEventListener("click", function () {
					state.setSelectedStep && state.setSelectedStep(sid);
				});

				if (state.reorderStep && typeof state.reorderStep === "function") {
					handle.draggable = true;

					handle.addEventListener("click", function (e) {
						e.stopPropagation();
					});

					handle.addEventListener("dragstart", function (e) {
						dragStepId = String(sid || "");
						row.classList.add("is-dragging");
						try {
							e.dataTransfer.effectAllowed = "move";
							e.dataTransfer.setData("text/plain", dragStepId);
						} catch (err) {}
					});

					row.addEventListener("dragover", function (e) {
						e.preventDefault();
						dropBeforeId = String(sid || "");
						clearDropTargets();
						row.classList.add("is-drop-target");
						try {
							e.dataTransfer.dropEffect = "move";
						} catch (err) {}
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
						} catch (err) {}
						row.classList.remove("is-drop-target");
						if (!dragId || dragId === targetId) return;
						state.reorderStep && state.reorderStep(dragId, targetId);
					});

					handle.addEventListener("dragend", function () {
						dragStepId = null;
						dropBeforeId = null;
						row.classList.remove("is-dragging");
						clearDropTargets();
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
			const selected = state.getSelectedStepId
				? state.getSelectedStepId()
				: null;
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
