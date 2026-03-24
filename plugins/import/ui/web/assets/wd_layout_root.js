(function () {
	"use strict";

	/**
	 * @param {string} tag
	 * @param {string | null | undefined} cls
	 * @returns {HTMLElement}
	 */
	function fallbackDom(tag, cls) {
		const node = document.createElement(tag);
		if (cls) node.className = cls;
		return node;
	}

	/**
	 * @param {string} tag
	 * @param {string | null | undefined} cls
	 * @param {string | undefined} value
	 * @returns {HTMLElement}
	 */
	function fallbackText(tag, cls, value) {
		const node = document.createElement(tag);
		if (cls) node.className = cls;
		node.textContent = String(value || "");
		return node;
	}

	/** @param {unknown} fn */
	function asDomFactory(fn) {
		return typeof fn === "function"
			? /** @type {AM2DomFactoryApi} */ (fn)
			: fallbackDom;
	}

	/** @param {unknown} fn */
	function asTextFactory(fn) {
		return typeof fn === "function"
			? /** @type {AM2TextFactoryApi} */ (fn)
			: fallbackText;
	}

	/**
	 * @param {{
	 * 	ui: AM2WDLayoutRootUi,
	 * 	el: AM2DomFactoryApi,
	 * 	text: AM2TextFactoryApi,
	 * }} opts
	 * @returns {AM2WDLayoutRootResult | null}
	 */
	function createRoot(opts) {
		const ui = /** @type {AM2WDLayoutRootUi} */ ((opts && opts.ui) || {});
		const el = asDomFactory(opts && opts.el);
		const text = asTextFactory(opts && opts.text);
		const mount = ui.ta && ui.ta.parentNode ? ui.ta.parentNode : null;
		if (!mount || !ui.ta) return null;
		const layout = el("div", "wdLayoutRoot");
		const toolbar = el("div", "wdToolbar");
		const table = el("div", "wdTable");
		const head = el("div", "wdHead");
		const body = el("div", "wdBody");
		const dropHint = el("div", "wdDropHint");
		const validation = el("div", "wdValidation");
		const validationHeader = el("div", "wdValidationHeader");
		const validationTitle = text(
			"div",
			"wdValidationTitle",
			"Validation Messages",
		);
		const validationCount = text("div", "wdValidationCount", "");
		const validationClear = /** @type {HTMLButtonElement} */ (
			text("button", "btn wdValidationClear", "Clear All")
		);
		validationClear.type = "button";
		const validationList = el("div", "wdValidationList");
		head.appendChild(text("div", "wdCellOrder", "Order"));
		head.appendChild(text("div", "wdCellId", "Step ID"));
		head.appendChild(text("div", "wdCellType", "Type"));
		head.appendChild(text("div", "wdCellReq", "Required"));
		head.appendChild(text("div", "wdCellActions", "Actions"));
		table.appendChild(head);
		table.appendChild(body);
		dropHint.appendChild(text("div", "wdDropHintText", "Drop to insert"));
		validationHeader.appendChild(validationTitle);
		validationHeader.appendChild(validationCount);
		validationHeader.appendChild(validationClear);
		validation.appendChild(validationHeader);
		validation.appendChild(validationList);
		layout.appendChild(toolbar);
		layout.appendChild(table);
		layout.appendChild(dropHint);
		layout.appendChild(validation);
		mount.insertBefore(layout, ui.ta);
		return {
			layout: layout,
			toolbar: toolbar,
			tableBody: body,
			dropHint: dropHint,
			validationCount: validationCount,
			validationClear: validationClear,
			validationList: validationList,
		};
	}

	window.AM2WDLayoutRoot = { createRoot: createRoot };
})();
