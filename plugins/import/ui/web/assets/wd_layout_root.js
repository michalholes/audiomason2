(function () {
	"use strict";

	function createRoot(opts) {
		const ui = (opts && opts.ui) || {};
		const el = (opts && opts.el) || function () {};
		const text = (opts && opts.text) || function () {};

		const mount = ui.ta && ui.ta.parentNode ? ui.ta.parentNode : null;
		if (!mount) return null;

		const layout = el("div", "wdLayoutRoot");
		const toolbar = el("div", "wdToolbar");
		const rootHead = el("div", "wdRootHead");
		const rootHeadLeft = el("div", "wdRootHeadLeft");
		rootHeadLeft.appendChild(text("div", "wdRootTitle", "Wizard Structure"));
		rootHeadLeft.appendChild(
			text("div", "wdRootSubtitle", "Define steps, order and policies"),
		);
		const rootHeadRight = el("div", "wdRootHeadRight");
		rootHeadRight.appendChild(text("div", "wdRootSteps", ""));
		rootHead.appendChild(rootHeadLeft);
		rootHead.appendChild(rootHeadRight);

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
		const validationClear = text(
			"button",
			"btn wdValidationClear",
			"Clear All",
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

		layout.appendChild(rootHead);
		layout.appendChild(toolbar);
		layout.appendChild(table);
		layout.appendChild(dropHint);
		layout.appendChild(validation);

		mount.insertBefore(layout, ui.ta);
		ui.ta.classList.add("wdHidden");

		return {
			layout: layout,
			rootSteps: rootHeadRight.firstChild,
			toolbar: toolbar,
			tableBody: body,
			dropHint: dropHint,
			validationCount: validationCount,
			validationClear: validationClear,
			validationList: validationList,
		};
	}

	/** @type {any} */ (window).AM2WDLayoutRoot = {
		createRoot: createRoot,
	};
})();
