(() => {
	const root =
		/** @type {(Window & typeof globalThis) & { AM2ImportWizardV3Helpers?: unknown }} */ (
			typeof window !== "undefined" ? window : globalThis
		);

	/** @param {AM2JsonValue | undefined} value */
	function isScalar(value) {
		return (
			typeof value === "string" ||
			typeof value === "number" ||
			typeof value === "boolean"
		);
	}

	/** @param {AM2ImportPromptModel} model @returns {AM2JsonValue} */
	function seedValue(model) {
		return model && model.prefill !== null
			? model.prefill
			: model.default_value;
	}

	/** @param {AM2JsonValue | undefined} value */
	function serializeSeed(value) {
		if (value === null || value === undefined) return "";
		if (isScalar(value)) return String(value);
		try {
			return JSON.stringify(value, null, 2);
		} catch {
			return String(value);
		}
	}

	/** @param {string} raw @returns {AM2JsonValue | string} */
	function parseLooseJson(raw) {
		if (raw === "") return "";
		try {
			return JSON.parse(raw);
		} catch {
			return raw;
		}
	}

	/** @param {AM2PromptNode | null | undefined} node @returns {Node[]} */
	function childNodes(node) {
		if (!node || typeof node !== "object") return [];
		/** @type {Node[] | NodeListOf<ChildNode> | HTMLCollection} */
		const children =
			node.children && typeof node.children !== "string"
				? node.children
				: node.childNodes && typeof node.childNodes !== "string"
					? node.childNodes
					: /** @type {Node[]} */ ([]);
		try {
			return Array.from(children);
		} catch {
			return [];
		}
	}

	/** @param {AM2PromptNode | null | undefined} node */
	function tagName(node) {
		if (!node || typeof node !== "object") return "";
		if (typeof node.tagName === "string") return node.tagName.toLowerCase();
		if (typeof node.tag === "string") return node.tag.toLowerCase();
		return "";
	}

	/** @param {AM2PromptNode | null | undefined} node @param {string} name */
	function getAttr(node, name) {
		if (!node || typeof node !== "object") return null;
		if (typeof node.getAttribute === "function") {
			const value = node.getAttribute(name);
			if (value !== null && value !== undefined) return String(value);
		}
		if (node.attrs && Object.prototype.hasOwnProperty.call(node.attrs, name)) {
			return String(node.attrs[name]);
		}
		if (name.startsWith("data-") && node.dataset) {
			const key = name
				.slice(5)
				.replace(/-([a-z])/g, (_, ch) => ch.toUpperCase());
			if (Object.prototype.hasOwnProperty.call(node.dataset, key)) {
				return String(node.dataset[key]);
			}
		}
		return null;
	}

	/**
	 * @param {AM2PromptNode | null | undefined} node
	 * @param {string} name
	 * @param {string | number | boolean} value
	 */
	function setAttr(node, name, value) {
		if (!node || typeof node !== "object") return;
		if (typeof node.setAttribute === "function") {
			node.setAttribute(name, String(value));
		}
		if (!node.attrs || typeof node.attrs !== "object") node.attrs = {};
		node.attrs[name] = String(value);
	}

	/**
	 * @param {AM2PromptNode | null | undefined} node
	 * @param {string} type
	 * @param {(event: Event) => void} handler
	 */
	function addEvent(node, type, handler) {
		if (!node || typeof node !== "object") return;
		if (typeof node.addEventListener === "function") {
			node.addEventListener(type, handler);
		}
		/** @type {AM2PromptNode & Record<string, unknown>} */ (node)[`on${type}`] =
			handler;
	}

	/** @param {HTMLElement | null | undefined} mount */
	function clearMount(mount) {
		if (!mount) return;
		if (typeof mount.replaceChildren === "function") {
			mount.replaceChildren();
			return;
		}
		if (Array.isArray(mount.children)) {
			/** @type {AM2JsonObject & { children?: Node[] }} */ (
				/** @type {unknown} */ (mount)
			).children = [];
			return;
		}
		while (mount.firstChild && typeof mount.removeChild === "function") {
			mount.removeChild(mount.firstChild);
		}
	}

	/**
	 * @param {AM2PromptNode | null | undefined} node
	 * @param {AM2PromptPredicate} visit
	 * @returns {boolean}
	 */
	function walkNodes(node, visit) {
		if (!node || typeof node !== "object") return false;
		if (visit(node)) return true;
		return childNodes(node).some((child) => walkNodes(child, visit));
	}

	/**
	 * @param {AM2PromptNode | null | undefined} node
	 * @param {AM2PromptPredicate} predicate
	 * @returns {AM2PromptNode | null}
	 */
	function findNode(node, predicate) {
		let found = null;
		walkNodes(node, (entry) => {
			if (predicate(entry)) {
				found = entry;
				return true;
			}
			return false;
		});
		return found;
	}

	/**
	 * @param {AM2PromptNode | null | undefined} node
	 * @param {AM2PromptPredicate} predicate
	 * @returns {AM2PromptNode[]}
	 */
	function findNodes(node, predicate) {
		/** @type {AM2PromptNode[]} */
		const found = [];
		walkNodes(node, (entry) => {
			if (predicate(entry)) found.push(entry);
			return false;
		});
		return found;
	}

	/** @param {HTMLElement} mount @returns {HTMLElement | null} */
	function findBodyMount(mount) {
		return /** @type {HTMLElement | null} */ (
			findNode(mount, (node) => getAttr(node, "data-v3-step-body") === "1")
		);
	}

	/** @param {HTMLElement} mount @param {AM2PromptElementFactory} makeEl @returns {HTMLElement} */
	function ensureBodyMount(mount, makeEl) {
		const existing = findBodyMount(mount);
		if (existing) return /** @type {HTMLElement} */ (existing);
		const body = makeEl("div", { "data-v3-step-body": "1" });
		mount.appendChild(body);
		return body;
	}

	/** @param {AM2ImportPromptBodyState | null | undefined} bodyState */
	function markDirty(bodyState) {
		if (bodyState) bodyState.dirty = true;
	}

	/** @param {AM2JsonValue | undefined} value */
	function serializeDropdownValue(value) {
		if (value === null || value === undefined) return "";
		return JSON.stringify(value);
	}

	/** @param {AM2JsonValue | string | undefined} raw @param {number} count @returns {Set<number>} */
	function selectionSetFromExpr(raw, count) {
		const text = typeof raw === "string" ? raw.trim() : "";
		const out = new Set();
		if (text === "") return out;
		if (text === "all") {
			for (let index = 0; index < count; index += 1) out.add(index);
			return out;
		}
		text.split(",").forEach((part) => {
			if (!/^\d+$/.test(part.trim())) return;
			const ordinal = Number(part.trim());
			if (ordinal >= 1 && ordinal <= count) out.add(ordinal - 1);
		});
		return out;
	}

	/** @param {Set<number> | null | undefined} selectionSet @param {number} count */
	function selectionExprFromSet(selectionSet, count) {
		const chosen = Array.from(selectionSet || []).filter(
			(index) => Number.isInteger(index) && index >= 0 && index < count,
		);
		chosen.sort((left, right) => left - right);
		if (count > 0 && chosen.length === count) return "all";
		if (!chosen.length) return "";
		return chosen.map((index) => String(index + 1)).join(",");
	}

	/**
	 * @param {AM2ImportPromptBodyState | null | undefined} bodyState
	 * @returns {AM2JsonValue | null}
	 */
	function extractLocalDraft(bodyState) {
		if (!bodyState || !bodyState.dirty) return null;
		if (bodyState.mode === "confirm") {
			const editor = /** @type {HTMLInputElement | null} */ (bodyState.editor);
			return !!(editor && editor.checked);
		}
		if (
			bodyState.mode === "checklist" ||
			bodyState.mode === "filterable-checklist"
		) {
			return selectionExprFromSet(
				bodyState.selectionSet,
				bodyState.model ? bodyState.model.items.length : 0,
			);
		}
		if (!bodyState.editor) return null;
		if (bodyState.mode === "dropdown") {
			return parseLooseJson(
				String(
					/** @type {HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement} */ (
						bodyState.editor
					).value || "",
				),
			);
		}
		return String(
			/** @type {HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement} */ (
				bodyState.editor
			).value || "",
		);
	}

	/** @param {AM2ImportPromptModel} model @param {AM2JsonValue | null | undefined} localDraft */
	function resolveSelectionSeed(model, localDraft) {
		if (typeof localDraft === "string") return localDraft;
		const seed = seedValue(model);
		return typeof seed === "string" ? seed : "";
	}

	/**
	 * @param {AM2ImportPromptModel} model
	 * @param {string | null | undefined} filterText
	 * @returns {number[]}
	 */
	function visibleItemIndices(model, filterText) {
		const needle = String(filterText || "")
			.trim()
			.toLowerCase();
		return model.items
			.map((item, index) => ({ item, index }))
			.filter(({ item }) => {
				if (!needle) return true;
				const haystack = `${item.label} ${item.item_id}`.toLowerCase();
				return haystack.includes(needle);
			})
			.map(({ index }) => index);
	}

	/**
	 * @param {HTMLElement} body
	 * @param {AM2PromptElementFactory} makeEl
	 * @param {string | null | undefined} text
	 * @param {string | null | undefined} className
	 */
	function appendHint(body, makeEl, text, className) {
		if (!text) return;
		body.appendChild(makeEl("div", { class: className || "hint", text }));
	}

	/**
	 * @param {HTMLElement} body
	 * @param {AM2PromptElementFactory} makeEl
	 * @param {AM2JsonValue[]} examples
	 */
	function renderExamplesList(body, makeEl, examples) {
		if (!examples.length) return;
		const list = makeEl("ul", { class: "hint" });
		examples.forEach((example) => {
			list.appendChild(makeEl("li", { text: serializeSeed(example) }));
		});
		body.appendChild(list);
	}

	/**
	 * @param {AM2PromptElementFactory} makeEl
	 * @param {string} mode
	 * @param {string} key
	 * @returns {HTMLInputElement | HTMLTextAreaElement}
	 */
	function createInputNode(makeEl, mode, key) {
		if (mode === "textarea") {
			return /** @type {HTMLTextAreaElement} */ (
				makeEl("textarea", { rows: "6", "data-v3-payload-key": key })
			);
		}
		/** @type {Record<string, string>} */
		const attrs = { "data-v3-payload-key": key };
		if (mode === "number") attrs.type = "number";
		return /** @type {HTMLInputElement} */ (makeEl("input", attrs));
	}

	/**
	 * @param {AM2ImportPromptBodyState | null | undefined} bodyState
	 * @param {AM2PromptElementFactory} makeEl
	 * @param {string} mode
	 * @param {string} key
	 */
	function ensureTextEditor(bodyState, makeEl, mode, key) {
		if (bodyState && bodyState.mode === mode && bodyState.editor) {
			return /** @type {HTMLInputElement | HTMLTextAreaElement} */ (
				bodyState.editor
			);
		}
		return createInputNode(makeEl, mode, key);
	}

	/** @param {HTMLElement} editor @param {AM2ImportPromptBodyState} bodyState */
	function bindTextEditor(editor, bodyState) {
		addEvent(editor, "input", () => markDirty(bodyState));
		addEvent(editor, "change", () => markDirty(bodyState));
	}

	root.AM2ImportWizardV3Helpers = {
		childNodes,
		tagName,
		getAttr,
		setAttr,
		addEvent,
		clearMount,
		walkNodes,
		findNode,
		findNodes,
		findBodyMount,
		ensureBodyMount,
		markDirty,
		serializeDropdownValue,
		selectionSetFromExpr,
		selectionExprFromSet,
		extractLocalDraft,
		resolveSelectionSeed,
		visibleItemIndices,
		appendHint,
		renderExamplesList,
		createInputNode,
		ensureTextEditor,
		bindTextEditor,
	};
})();
