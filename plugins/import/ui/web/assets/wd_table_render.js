(function () {
	"use strict";

	const W = window;

	/** @type {(definition: AM2JsonObject) => AM2WDStableGraphResult} */
	const stableGraph =
		W.AM2WDGraphStable && W.AM2WDGraphStable.stableGraph
			? W.AM2WDGraphStable.stableGraph
			: function () {
					return { version: 1, nodes: [], edges: [], entry: null };
				};

	/** @param {Node | null | undefined} node */
	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	/**
	 * @param {{
	 *   body?: HTMLElement | null,
	 *   el?: AM2DomFactoryApi | null,
	 *   text?: AM2TextFactoryApi | null,
	 *   state?: AM2WDTableStateApi | null,
	 * } | null | undefined} opts
	 * @returns {AM2WDTableRenderInstance | null}
	 */
	function initTable(opts) {
		const body = opts && opts.body ? opts.body : null;
		/** @type {AM2DomFactoryApi} */
		const el =
			(opts && opts.el) ||
			/** @type {AM2DomFactoryApi} */ (() => document.createElement("div"));
		/** @type {AM2TextFactoryApi} */
		const text =
			(opts && opts.text) ||
			/** @type {AM2TextFactoryApi} */ (
				(tag, cls, value) => {
					const node = document.createElement(tag);
					if (cls) node.className = cls;
					node.textContent = String(value || "");
					return node;
				}
			);
		/** @type {AM2WDTableStateApi} */
		const state =
			(opts && opts.state) ||
			/** @type {AM2WDTableStateApi} */ ({
				getWizardDraft: () => ({}),
				getSelectedStepId: () => null,
				isOptional: () => false,
				canRemove: () => false,
				setSelectedStep: () => {},
				removeStep: () => {},
				moveStepUp: () => {},
				moveStepDown: () => {},
				reorderStep: () => {},
			});
		if (!body) return null;
		const tableBody = body;

		/** @type {Record<string, HTMLElement>} */
		const rowById = {};
		/** @type {string | null} */
		let dragStepId = null;
		/** @type {string | null} */
		let dropBeforeId = null;

		function clearDropTargets() {
			Object.keys(rowById).forEach((stepId) => {
				const row = rowById[stepId];
				if (row && row.classList) row.classList.remove("is-drop-target");
			});
		}

		if (typeof state.reorderStep === "function") {
			tableBody.addEventListener("dragover", function (event) {
				event.preventDefault();
				dropBeforeId = null;
				try {
					if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
				} catch (error) {}
			});

			tableBody.addEventListener("drop", function (event) {
				event.preventDefault();
				let dragId = dragStepId;
				try {
					dragId =
						event.dataTransfer && event.dataTransfer.getData("text/plain")
							? event.dataTransfer.getData("text/plain")
							: dragId;
				} catch (error) {}
				clearDropTargets();
				if (!dragId) return;
				state.reorderStep(dragId, dropBeforeId || null);
			});
		}

		function renderAll() {
			clear(tableBody);
			Object.keys(rowById).forEach((stepId) => {
				delete rowById[stepId];
			});
			const wizardDraft = state.getWizardDraft ? state.getWizardDraft() : {};
			const graph = stableGraph(wizardDraft);
			const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
			const selected = state.getSelectedStepId
				? state.getSelectedStepId()
				: null;

			dragStepId = null;
			dropBeforeId = null;

			nodes.forEach((stepId, index) => {
				const sid = String(stepId || "");
				const row = el("div", "wdRow");
				row.dataset.stepId = sid;
				row.classList.toggle("is-selected", String(selected || "") === sid);

				const cellOrder = el("div", "wdCellOrder");
				const handle = el("span", "wdDragHandle");
				const gripSvg =
					W.AM2WDDomIcons && W.AM2WDDomIcons.svgIcon
						? W.AM2WDDomIcons.svgIcon("grip", "wdGrip", "Reorder")
						: null;
				if (gripSvg) handle.appendChild(gripSvg);
				else handle.appendChild(text("span", null, "==="));
				cellOrder.appendChild(handle);
				cellOrder.appendChild(text("span", null, String(index + 1)));

				const cellId = text("div", "wdCellId", sid);
				const optional = !!(state.isOptional && state.isOptional(sid));
				const cellType = text(
					"div",
					"wdCellType",
					optional ? "optional" : "mandatory",
				);
				const cellReq = text("div", "wdCellReq", optional ? "no" : "yes");
				const cellActions = el("div", "wdCellActions");

				const btnRemove = /** @type {HTMLButtonElement} */ (
					el("button", "btn btnSmall wdDeleteBtn")
				);
				btnRemove.type = "button";
				btnRemove.title = "Remove";
				const trashSvg =
					W.AM2WDDomIcons && W.AM2WDDomIcons.svgIcon
						? W.AM2WDDomIcons.svgIcon("trash", undefined, "Remove")
						: null;
				if (trashSvg) btnRemove.appendChild(trashSvg);
				else btnRemove.appendChild(text("span", null, "X"));
				btnRemove.disabled = !(state.canRemove && state.canRemove(sid));
				btnRemove.classList.toggle("is-disabled", btnRemove.disabled);
				btnRemove.addEventListener("click", function (event) {
					event.stopPropagation();
					if (state.removeStep) state.removeStep(sid);
				});
				cellActions.appendChild(btnRemove);

				row.addEventListener("click", function () {
					if (state.setSelectedStep) state.setSelectedStep(sid);
				});

				if (typeof state.reorderStep === "function") {
					handle.draggable = true;
					handle.addEventListener("click", function (event) {
						event.stopPropagation();
					});
					handle.addEventListener("dragstart", function (event) {
						dragStepId = sid;
						row.classList.add("is-dragging");
						try {
							if (event.dataTransfer) {
								event.dataTransfer.effectAllowed = "move";
								event.dataTransfer.setData("text/plain", sid);
							}
						} catch (error) {}
					});
					row.addEventListener("dragover", function (event) {
						event.preventDefault();
						event.stopPropagation();
						dropBeforeId = sid;
						clearDropTargets();
						row.classList.add("is-drop-target");
						try {
							if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
						} catch (error) {}
					});
					row.addEventListener("dragleave", function () {
						row.classList.remove("is-drop-target");
					});
					row.addEventListener("drop", function (event) {
						event.preventDefault();
						event.stopPropagation();
						let dragId = dragStepId;
						try {
							dragId =
								event.dataTransfer && event.dataTransfer.getData("text/plain")
									? event.dataTransfer.getData("text/plain")
									: dragId;
						} catch (error) {}
						row.classList.remove("is-drop-target");
						if (!dragId || dragId === sid) return;
						state.reorderStep(dragId, sid);
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
				tableBody.appendChild(row);
				rowById[sid] = row;
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

		return { renderAll, updateSelection };
	}

	W.AM2WDTableRender = { initTable };
})();
