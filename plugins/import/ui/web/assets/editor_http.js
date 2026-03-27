(function () {
	"use strict";

	/**
	 * @param {string} url
	 * @param {RequestInit | null | undefined} [opts]
	 * @returns {Promise<AM2EditorHttpResponse>}
	 */
	async function requestJSON(url, opts) {
		const r = await fetch(url, opts || {});
		const text = await r.text();
		/** @type {AM2EditorHttpPayload} */
		let data = {};
		try {
			data = /** @type {AM2EditorHttpPayload} */ (JSON.parse(text || "{}"));
		} catch {
			data = { text: text || "" };
		}
		return { ok: r.ok, status: r.status, data };
	}

	/** @param {AM2JsonValue} obj
	 * @returns {string}
	 */
	function pretty(obj) {
		return JSON.stringify(obj, null, 2);
	}

	/**
	 * @param {Node | null | undefined} node
	 * @param {AM2EditorHttpPayload | AM2JsonValue | undefined} payload
	 */
	function renderError(node, payload) {
		if (!node) return;
		if (!payload) {
			node.textContent = "";
			return;
		}
		const record =
			typeof payload === "object" && !Array.isArray(payload) && payload
				? payload
				: null;
		const err = record && record.error ? record.error : null;
		if (err && typeof err === "object") {
			node.textContent = pretty(payload);
			return;
		}

		if (record && Object.prototype.hasOwnProperty.call(record, "detail")) {
			const detail = record.detail;
			if (typeof detail === "string") {
				node.textContent = detail;
				return;
			}
			node.textContent = pretty(detail || null);
			return;
		}

		node.textContent = String(record && record.text ? record.text : payload);
	}

	window.AM2EditorHTTP = {
		requestJSON,
		pretty,
		renderError,
	};
})();
