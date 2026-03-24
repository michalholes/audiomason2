(function () {
	"use strict";

	/**
	 * @param {string} tag
	 * @param {string | null | undefined} cls
	 * @returns {HTMLElement}
	 */
	function fallbackDom(tag, cls) {
		const node = document.createElement(tag);
		if (cls) node.className = cls;
		return node;
	}

	/**
	 * @param {string} tag
	 * @param {string | null | undefined} cls
	 * @param {string | undefined} value
	 * @returns {HTMLElement}
	 */
	function fallbackText(tag, cls, value) {
		const node = document.createElement(tag);
		if (cls) node.className = cls;
		node.textContent = String(value || "");
		return node;
	}

	let _focusHandlerBound = false;
	/** @type {HTMLInputElement | null} */
	let _lastSearch = null;
	/** @type {HTMLElement | null} */
	let _lastMount = null;

	/** @param {Node | null} node */
	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	/** @param {unknown} fn */
	function asDomFactory(fn) {
		return typeof fn === "function"
			? /** @type {AM2DomFactoryApi} */ (fn)
			: fallbackDom;
	}

	/** @param {unknown} fn */
	function asTextFactory(fn) {
		return typeof fn === "function"
			? /** @type {AM2TextFactoryApi} */ (fn)
			: fallbackText;
	}

	/**
	 * @param {AM2JsonObject} node
	 * @returns {string}
	 */
	function itemId(node) {
		return typeof node.step_id === "string" ? node.step_id : "";
	}

	/**
	 * @param {{
	 * 	mount: HTMLElement | null,
	 * 	el: AM2DomFactoryApi,
	 * 	text: AM2TextFactoryApi,
	 * 	items: AM2JsonObject[],
	 * 	state: {
	 * 		canAdd?: (stepId: string) => boolean,
	 * 		addStep?: (stepId: string) => void,
	 * 	},
	 * }} opts
	 */
	function renderPalette(opts) {
		const mount = opts && opts.mount;
		const items = Array.isArray(opts && opts.items) ? opts.items : [];
		const state = (opts && opts.state) || {};
		const el = asDomFactory(opts && opts.el);
		const text = asTextFactory(opts && opts.text);
		if (!mount) return;
		clear(mount);
		const searchWrap = el("div", "wdPaletteSearch");
		const search = /** @type {HTMLInputElement} */ (
			el("input", "wdPaletteSearchInput")
		);
		search.type = "search";
		search.placeholder = "Search";
		searchWrap.appendChild(search);
		mount.appendChild(searchWrap);
		const list = el("div", "wdPaletteGroups");
		mount.appendChild(list);

		/**
		 * @param {AM2JsonObject} item
		 * @param {string} query
		 * @returns {boolean}
		 */
		function matches(item, query) {
			if (!query) return true;
			const haystack = (
				String(itemId(item) || "") +
				" " +
				String(item.displayName || "") +
				" " +
				String(item.shortDescription || "") +
				" " +
				String(item.title || "")
			)
				.toLowerCase()
				.trim();
			return haystack.indexOf(query.toLowerCase().trim()) >= 0;
		}

		_lastSearch = search;
		_lastMount = mount;

		function renderList() {
			clear(list);
			const query = String(search.value || "");
			items.forEach(function (item) {
				if (!matches(item, query)) return;
				const sid = itemId(item);
				if (!sid) return;
				const row = el("div", "wdPaletteItem");
				const meta = el("div", "wdPaletteMeta");
				meta.appendChild(text("div", "wdPaletteItemId", sid));
				meta.appendChild(
					text(
						"div",
						"wdPaletteItemTitle",
						String(item.displayName || item.title || sid),
					),
				);
				if (item.shortDescription) {
					meta.appendChild(
						text(
							"div",
							"wdPaletteItemDesc",
							String(item.shortDescription || ""),
						),
					);
				}
				const btn = /** @type {HTMLButtonElement} */ (
					text("button", "btn btnSmall", "Add")
				);
				btn.type = "button";
				btn.disabled = !(state.canAdd && state.canAdd(sid));
				btn.classList.toggle("is-disabled", btn.disabled);
				btn.addEventListener("click", function () {
					state.addStep && state.addStep(sid);
				});
				row.appendChild(meta);
				row.appendChild(btn);
				list.appendChild(row);
			});
		}

		search.addEventListener("input", function () {
			renderList();
		});
		if (!_focusHandlerBound) {
			_focusHandlerBound = true;
			window.addEventListener("am2:palette:focus", function () {
				try {
					_lastSearch && _lastSearch.focus();
				} catch (e) {
					// ignore
				}
				if (_lastMount && _lastMount.classList) {
					_lastMount.classList.add("wdPaletteAttention");
					window.setTimeout(function () {
						if (_lastMount) _lastMount.classList.remove("wdPaletteAttention");
					}, 900);
				}
			});
		}
		renderList();
	}

	window.AM2WDPaletteRender = { renderPalette: renderPalette };
})();
