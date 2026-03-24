(function () {
	"use strict";

	/**
	 * @param {string} title
	 * @param {HTMLElement | null} body
	 * @param {AM2DomFactoryApi} el
	 * @param {AM2TextFactoryApi} text
	 * @returns {HTMLElement}
	 */
	function _section(title, body, el, text) {
		const wrap = el("div", "flowSidebarSection");
		const head = el("div", "flowSidebarSectionHead");
		head.appendChild(text("div", "flowSidebarSectionTitle", title));
		wrap.appendChild(head);
		if (body) wrap.appendChild(body);
		return wrap;
	}

	/** @param {unknown} value */
	function asElement(value) {
		return value instanceof HTMLElement ? value : null;
	}

	/** @param {unknown} value */
	function asClearNode(value) {
		return typeof value === "function"
			? /** @type {AM2ClearNodeFn} */ (value)
			: null;
	}

	/** @param {unknown} value */
	function asDomFactory(value) {
		return typeof value === "function"
			? /** @type {AM2DomFactoryApi} */ (value)
			: null;
	}

	/** @param {unknown} value */
	function asTextFactory(value) {
		return typeof value === "function"
			? /** @type {AM2TextFactoryApi} */ (value)
			: null;
	}

	/** @param {AM2WDSidebarSectionsOptions} ctx */
	function buildSidebarSections(ctx) {
		const flowSidebar = asElement(ctx.flowSidebar);
		const stepPanel = asElement(ctx.stepPanel);
		const transitionsPanel = asElement(ctx.transitionsPanel);
		const clear = asClearNode(ctx.clear);
		const el = asDomFactory(ctx.el);
		const text = asTextFactory(ctx.text);
		if (!flowSidebar || !stepPanel || !transitionsPanel) return;
		if (!clear || !el || !text) return;
		clear(flowSidebar);
		flowSidebar.appendChild(_section("Inspector", stepPanel, el, text));
		flowSidebar.appendChild(
			_section("Transitions", transitionsPanel, el, text),
		);
		return {};
	}

	/** @param {AM2JsonObject} ctx */
	function buildSidebarTabs(ctx) {
		return buildSidebarSections(
			/** @type {AM2WDSidebarSectionsOptions} */ (/** @type {unknown} */ (ctx)),
		);
	}

	/** @param {AM2JsonObject} state */
	function clearSidebar(state) {
		state.selected = null;
		try {
			window.dispatchEvent(
				new CustomEvent("am2:wd:selected", { detail: { step_id: null } }),
			);
		} catch (e) {
			// ignore
		}
	}

	/**
	 * @param {AM2JsonObject} state
	 * @param {string | null | undefined} stepId
	 */
	function renderSidebar(state, stepId) {
		state.selected = stepId || null;
		try {
			window.dispatchEvent(
				new CustomEvent("am2:wd:selected", {
					detail: { step_id: state.selected },
				}),
			);
		} catch (e) {
			// ignore
		}
	}

	window.AM2WDSidebar = {
		buildSidebarSections: buildSidebarSections,
		buildSidebarTabs: buildSidebarTabs,
		clearSidebar: clearSidebar,
		renderSidebar: renderSidebar,
	};
})();
