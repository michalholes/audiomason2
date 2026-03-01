(function () {
	"use strict";

	function setRawErrorVisible(state, ui, on) {
		state.showRawError = !!on;
		if (!ui || !ui.err) return;
		ui.err.classList.toggle("is-collapsed", !state.showRawError);
	}

	function setupRawErrorPanel(ctx) {
		const ui = ctx && ctx.ui;
		const state = ctx && ctx.state;
		const el = ctx && ctx.el;
		const text = ctx && ctx.text;

		if (!ui || !ui.err || !ui.err.parentNode) return;
		const parent = ui.err.parentNode;

		const wrap = el("div", "wdErrWrap");
		const bar = el("div", "wdErrBar");
		const title = text("div", "wdErrTitle", "Raw Error");
		const toggle = text("button", "btn wdErrToggle", "Details");
		toggle.type = "button";

		bar.appendChild(title);
		bar.appendChild(toggle);
		wrap.appendChild(bar);

		parent.insertBefore(wrap, ui.err);
		wrap.appendChild(ui.err);

		ui.err.classList.add("wdRawError");
		ui.err.classList.add("is-collapsed");

		toggle.addEventListener("click", () => {
			setRawErrorVisible(state, ui, !state.showRawError);
		});

		state.showRawError = false;
		state.hasErrorDetails = false;
	}

	window.AM2WDRawError = {
		setupRawErrorPanel: setupRawErrorPanel,
		setRawErrorVisible: setRawErrorVisible,
	};
})();
