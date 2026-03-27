(function () {
	"use strict";

	/** @typedef {{
	 * 	stepId: string,
	 * 	title: string,
	 * 	subtitle: string,
	 * 	kind: string,
	 * }} AM2FlowCanvasNodeCard
	 */

	/** @type {Window} */
	const W = window;

	/** @param {Node | null | undefined} node */
	function clear(node) {
		while (node && node.firstChild) {
			node.removeChild(node.firstChild);
		}
	}

	/**
	 * @param {string} tag
	 * @param {string | null | undefined} [cls]
	 * @param {string | number | boolean | null | undefined} [textValue]
	 * @returns {HTMLElement}
	 */
	function el(tag, cls, textValue) {
		const node = document.createElement(tag);
		if (cls) node.className = cls;
		if (textValue !== undefined) {
			node.textContent = String(textValue);
		}
		return node;
	}

	/**
	 * @param {string | null | undefined} stepId
	 * @param {Record<string, AM2JsonObject> | null | undefined} catalog
	 * @returns {AM2JsonObject | null}
	 */
	function lookupMeta(stepId, catalog) {
		if (!catalog || typeof catalog !== "object") return null;
		return catalog[String(stepId || "")] || null;
	}

	/**
	 * @param {AM2JsonObject | null | undefined} rawNode
	 * @param {AM2JsonObject | null | undefined} meta
	 * @returns {string}
	 */
	function nodeTitle(rawNode, meta) {
		const node = rawNode && typeof rawNode === "object" ? rawNode : {};
		const op =
			node.op && typeof node.op === "object" && !Array.isArray(node.op)
				? node.op
				: {};
		const inputs =
			op.inputs && typeof op.inputs === "object" && !Array.isArray(op.inputs)
				? op.inputs
				: {};
		const label = typeof inputs.label === "string" ? inputs.label.trim() : "";
		if (label) return label;
		if (meta && meta.displayName) return String(meta.displayName);
		if (meta && meta.title) return String(meta.title);
		return String(node.step_id || "");
	}

	/**
	 * @param {AM2JsonObject | null | undefined} rawNode
	 * @param {AM2JsonObject | null | undefined} meta
	 * @returns {string}
	 */
	function nodeSubtitle(rawNode, meta) {
		const node = rawNode && typeof rawNode === "object" ? rawNode : {};
		const op =
			node.op && typeof node.op === "object" && !Array.isArray(node.op)
				? node.op
				: {};
		const inputs =
			op.inputs && typeof op.inputs === "object" && !Array.isArray(op.inputs)
				? op.inputs
				: {};
		const prompt =
			typeof inputs.prompt === "string" ? inputs.prompt.trim() : "";
		const textValue = typeof inputs.text === "string" ? inputs.text.trim() : "";
		if (prompt) return prompt;
		if (textValue) return textValue;
		if (meta && meta.shortDescription) return String(meta.shortDescription);
		const pid = op.primitive_id ? String(op.primitive_id) : "";
		if (pid) return pid + "@" + String(op.primitive_version || 0);
		return "Workflow step";
	}

	/** @param {AM2JsonObject | null | undefined} rawNode
	 * @returns {string}
	 */
	function nodeKind(rawNode) {
		const op =
			rawNode &&
			rawNode.op &&
			typeof rawNode.op === "object" &&
			!Array.isArray(rawNode.op)
				? rawNode.op
				: {};
		const pid = String(op.primitive_id || "");
		if (!pid) return "kind-default";
		if (pid === "ui.message") return "kind-message";
		if (
			pid.indexOf("io.") === 0 ||
			pid.indexOf("import.") === 0 ||
			pid.indexOf("flow.") === 0
		) {
			return "kind-io";
		}
		if (pid.indexOf("confirm") >= 0 || pid.indexOf("condition") >= 0) {
			return "kind-decision";
		}
		return "kind-default";
	}

	/**
	 * @param {string | null | undefined} stepId
	 * @param {AM2DSLEditorEdgeRecord[] | null | undefined} edges
	 * @returns {number}
	 */
	function outgoingCount(stepId, edges) {
		const sid = String(stepId || "");
		const items = Array.isArray(edges) ? edges : [];
		return items.filter(function (edge) {
			const fromId =
				edge && edge.from_step_id !== undefined
					? edge.from_step_id
					: edge && edge.from !== undefined
						? edge.from
						: "";
			return String(fromId || "") === sid;
		}).length;
	}

	/**
	 * @param {Array<AM2JsonObject | string | null> | null | undefined} items
	 * @param {Record<string, AM2JsonObject> | null | undefined} catalog
	 * @returns {AM2FlowCanvasNodeCard[]}
	 */
	function normalizeNodes(items, catalog) {
		return (Array.isArray(items) ? items : [])
			.map(function (item) {
				if (typeof item === "string") {
					const meta = lookupMeta(item, catalog);
					return {
						stepId: String(item),
						title:
							meta && meta.displayName
								? String(meta.displayName)
								: String(item),
						subtitle:
							meta && meta.shortDescription
								? String(meta.shortDescription)
								: "Workflow step",
						kind: "kind-default",
					};
				}
				if (!item || typeof item !== "object") return null;
				const stepId = String(item.step_id || "");
				if (!stepId) return null;
				const meta = lookupMeta(stepId, catalog);
				return {
					stepId: stepId,
					title: nodeTitle(item, meta),
					subtitle: nodeSubtitle(item, meta),
					kind: nodeKind(item),
				};
			})
			.filter(function (item) {
				return item !== null;
			});
	}

	/** @param {AM2FlowCanvasRenderOptions | null | undefined} opts */
	function renderCanvas(opts) {
		const mount = opts && opts.mount;
		const metaMount = opts && opts.metaMount;
		if (!mount) return;
		clear(mount);

		const nodes = normalizeNodes(opts && opts.nodes, opts && opts.catalog);
		const edges = Array.isArray(opts && opts.edges) ? opts.edges : [];
		const selectedStepId = String((opts && opts.selectedStepId) || "");
		/** @type {(stepId: string) => void} */
		const onSelectStep =
			typeof (opts && opts.onSelectStep) === "function"
				? opts.onSelectStep
				: function () {};

		if (metaMount) {
			metaMount.textContent =
				String(nodes.length) +
				" steps" +
				" - " +
				String(edges.length) +
				" transitions";
		}

		if (!nodes.length) {
			mount.appendChild(
				el(
					"div",
					"flowCanvasEmpty",
					"No graph steps are available in this draft.",
				),
			);
			return;
		}

		const track = el("div", "flowCanvasTrack");
		nodes.forEach(function (item) {
			const wrap = el("div", "flowCanvasCardWrap");
			const card = /** @type {HTMLButtonElement} */ (
				el("button", "flowCanvasCard")
			);
			card.type = "button";
			card.setAttribute("data-am2-flow-canvas-step", item.stepId);
			card.classList.toggle("is-selected", item.stepId === selectedStepId);
			card.addEventListener("click", function () {
				onSelectStep(item.stepId);
			});

			const dot = el("span", "flowCanvasCardDot " + item.kind);
			const title = el("div", "flowCanvasCardTitle", item.title);
			const subtitle = el("div", "flowCanvasCardSubtitle", item.subtitle);
			const meta = el(
				"div",
				"flowCanvasCardMeta",
				String(outgoingCount(item.stepId, edges)) + " outgoing",
			);

			card.appendChild(dot);
			card.appendChild(title);
			card.appendChild(subtitle);
			card.appendChild(meta);
			wrap.appendChild(card);
			track.appendChild(wrap);
		});
		mount.appendChild(track);
	}

	W.AM2FlowCanvasPanel = {
		renderCanvas: renderCanvas,
	};
})();
