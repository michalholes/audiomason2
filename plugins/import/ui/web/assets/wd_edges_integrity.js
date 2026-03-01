(function () {
	"use strict";

	function normalizeEdges(nodes, edges) {
		const nodeSet = new Set(Array.isArray(nodes) ? nodes : []);
		const out = [];
		(Array.isArray(edges) ? edges : []).forEach((e) => {
			if (!e || typeof e !== "object") return;
			const frm = e.from_step_id;
			const to = e.to_step_id;
			if (typeof frm !== "string" || typeof to !== "string") return;
			if (!nodeSet.has(frm) || !nodeSet.has(to)) return;
			out.push(e);
		});
		return out;
	}

	window.AM2WDEdgesIntegrity = { normalizeEdges: normalizeEdges };
})();
