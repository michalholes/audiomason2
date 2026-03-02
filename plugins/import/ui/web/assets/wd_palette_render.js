(function () {
	"use strict";

	/** @type {any} */
	const W = window;

	let _focusHandlerBound = false;
	let _lastSearch = null;
	let _lastMount = null;

	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	function renderPalette(opts) {
		const mount = opts && opts.mount;
		const items = (opts && opts.items) || [];
		const state = (opts && opts.state) || {};
		const el = (opts && opts.el) || function () {};
		const text = (opts && opts.text) || function () {};

		if (!mount) return;
		clear(mount);

		const searchWrap = el("div", "wdPaletteSearch");
		const search = el("input", "wdPaletteSearchInput");
		search.type = "search";
		search.placeholder = "Search steps...";
		searchWrap.appendChild(search);
		mount.appendChild(searchWrap);

		const list = el("div", "wdPaletteGroups");
		mount.appendChild(list);

		function matches(it, q) {
			if (!q) return true;
			const s = (
				String((it && it.step_id) || "") +
				" " +
				String((it && it.displayName) || "") +
				" " +
				String((it && it.shortDescription) || "") +
				" " +
				String((it && it.title) || "")
			)
				.toLowerCase()
				.trim();
			return s.indexOf(q.toLowerCase().trim()) >= 0;
		}

		_lastSearch = search;
		_lastMount = mount;

		function renderList() {
			clear(list);
			const q = String(search.value || "");

			const groups = [
				{ kind: "mandatory", title: "Mandatory Steps" },
				{ kind: "optional", title: "Optional Steps" },
				{ kind: "conditional", title: "Conditional Steps" },
			];

			function groupItems(kind) {
				return (Array.isArray(items) ? items : []).filter(function (it) {
					if (!it) return false;
					if (String(it.kind || "") !== kind) return false;
					return matches(it, q);
				});
			}

			groups.forEach(function (g) {
				const group = el("div", "wdPaletteGroup");
				group.appendChild(text("div", "wdPaletteGroupTitle", g.title));

				const rows = el("div", "wdPaletteGroupRows");
				const arr = groupItems(g.kind);

				arr.forEach(function (it) {
					const sid = String(it && it.step_id ? it.step_id : "");
					if (!sid) return;

					const row = el("div", "wdPaletteItem");
					const meta = el("div", "wdPaletteMeta");

					const idRow = el("div", "wdPaletteItemIdRow");
					if (String(it.pinned || "") !== "none") {
						const pin = text(
							"span",
							"wdPalettePinned",
							String(it.pinned || ""),
						);
						idRow.appendChild(pin);
					}
					idRow.appendChild(text("span", "wdPaletteItemId", sid));
					if (g.kind === "mandatory") {
						const lock =
							W.AM2WDDomIcons && W.AM2WDDomIcons.svgIcon
								? W.AM2WDDomIcons.svgIcon("lock", "wdSvg", "Mandatory")
								: null;
						if (lock) idRow.appendChild(lock);
					}
					meta.appendChild(idRow);

					meta.appendChild(
						text(
							"div",
							"wdPaletteItemTitle",
							String(it.displayName || it.title || sid),
						),
					);

					if (it && it.shortDescription) {
						meta.appendChild(
							text(
								"div",
								"wdPaletteItemDesc",
								String(it.shortDescription || ""),
							),
						);
					}

					let btn = null;
					if (g.kind === "mandatory") {
						btn = text("button", "btn btnSmall", "Locked");
						btn.type = "button";
						btn.disabled = true;
						btn.classList.add("is-disabled");
					} else {
						btn = text("button", "btn btnSmall", "Add");
						btn.type = "button";
						btn.disabled = !(state.canAdd && state.canAdd(sid));
						btn.classList.toggle("is-disabled", btn.disabled);
						btn.addEventListener("click", function () {
							state.addStep && state.addStep(sid);
						});
					}

					row.appendChild(meta);
					row.appendChild(btn);
					rows.appendChild(row);
				});

				group.appendChild(rows);
				list.appendChild(group);
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
						_lastMount && _lastMount.classList.remove("wdPaletteAttention");
					}, 900);
				}
			});
		}

		renderList();
	}

	/** @type {any} */ (window).AM2WDPaletteRender = {
		renderPalette: renderPalette,
	};
})();
