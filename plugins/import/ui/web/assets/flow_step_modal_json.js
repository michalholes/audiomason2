/// <reference path="../../../../../types/am2-import-ui-globals.d.ts" />
(function () {
	"use strict";

	/** @type {Window} */
	const W = window;

	/** @param {{
	 * 	textarea: HTMLTextAreaElement | null,
	 * 	value: string,
	 * 	onInput?: ((value: string) => void) | undefined,
	 * } | null | undefined} opts */
	function renderJSON(opts) {
		const textarea = opts && opts.textarea;
		const value = String((opts && opts.value) || "");
		const rawOnInput = opts ? opts.onInput : undefined;
		const onInput =
			typeof rawOnInput === "function" ? rawOnInput : function () {};
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
