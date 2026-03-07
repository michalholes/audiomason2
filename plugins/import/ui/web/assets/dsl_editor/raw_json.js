(function () {
	"use strict";

	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	function el(tag, cls, textValue) {
		const node = document.createElement(tag);
		if (cls) node.className = cls;
		if (textValue !== undefined) node.textContent = String(textValue);
		return node;
	}

	function renderRawJSON(opts) {
		const mount = opts && opts.mount;
		const textarea = opts && opts.textarea;
		if (!mount || !textarea) return;
		clear(mount);
		const state = (opts && opts.state) || {};
		const actions = (opts && opts.actions) || {};
		const mode = state.rawMode === true;
		const onSetMode =
			typeof actions.onSetMode === "function"
				? actions.onSetMode
				: function () {};
		const onApply =
			typeof actions.onApply === "function" ? actions.onApply : function () {};

		const toolbar = el("div", "buttonRow");
		toolbar.setAttribute("data-am2-raw-json-toolbar", "true");
		const visualBtn = el("button", "btn", "Visual");
		visualBtn.type = "button";
		visualBtn.setAttribute("data-am2-raw-json-toggle", "visual");
		visualBtn.addEventListener("click", function () {
			onSetMode(false);
		});
		const rawBtn = el("button", "btn", "Raw JSON");
		rawBtn.type = "button";
		rawBtn.setAttribute("data-am2-raw-json-toggle", "raw");
		rawBtn.addEventListener("click", function () {
			onSetMode(true);
		});
		toolbar.appendChild(visualBtn);
		toolbar.appendChild(rawBtn);
		mount.appendChild(toolbar);

		textarea.classList.toggle("is-hidden", !mode);
		if (!mode) return;

		const note = el(
			"div",
			"flowStepDesc",
			"Raw JSON is authoritative. Visual mode must preserve unknown keys.",
		);
		note.setAttribute("data-am2-raw-json-note", "authoritative");
		mount.appendChild(note);

		const applyBtn = el("button", "btn", "Apply Raw JSON");
		applyBtn.type = "button";
		applyBtn.setAttribute("data-am2-raw-json-apply", "true");
		applyBtn.addEventListener("click", function () {
			onApply(textarea.value || "{}");
		});
		mount.appendChild(applyBtn);
	}

	window["AM2DSLEditorRawJSON"] = { renderRawJSON: renderRawJSON };
})();
