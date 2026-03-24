(function () {
	"use strict";

	/** @param {Node | null} node */
	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	/** @param {string} tag @param {string | null | undefined} cls @param {unknown=} textValue */
	function el(tag, cls, textValue) {
		const node = document.createElement(tag);
		if (cls) node.className = cls;
		if (textValue !== undefined) node.textContent = String(textValue);
		return node;
	}

	/** @param {string} label @returns {HTMLButtonElement} */
	function button(label) {
		const node = document.createElement("button");
		node.className = "btn";
		node.type = "button";
		node.textContent = label;
		return node;
	}

	/** @param {AM2DSLEditorRawJSONOptions} opts */
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
		const visualBtn = button("Visual");
		visualBtn.setAttribute("data-am2-raw-json-toggle", "visual");
		visualBtn.addEventListener("click", function () {
			onSetMode(false);
		});
		const rawBtn = button("Raw JSON");
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

		const applyBtn = button("Apply Raw JSON");
		applyBtn.setAttribute("data-am2-raw-json-apply", "true");
		applyBtn.addEventListener("click", function () {
			onApply(textarea.value || "{}");
		});
		mount.appendChild(applyBtn);
	}

	window.AM2DSLEditorRawJSON = { renderRawJSON };
})();
