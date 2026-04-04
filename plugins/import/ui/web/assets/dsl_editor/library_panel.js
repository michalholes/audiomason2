/// <reference path="../../../../../../types/am2-import-ui-globals.d.ts" />
(function () {
	"use strict";

	/** @param {Node | null} node */
	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	/** @param {string} tag @param {string | null | undefined} cls @param {unknown=} textValue */
	function el(tag, cls, textValue) {
		const node = document.createElement(tag);
		if (cls) node.className = cls;
		if (textValue !== undefined) node.textContent = String(textValue);
		return node;
	}

	/** @param {string} label @returns {HTMLButtonElement} */
	function button(label) {
		const node = document.createElement("button");
		node.className = "btn";
		node.type = "button";
		node.textContent = label;
		return node;
	}

	/** @param {string} labelText @param {HTMLElement} inputNode */
	function row(labelText, inputNode) {
		const wrap = el("label", "flowField");
		wrap.appendChild(el("div", "flowStepSectionTitle", labelText));
		wrap.appendChild(inputNode);
		return wrap;
	}

	/** @param {AM2DSLEditorLibrary | null} library */
	function cloneParams(library) {
		return /** @type {AM2DSLEditorLibraryParam[]} */ (
			JSON.parse(JSON.stringify((library && library.params) || []))
		);
	}

	/** @param {AM2JsonObject} definition @returns {Record<string, AM2DSLEditorLibrary>} */
	function libraries(definition) {
		const raw = definition && definition.libraries;
		return raw && typeof raw === "object"
			? /** @type {Record<string, AM2DSLEditorLibrary>} */ (raw)
			: {};
	}

	/** @param {AM2DSLEditorLibraryPanelOptions} opts */
	function renderLibraryPanel(opts) {
		const mount = opts && opts.mount;
		if (!mount) return;
		clear(mount);
		const definition = (opts && opts.definition) || {};
		/** @type {AM2DSLEditorLibraryPanelState} */
		const state = opts && opts.state ? opts.state : { selectedLibraryId: "" };
		const actions = (opts && opts.actions) || {};
		const onAddLibrary =
			typeof actions.onAddLibrary === "function"
				? actions.onAddLibrary
				: function () {};
		const onPatchLibrary =
			typeof actions.onPatchLibrary === "function"
				? actions.onPatchLibrary
				: function () {};
		const onRemoveLibrary =
			typeof actions.onRemoveLibrary === "function"
				? actions.onRemoveLibrary
				: function () {};
		const onSelectLibrary =
			typeof actions.onSelectLibrary === "function"
				? actions.onSelectLibrary
				: function () {};
		const onSelectRoot =
			typeof actions.onSelectRoot === "function"
				? actions.onSelectRoot
				: function () {};
		const selectedLibraryId = String(state.selectedLibraryId || "");
		const allLibraries = libraries(definition);
		const selectedLibrary = allLibraries[selectedLibraryId] || null;

		const wrap = el("div", "flowStepSection");
		wrap.setAttribute("data-am2-library-panel", "true");
		wrap.appendChild(el("div", "flowStepSectionTitle", "Libraries"));

		const rootBtn = button("Edit Main Graph");
		rootBtn.setAttribute("data-am2-library-select", "root");
		rootBtn.addEventListener("click", function () {
			onSelectRoot();
		});
		wrap.appendChild(rootBtn);

		Object.keys(allLibraries)
			.sort()
			.forEach(function (libraryId) {
				const library = allLibraries[libraryId] || {};
				const card = el("div", "flowStepSection");
				card.setAttribute("data-am2-library-card", libraryId);
				card.appendChild(
					el(
						"div",
						"flowStepDesc",
						libraryId +
							" nodes=" +
							String((library.nodes || []).length) +
							" params=" +
							String((library.params || []).length),
					),
				);
				const editBtn = button("Edit Library");
				editBtn.setAttribute("data-am2-library-select", libraryId);
				editBtn.addEventListener("click", function () {
					onSelectLibrary(libraryId);
				});
				card.appendChild(editBtn);
				if (libraryId === selectedLibraryId) {
					const removeBtn = button("Delete Library");
					removeBtn.setAttribute("data-am2-library-remove", libraryId);
					removeBtn.addEventListener("click", function () {
						onRemoveLibrary(libraryId);
					});
					card.appendChild(removeBtn);
				}
				wrap.appendChild(card);
			});

		const newIdInput = document.createElement("input");
		newIdInput.setAttribute("data-am2-library-new-id", "true");
		wrap.appendChild(row("new library id", newIdInput));
		const addBtn = button("Add Library");
		addBtn.setAttribute("data-am2-library-add", "true");
		addBtn.addEventListener("click", function () {
			onAddLibrary(newIdInput.value || "library");
		});
		wrap.appendChild(addBtn);

		if (selectedLibrary) {
			const editor = el("div", "flowStepSection");
			editor.setAttribute("data-am2-library-editor", selectedLibraryId);
			editor.appendChild(
				el(
					"div",
					"flowStepDesc",
					"Editing library graph and declaration for " +
						selectedLibraryId +
						".",
				),
			);
			const entrySelect = document.createElement("select");
			const emptyOption = document.createElement("option");
			emptyOption.value = "";
			emptyOption.textContent = "(unset)";
			emptyOption.selected = !selectedLibrary.entry_step_id;
			entrySelect.appendChild(emptyOption);
			(selectedLibrary.nodes || []).forEach(function (node) {
				const option = document.createElement("option");
				option.value = String(node.step_id || "");
				option.textContent = String(node.step_id || "");
				option.selected =
					option.value === String(selectedLibrary.entry_step_id || "");
				entrySelect.appendChild(option);
			});
			entrySelect.setAttribute(
				"data-am2-library-entry-step",
				selectedLibraryId,
			);
			entrySelect.addEventListener("change", function () {
				onPatchLibrary({ entry_step_id: entrySelect.value || "" });
			});
			editor.appendChild(row("entry_step_id", entrySelect));

			const params = cloneParams(selectedLibrary);
			params.forEach(function (param, index) {
				const card = el("div", "flowStepSection");
				const nameInput = document.createElement("input");
				nameInput.value = String((param && param.name) || "");
				nameInput.setAttribute("data-am2-library-param-name", String(index));
				nameInput.addEventListener("change", function () {
					const next = cloneParams(selectedLibrary);
					next[index] = {
						name: nameInput.value || "",
						required: !!(next[index] && next[index].required),
					};
					onPatchLibrary({ params: next });
				});
				card.appendChild(row("param name", nameInput));

				const requiredSelect = document.createElement("select");
				[
					{ value: "false", label: "optional" },
					{ value: "true", label: "required" },
				].forEach(function (item) {
					const option = document.createElement("option");
					option.value = item.value;
					option.textContent = item.label;
					option.selected = String(!!param.required) === item.value;
					requiredSelect.appendChild(option);
				});
				requiredSelect.setAttribute(
					"data-am2-library-param-required",
					String(index),
				);
				requiredSelect.addEventListener("change", function () {
					const next = cloneParams(selectedLibrary);
					next[index] = {
						name: String((next[index] && next[index].name) || ""),
						required: requiredSelect.value === "true",
					};
					onPatchLibrary({ params: next });
				});
				card.appendChild(row("required", requiredSelect));

				const removeBtn = button("Remove Param");
				removeBtn.setAttribute("data-am2-library-param-remove", String(index));
				removeBtn.addEventListener("click", function () {
					const next = cloneParams(selectedLibrary).filter(
						function (_item, idx) {
							return idx !== index;
						},
					);
					onPatchLibrary({ params: next });
				});
				card.appendChild(removeBtn);
				editor.appendChild(card);
			});

			const addParamBtn = button("Add Param");
			addParamBtn.setAttribute("data-am2-library-param-add", "true");
			addParamBtn.addEventListener("click", function () {
				const next = cloneParams(selectedLibrary);
				next.push({
					name: "param_" + String(next.length + 1),
					required: false,
				});
				onPatchLibrary({ params: next });
			});
			editor.appendChild(addParamBtn);
			wrap.appendChild(editor);
		}

		mount.appendChild(wrap);
	}

	window.AM2DSLEditorLibraryPanel = { renderLibraryPanel };
})();
