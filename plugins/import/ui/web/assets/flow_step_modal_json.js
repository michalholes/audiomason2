(function () {
	"use strict";

	const W = /** @type {any} */ (window);

	function renderJSON(opts) {
		const textarea = opts && opts.textarea;
		const value = String((opts && opts.value) || "");
		const onInput =
			typeof (opts && opts.onInput) === "function"
				? opts.onInput
				: function () {};
		if (!textarea) return;
		textarea.value = value;
		textarea.oninput = function () {
			onInput(textarea.value || "");
		};
	}

	W.AM2FlowStepModalJSON = {
		renderJSON: renderJSON,
	};
})();
