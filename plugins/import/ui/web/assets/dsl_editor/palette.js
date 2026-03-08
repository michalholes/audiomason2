(function () {
	"use strict";

	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	function el(tag, cls, textValue) {
		const node = document.createElement(tag);
		if (cls) node.className = cls;
		if (textValue !== undefined) node.textContent = String(textValue);
		return node;
	}

	function primitiveLine(item) {
		const pid = String(item.primitive_id || "");
		const version = Number(item.version || 0);
		return pid + "@" + version;
	}

	function matches(item, searchText) {
		if (!searchText) return true;
		const hay = [
			primitiveLine(item),
			String(item.determinism_notes || ""),
			String(item.phase || ""),
		]
			.join(" ")
			.toLowerCase();
		return hay.indexOf(searchText.toLowerCase()) >= 0;
	}

	function renderPalette(opts) {
		const mount = opts && opts.mount;
		if (!mount) return;
		clear(mount);

		const state = (opts && opts.state) || {};
		const registry = Array.isArray(opts && opts.registry) ? opts.registry : [];
		const onSearch =
			typeof state.onSearch === "function" ? state.onSearch : function () {};
		const onAdd =
			typeof state.onAddPrimitive === "function"
				? state.onAddPrimitive
				: function () {};
		const searchText = String(state.searchText || "");

		const wrap = el("div", "flowStepSection");
		wrap.appendChild(el("div", "flowStepSectionTitle", "Primitive Palette"));

		const search = document.createElement("input");
		search.value = searchText;
		search.placeholder = "Search primitives";
		search.addEventListener("input", function () {
			onSearch(search.value || "");
		});
		wrap.appendChild(search);

		const list = el("div", "flowStepHistory");
		registry
			.filter((item) => matches(item, searchText))
			.forEach((item) => {
				const row = el("div", "historyItem");
				row.setAttribute("data-am2-palette-primitive", primitiveLine(item));
				const meta = el("div", "historyMeta");
				meta.appendChild(el("div", null, primitiveLine(item)));
				meta.appendChild(
					el(
						"div",
						null,
						"phase=" +
							String(item.phase || "") +
							" " +
							String(item.determinism_notes || ""),
					),
				);
				const btn = el("button", "btn", "Add Node");
				btn.type = "button";
				btn.setAttribute("data-am2-palette-add", primitiveLine(item));
				btn.addEventListener("click", function () {
					onAdd(item);
				});
				row.appendChild(meta);
				row.appendChild(btn);
				list.appendChild(row);
			});
		wrap.appendChild(list);
		mount.appendChild(wrap);
	}

	window["AM2DSLEditorPalette"] = { renderPalette: renderPalette };
})();
