(function () {
	"use strict";

	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	function renderValidation(opts) {
		const mount = opts && opts.mount;
		const countEl = opts && opts.countEl;
		const el = (opts && opts.el) || function () {};
		const text = (opts && opts.text) || function () {};
		const messages = (opts && opts.messages) || [];
		if (!mount) return;

		clear(mount);
		const msgs = Array.isArray(messages) ? messages : [];
		if (countEl) countEl.textContent = msgs.length ? String(msgs.length) : "";

		if (!msgs.length) {
			mount.appendChild(
				text("div", "wdValidationEmpty", "No validation messages."),
			);
			return;
		}

		msgs.forEach(function (m) {
			const row = el("div", "wdValidationItem");
			row.textContent = String(m || "");
			mount.appendChild(row);
		});
	}

	window.AM2WDDetailsRender = {
		renderValidation: renderValidation,
	};
})();
