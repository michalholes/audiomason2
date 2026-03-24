(function () {
	"use strict";

	/**
	 * @param {string[]} nodes
	 * @param {AM2JsonObject[]} edges
	 * @returns {AM2JsonObject[]}
	 */
	function normalizeEdges(nodes, edges) {
		const nodeSet = new Set(Array.isArray(nodes) ? nodes : []);
		/** @type {AM2JsonObject[]} */
		const out = [];
		(Array.isArray(edges) ? edges : []).forEach((edge) => {
			if (!edge || typeof edge !== "object" || Array.isArray(edge)) return;
			const fromVal = edge.from_step_id;
			const toVal = edge.to_step_id;
			if (typeof fromVal !== "string" || typeof toVal !== "string") return;
			if (!nodeSet.has(fromVal) || !nodeSet.has(toVal)) return;
			out.push(edge);
		});
		return out;
	}

	window.AM2WDEdgesIntegrity = { normalizeEdges: normalizeEdges };
})();
