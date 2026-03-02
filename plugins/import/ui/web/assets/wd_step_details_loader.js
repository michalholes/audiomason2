(function () {
	"use strict";

	const H = window.AM2EditorHTTP;

	const cache = new Map();
	let loadingStepId = null;
	let errorToken = null;

	function getCached(stepId) {
		if (!stepId) return null;
		return cache.has(stepId) ? cache.get(stepId) : null;
	}

	function getState() {
		return { loadingStepId: loadingStepId, errorToken: errorToken };
	}

	async function loadStepDetails(stepId) {
		if (!stepId) return;
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
