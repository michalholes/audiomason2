(function () {
  "use strict";

  function stableGraph(defn) {
    const root = defn && typeof defn === "object" ? defn : {};
    const vAny = root.version;
    const version = typeof vAny === "number" ? vAny : 1;

    if (version === 2 && root.graph && typeof root.graph === "object") {
      const g = root.graph;
      const entry = typeof g.entry_step_id === "string" ? g.entry_step_id : null;

      const nodesAny = Array.isArray(g.nodes) ? g.nodes : [];
      const nodes = nodesAny
        .map((n) => (n && typeof n.step_id === "string" ? n.step_id : ""))
        .filter((x) => x);

      const edgesAny = Array.isArray(g.edges) ? g.edges : [];
      const edges = edgesAny
        .map((e) => (e && typeof e === "object" ? e : null))
        .filter((e) => e)
        .map((e) => ({
          from_step_id: typeof e.from_step_id === "string" ? e.from_step_id : "",
          to_step_id: typeof e.to_step_id === "string" ? e.to_step_id : "",
          priority: typeof e.priority === "number" ? e.priority : 0,
          when: e.when === undefined ? null : e.when,
        }))
        .filter((e) => e.from_step_id && e.to_step_id);

      return { version: 2, entry: entry || nodes[0] || null, nodes: nodes, edges: edges };
    }

    const steps = root && Array.isArray(root.steps) ? root.steps : [];
    const nodes = steps
      .map((x) => (x && typeof x.step_id === "string" ? x.step_id : ""))
      .filter((x) => x);
    return { version: 1, nodes: nodes, edges: [], entry: nodes[0] || null };
  }

  window.AM2WDGraphStable = { stableGraph: stableGraph };
})();
