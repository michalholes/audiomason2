/// <reference path="../../../../am2-globals.d.ts" />
/** @typedef {AM2WebWizardBody} AM2AppDragdropWizardBody */
/** @typedef {AM2WebStepRowDragdropDeps} AM2AppDragdropDeps */

function readDragIndex(/** @type {DragEvent} */ ev) {
	const dt = ev.dataTransfer;
	if (!dt) return -1;
	return parseInt(dt.getData("text/plain") || "-1", 10);
}

export function bindStepRowDragdropHandlers(
	/** @type {HTMLElement} */ row,
	/** @type {number} */ idx,
	/** @type {AM2AppDragdropWizardBody} */ wiz,
	/** @type {AM2AppDragdropDeps} */ deps,
) {
	row.addEventListener("dragstart", (/** @type {DragEvent} */ ev) => {
		const dt = ev.dataTransfer;
		if (!dt) return;
		dt.setData("text/plain", String(idx));
		dt.effectAllowed = "move";
	});
	row.addEventListener("dragover", (/** @type {DragEvent} */ ev) => {
		ev.preventDefault();
		const dt = ev.dataTransfer;
		if (!dt) return;
		dt.dropEffect = "move";
	});
	row.addEventListener("drop", (/** @type {DragEvent} */ ev) => {
		ev.preventDefault();
		const from = readDragIndex(ev);
		const to = idx;
		const steps = Array.isArray(wiz.steps) ? wiz.steps : [];
		if (Number.isNaN(from) || from < 0 || from >= steps.length) return;
		if (from === to) return;
		const [it] = steps.splice(from, 1);
		if (!it) return;
		steps.splice(to, 0, it);
		deps.renderDetail();
		deps.renderStepEditor(to);
		deps.refreshYamlPreview();
	});
}
