(function () {
	"use strict";

	const H = window.AM2EditorHTTP;
	/** @type {Map<string, AM2JsonValue | null>} */
	const cache = new Map();
	/** @type {string | null} */
	let loadingStepId = null;
	/** @type {string | null} */
	let errorToken = null;

	/** @param {string} stepId */
	function getCached(stepId) {
		if (!stepId) return null;
		return cache.has(stepId) ? cache.get(stepId) || null : null;
	}

	/** @returns {AM2WDStepDetailsLoaderState} */
	function getState() {
		return { loadingStepId: loadingStepId, errorToken: errorToken };
	}

	/** @param {string} stepId */
	async function loadStepDetails(stepId) {
		if (!stepId || !H || !H.requestJSON) return;
		if (cache.has(stepId)) return;
		loadingStepId = stepId;
		errorToken = null;
		const out = await H.requestJSON(
			"/import/ui/steps/" + encodeURIComponent(String(stepId)),
		);
		if (out && out.ok) {
			cache.set(stepId, out.data || null);
			loadingStepId = null;
			return;
		}
		errorToken = "request_failed";
		loadingStepId = null;
	}

	window.AM2WDStepDetailsLoader = {
		loadStepDetails: loadStepDetails,
		getCached: getCached,
		getState: getState,
	};
})();
