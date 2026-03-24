(function () {
	"use strict";

	/**
	 * @typedef {{version:number,nodes:string[],edges:AM2JsonObject[],entry:string|null}}
	 * 	AM2WDStableGraph
	 */

	/**
	 * @param {AM2JsonValue} value
	 * @returns {AM2JsonObject | null}
	 */
	function asJsonObject(value) {
		if (!value || typeof value !== "object" || Array.isArray(value))
			return null;
		return /** @type {AM2JsonObject} */ (value);
	}

	/**
	 * @param {AM2JsonObject} defn
	 * @returns {AM2WDStableGraph}
	 */
	function stableGraph(defn) {
		const root = defn && typeof defn === "object" ? defn : {};
		const version = typeof root.version === "number" ? root.version : 1;
		const graph = asJsonObject(root.graph || null);
		if (version === 2 && graph) {
			const entry =
				typeof graph.entry_step_id === "string" ? graph.entry_step_id : null;
			const nodes = (Array.isArray(graph.nodes) ? graph.nodes : [])
				.map((node) => {
					const obj = asJsonObject(node);
					return obj && typeof obj.step_id === "string" ? obj.step_id : "";
				})
				.filter((stepId) => Boolean(stepId));
			const edges = (Array.isArray(graph.edges) ? graph.edges : [])
				.map((edge) => asJsonObject(edge))
				.filter((edge) => edge !== null)
				.map((edge) => ({
					from_step_id:
						typeof edge.from_step_id === "string" ? edge.from_step_id : "",
					to_step_id:
						typeof edge.to_step_id === "string" ? edge.to_step_id : "",
					priority: typeof edge.priority === "number" ? edge.priority : 0,
					when: edge.when === undefined ? null : edge.when,
				}))
				.filter((edge) => Boolean(edge.from_step_id && edge.to_step_id));
			return {
				version: 2,
				entry: entry || nodes[0] || null,
				nodes: nodes,
				edges: edges,
			};
		}
		const nodes = (Array.isArray(root.steps) ? root.steps : [])
			.map((step) => {
				const obj = asJsonObject(step);
				return obj && typeof obj.step_id === "string" ? obj.step_id : "";
			})
			.filter((stepId) => Boolean(stepId));
		return { version: 1, nodes: nodes, edges: [], entry: nodes[0] || null };
	}

	window.AM2WDGraphStable = { stableGraph: stableGraph };
})();
