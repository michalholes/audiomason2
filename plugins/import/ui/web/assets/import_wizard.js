/// <reference path="../../../../../am2-globals.d.ts" />
(() => {
	/**
	 * @typedef {AM2ImportWizardField & {
	 * 	constraints?: { min?: number; max?: number } | null,
	 * }} AM2ImportWizardLegacyField
	 */

	/**
	 * @typedef {{
	 * 	root: HTMLInputElement | null,
	 * 	path: HTMLInputElement | null,
	 * 	mode: HTMLSelectElement | null,
	 * 	start: HTMLButtonElement | null,
	 * 	resumeExisting: HTMLButtonElement | null,
	 * 	startNew: HTMLButtonElement | null,
	 * 	cancelPendingStart: HTMLButtonElement | null,
	 * 	reload: HTMLButtonElement | null,
	 * 	submit: HTMLButtonElement | null,
	 * 	step: HTMLElement | null,
	 * }} AM2ImportWizardDOM
	 */

	/**
	 * @typedef {{ [name: string]: string[] }} AM2GroupedSelections
	 */

	/**
	 * @typedef {Error & {
	 * 	status?: number,
	 * 	data?: unknown,
	 * }} AM2FetchError
	 */

	/**
	 * @param {string} url
	 * @param {RequestInit} [opts]
	 * @returns {Promise<AM2JsonObject>}
	 */
	async function fetchJSON(url, opts) {
		const r = await fetch(url, opts || {});
		const ct = (r.headers.get("content-type") || "").toLowerCase();
		const text = await r.text();
		let data = null;
		if (ct.includes("application/json")) {
			try {
				data = JSON.parse(text || "{}");
			} catch {
				data = { text };
			}
		} else {
			try {
				data = JSON.parse(text || "{}");
			} catch {
				data = { text };
			}
		}
		if (!r.ok) {
			const msg =
				data && data.error && data.error.message
					? String(data.error.message)
					: text || `${r.status} ${r.statusText}`;
			const err = /** @type {AM2FetchError} */ (new Error(msg));
			err.status = r.status;
			err.data = data;
			throw err;
		}
		return data;
	}

	/**
	 * @param {string} tag
	 * @param {Record<string, string | number | boolean | null | undefined> | null} [attrs]
	 * @param {Node[] | null} [children]
	 * @returns {HTMLElement}
	 */
	function el(tag, attrs, children) {
		const n = document.createElement(tag);
		if (attrs && typeof attrs === "object") {
			for (const [k, v] of Object.entries(attrs)) {
				if (k === "class") n.className = String(v);
				else if (k === "text") n.textContent = String(v);
				else n.setAttribute(k, String(v));
			}
		}
		(children || []).forEach((c) => {
			n.appendChild(c);
		});
		return n;
	}

	/**
	 * @param {Node | null} node
	 * @returns {void}
	 */
	function clear(node) {
		if (!node) return;
		while (node.firstChild) node.removeChild(node.firstChild);
	}

	/**
	 * @param {string} id
	 * @param {unknown} text
	 * @returns {void}
	 */
	function setText(id, text) {
		const n = document.getElementById(id);
		if (n) n.textContent = String(text || "");
	}

	/**
	 * @param {string} id
	 * @param {unknown} obj
	 * @returns {void}
	 */
	function setPre(id, obj) {
		const n = document.getElementById(id);
		if (!n) return;
		n.textContent = obj ? JSON.stringify(obj, null, 2) : "";
	}

	/**
	 * @param {AM2ImportWizardLegacyField | null | undefined} fld
	 * @returns {string}
	 */
	function fieldName(fld) {
		return fld && typeof fld.name === "string" ? fld.name : "";
	}

	/**
	 * @param {AM2ImportWizardLegacyField | null | undefined} fld
	 * @returns {string}
	 */
	function fieldType(fld) {
		return fld && typeof fld.type === "string" ? fld.type : "text";
	}

	/**
	 * @param {string} ftype
	 * @param {AM2ImportWizardLegacyField | null | undefined} fld
	 * @returns {void}
	 */
	function renderUnsupported(ftype, fld) {
		const meta =
			fld && typeof fld === "object" ? JSON.stringify(fld, null, 2) : "";
		const msg =
			"Unsupported field type: " + String(ftype || "") + "\n\n" + meta;
		setText("stepError", msg);
	}

	/**
	 * @param {AM2ImportWizardState | null} state
	 * @param {string} name
	 * @returns {AM2JsonValue | null}
	 */
	function readAnswer(state, name) {
		const ans =
			state && state.answers && typeof state.answers === "object"
				? state.answers
				: null;
		if (ans && name in ans) return ans[name];
		const inp =
			state && state.inputs && typeof state.inputs === "object"
				? state.inputs
				: null;
		if (inp && name in inp) return inp[name];
		return null;
	}

	/**
	 * @param {AM2ImportWizardLegacyField | null | undefined} fld
	 * @returns {Array<AM2ImportWizardFieldOption | string>}
	 */
	function normalizeItems(fld) {
		const items = fld && Array.isArray(fld.items) ? fld.items : null;
		if (items) return items;
		const opts = fld && Array.isArray(fld.options) ? fld.options : null;
		return opts || [];
	}

	/**
	 * @param {AM2ImportWizardFieldOption | string | null | undefined} it
	 * @returns {string}
	 */
	function itemId(it) {
		if (it && typeof it === "object") {
			if (typeof it.item_id === "string") return it.item_id;
			if (typeof it.value === "string") return it.value;
		}
		return String(it || "");
	}

	/**
	 * @param {AM2ImportWizardFieldOption | string | null | undefined} it
	 * @returns {string}
	 */
	function itemLabel(it) {
		if (it && typeof it === "object") {
			if (typeof it.label === "string") return it.label;
			if (typeof it.display_label === "string") return it.display_label;
			if (typeof it.value === "string") return it.value;
			if (typeof it.item_id === "string") return it.item_id;
		}
		return String(it || "");
	}

	/** @type {AM2ImportWizardDOM} */
	const ui = {
		root: /** @type {HTMLInputElement|null} */ (
			document.getElementById("root")
		),
		path: /** @type {HTMLInputElement|null} */ (
			document.getElementById("path")
		),
		mode: /** @type {HTMLSelectElement|null} */ (
			document.getElementById("mode")
		),
		start: /** @type {HTMLButtonElement|null} */ (
			document.getElementById("start")
		),
		resumeExisting: /** @type {HTMLButtonElement|null} */ (
			document.getElementById("resumeExisting")
		),
		startNew: /** @type {HTMLButtonElement|null} */ (
			document.getElementById("startNew")
		),
		cancelPendingStart: /** @type {HTMLButtonElement|null} */ (
			document.getElementById("cancelPendingStart")
		),
		reload: /** @type {HTMLButtonElement|null} */ (
			document.getElementById("reload")
		),
		submit: /** @type {HTMLButtonElement|null} */ (
			document.getElementById("submit")
		),
		step: document.getElementById("step"),
	};

	if (
		!ui.root ||
		!ui.path ||
		!ui.mode ||
		!ui.start ||
		!ui.reload ||
		!ui.submit ||
		!ui.step
	) {
		return;
	}

	const rootInput = ui.root;
	const pathInput = ui.path;
	const modeSelect = ui.mode;
	const startButton = ui.start;
	const reloadButton = ui.reload;
	const submitButton = ui.submit;
	const stepMount = ui.step;

	/** @param {unknown} errorLike */
	function errorMessage(errorLike) {
		return errorLike instanceof Error
			? errorLike.message
			: String(errorLike || "");
	}

	/**
	 * @returns {void}
	 */
	function initTabs() {
		const wrap = document.getElementById("tabs");
		if (!wrap) return;
		const btns = /** @type {HTMLElement[]} */ (
			Array.from(wrap.querySelectorAll(".tabBtn"))
		);
		const panels = /** @type {HTMLElement[]} */ (
			Array.from(document.querySelectorAll(".tabPanel"))
		);

		let flowAutoLoaded = false;

		/**
		 * @param {number} attempt
		 * @returns {void}
		 */
		function tryFlowAutoReload(attempt) {
			const fn = window.AM2UI && window.AM2UI.doReloadAll;
			if (typeof fn === "function") {
				void fn();
				return;
			}
			if (attempt >= 3) return;
			const delays = [0, 50, 200];
			setTimeout(() => tryFlowAutoReload(attempt + 1), delays[attempt] || 0);
		}

		/**
		 * @param {string} tab
		 * @returns {void}
		 */
		function activate(tab) {
			btns.forEach((b) => {
				b.classList.toggle("active", b.dataset.tab === tab);
			});
			panels.forEach((p) => {
				p.classList.toggle("active", p.dataset.panel === tab);
			});

			if (tab === "flow" && !flowAutoLoaded) {
				flowAutoLoaded = true;
				queueMicrotask(() => tryFlowAutoReload(0));
			}
		}

		btns.forEach((b) => {
			b.addEventListener("click", () =>
				activate(String(b.dataset.tab || "run")),
			);
		});
		activate("run");
	}

	const v3Renderer = /** @type {AM2ImportWizardV3Api | null} */ (
		typeof window !== "undefined" ? window.AM2ImportWizardV3 || null : null
	);
	const promptHelpers = /** @type {AM2ImportWizardV3HelpersApi | null} */ (
		typeof window !== "undefined"
			? window.AM2ImportWizardV3Helpers || null
			: null
	);

	/** @type {string | null} */
	let sessionId = null;
	/** @type {AM2ImportWizardFlow | null} */
	let flow = null;
	/** @type {AM2ImportWizardState | null} */
	let state = null;
	/** @type {AM2ImportEffectiveModel | null} */
	let sessionEffectiveModel = null;
	/** @type {string | null} */
	let currentStep = null;
	/** @type {AM2ImportStartConflict | null} */
	let pendingStartConflict = null;

	initTabs();

	/**
	 * @returns {Promise<void>}
	 */
	async function loadFlow() {
		flow = await fetchJSON("/import/ui/flow");
	}

	/**
	 * @returns {Promise<void>}
	 */
	async function loadState() {
		if (!sessionId) {
			state = null;
			return;
		}
		const sid = encodeURIComponent(sessionId);
		state = await fetchJSON(`/import/ui/session/${sid}/state`);
		sessionEffectiveModel =
			state && typeof state.effective_model === "object"
				? state.effective_model
				: null;
	}

	/**
	 * @returns {AM2ImportWizardStep[]}
	 */
	function _resolvedSteps() {
		const sSteps =
			sessionEffectiveModel && Array.isArray(sessionEffectiveModel.steps)
				? sessionEffectiveModel.steps
				: null;
		if (sSteps) return sSteps;
		return flow && Array.isArray(flow.steps) ? flow.steps : [];
	}

	/**
	 * @param {string} stepId
	 * @returns {AM2ImportWizardStep | null}
	 */
	function _findSessionStep(stepId) {
		const steps =
			sessionEffectiveModel && Array.isArray(sessionEffectiveModel.steps)
				? sessionEffectiveModel.steps
				: [];
		return steps.find((s) => s && s.step_id === stepId) || null;
	}

	/**
	 * @param {string} stepId
	 * @param {string} field
	 * @returns {Array<AM2ImportWizardFieldOption | string>}
	 */
	function _sessionFieldItems(stepId, field) {
		const step = _findSessionStep(stepId);
		const fields = step && Array.isArray(step.fields) ? step.fields : [];
		const match = fields.find((f) => f && f.name === field) || null;
		const items = match && Array.isArray(match.items) ? match.items : null;
		return items || [];
	}

	/**
	 * @param {string} stepId
	 * @returns {AM2ImportWizardStep | null}
	 */
	function findStep(stepId) {
		const steps = _resolvedSteps();
		return steps.find((s) => s && s.step_id === stepId) || null;
	}

	/**
	 * @param {AM2ImportWizardLegacyField} fld
	 * @param {string} stepId
	 * @returns {HTMLElement}
	 */
	function renderField(fld, stepId) {
		const name = fieldName(fld);
		const ftype = fieldType(fld);
		const box = el("div", { class: "field" });
		box.appendChild(el("div", { class: "fieldName", text: name }));

		const cur = readAnswer(state, name);

		if (ftype === "toggle" || ftype === "confirm") {
			const row = el("div", { class: "choiceItem" });
			const inp = /** @type {HTMLInputElement} */ (
				el("input", { type: "checkbox" })
			);
			inp.checked = !!cur;
			inp.dataset.stepId = stepId;
			inp.dataset.field = name;
			inp.dataset.ftype = ftype;
			row.appendChild(inp);
			row.appendChild(el("div", { class: "hint", text: "" }));
			box.appendChild(row);
			return box;
		}

		if (ftype === "number") {
			const inp = /** @type {HTMLInputElement} */ (
				el("input", { type: "number" })
			);
			inp.value = cur === null || cur === undefined ? "" : String(cur);
			const c =
				fld && typeof fld.constraints === "object" ? fld.constraints : null;
			if (c && typeof c.min === "number") inp.min = String(c.min);
			if (c && typeof c.max === "number") inp.max = String(c.max);
			inp.dataset.stepId = stepId;
			inp.dataset.field = name;
			inp.dataset.ftype = ftype;
			box.appendChild(inp);
			return box;
		}

		if (ftype === "select") {
			const sel = /** @type {HTMLSelectElement} */ (el("select"));
			const items = sessionEffectiveModel
				? _sessionFieldItems(stepId, name)
				: normalizeItems(fld);
			items.forEach((it) => {
				const v = itemId(it);
				sel.appendChild(el("option", { value: v, text: itemLabel(it) }));
			});
			if (cur !== null && cur !== undefined) sel.value = String(cur);
			sel.dataset.stepId = stepId;
			sel.dataset.field = name;
			sel.dataset.ftype = ftype;
			box.appendChild(sel);
			return box;
		}

		if (ftype === "table_edit") {
			const ta = /** @type {HTMLTextAreaElement} */ (
				el("textarea", { rows: "10" })
			);
			if (typeof cur === "string") ta.value = cur;
			else ta.value = JSON.stringify(cur || [], null, 2);
			ta.dataset.stepId = stepId;
			ta.dataset.field = name;
			ta.dataset.ftype = ftype;
			box.appendChild(ta);
			return box;
		}

		if (ftype === "multi_select_indexed") {
			const items = sessionEffectiveModel
				? _sessionFieldItems(stepId, name)
				: normalizeItems(fld);
			const curArr = Array.isArray(cur) ? cur.map(String) : [];
			const list = el("div", { class: "choiceList" });
			items.forEach((it) => {
				const id = itemId(it);
				const row = el("label", { class: "choiceItem" });
				const cb = /** @type {HTMLInputElement} */ (
					el("input", { type: "checkbox" })
				);
				cb.checked = curArr.includes(String(id));
				cb.dataset.stepId = stepId;
				cb.dataset.field = name;
				cb.dataset.ftype = ftype;
				cb.dataset.itemId = String(id);
				row.appendChild(cb);
				row.appendChild(el("span", { text: itemLabel(it) }));
				list.appendChild(row);
			});
			box.appendChild(list);
			box.appendChild(
				el("div", {
					class: "hint",
					text: `Selection is sent as ${name}_ids`,
				}),
			);
			return box;
		}

		if (ftype === "text") {
			const inp = /** @type {HTMLInputElement} */ (el("input"));
			inp.value = cur === null || cur === undefined ? "" : String(cur);
			inp.dataset.stepId = stepId;
			inp.dataset.field = name;
			inp.dataset.ftype = ftype;
			box.appendChild(inp);
			return box;
		}

		renderUnsupported(ftype, fld);
		return box;
	}

	/**
	 * @param {string} stepId
	 * @returns {Record<string, AM2JsonValue>}
	 */
	function collectPayload(stepId) {
		setText("stepError", "");
		const step = findStep(stepId);
		if (
			v3Renderer &&
			state &&
			v3Renderer.isV3State(state) &&
			v3Renderer.isPromptStep(step)
		) {
			return v3Renderer.collectPayload({ mount: stepMount, step });
		}
		/** @type {Record<string, AM2JsonValue>} */
		const payload = {};

		const nodes = Array.from(
			stepMount.querySelectorAll("input,select,textarea"),
		);
		/** @type {AM2GroupedSelections} */
		const grouped = {};

		nodes.forEach((n) => {
			const node =
				/** @type {HTMLInputElement|HTMLSelectElement|HTMLTextAreaElement} */ (
					n
				);
			if (node.dataset.stepId !== stepId) return;
			const ftype = node.dataset.ftype || "";
			const name = node.dataset.field || "";
			if (!name) return;

			if (ftype === "multi_select_indexed") {
				if (!grouped[name]) grouped[name] = [];
				if (
					node instanceof HTMLInputElement &&
					node.getAttribute("type") === "checkbox" &&
					node.checked
				) {
					grouped[name].push(String(node.dataset.itemId || ""));
				}
				return;
			}

			if (
				n.tagName.toLowerCase() === "input" &&
				n.getAttribute("type") === "checkbox"
			) {
				payload[name] =
					node instanceof HTMLInputElement ? !!node.checked : false;
				return;
			}

			if (
				n.tagName.toLowerCase() === "input" &&
				n.getAttribute("type") === "number"
			) {
				if (node.value === "") payload[name] = null;
				else payload[name] = Number(node.value);
				return;
			}

			if (n.tagName.toLowerCase() === "textarea") {
				const raw = String(node.value || "");
				try {
					payload[name] = JSON.parse(raw);
				} catch {
					payload[name] = raw;
				}
				return;
			}

			payload[name] = String(node.value || "");
		});

		for (const [name, ids] of Object.entries(grouped)) {
			payload[`${name}_ids`] = ids;
		}

		return payload;
	}

	/**
	 * @returns {Promise<void>}
	 */
	async function submitStep() {
		if (!sessionId || !currentStep) return;
		const previousState =
			state && typeof state === "object"
				? /** @type {AM2ImportWizardState} */ (state)
				: null;
		const sid = encodeURIComponent(sessionId);
		const pid = encodeURIComponent(currentStep);
		const payload = collectPayload(currentStep);
		const r = await fetchJSON(`/import/ui/session/${sid}/step/${pid}`, {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: JSON.stringify(payload),
		});
		const errorPayload =
			typeof r.error === "object" && r.error && !Array.isArray(r.error)
				? /** @type {AM2JsonObject} */ (r.error)
				: null;
		if (errorPayload) {
			const messageValue = errorPayload["message"];
			const message =
				typeof messageValue === "string"
					? messageValue
					: "step submission failed";
			throw new Error(message);
		}
		state = r;
		sessionEffectiveModel =
			state && typeof state.effective_model === "object"
				? state.effective_model
				: null;
		if (
			promptHelpers &&
			promptHelpers.shouldAutoStartPhaseBoundary(previousState, state)
		) {
			await startProcessing();
		}
	}

	/**
	 * @returns {Promise<void>}
	 */
	async function startProcessing() {
		if (!sessionId) return;
		const sid = encodeURIComponent(sessionId);
		const r = await fetchJSON(`/import/ui/session/${sid}/start_processing`, {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: JSON.stringify({ confirm: true }),
		});
		const ids = r && Array.isArray(r.job_ids) ? r.job_ids.join(", ") : "";
		setText("status", `job_ids: ${ids}`);
	}

	/**
	 * @returns {Promise<void>}
	 */
	async function refresh() {
		if (!flow) await loadFlow();
		await loadState();

		setPre("state", state);
		clear(stepMount);

		if (!state) {
			setText("status", "No active session.");
			currentStep = null;
			submitButton.disabled = true;
			return;
		}

		currentStep = String(state.current_step_id || "");
		const step = findStep(currentStep);
		const title = step && step.title ? String(step.title) : currentStep;
		stepMount.appendChild(el("div", { class: "hint", text: `Step: ${title}` }));

		const status = String(state.status || "");
		if (status && status !== "in_progress") {
			stepMount.appendChild(
				el("div", { class: "hint", text: `Session status: ${status}` }),
			);
			submitButton.disabled = true;
			setText("status", `session_id: ${sessionId}`);
			return;
		}

		if (
			v3Renderer &&
			state &&
			v3Renderer.isV3State(state) &&
			v3Renderer.isPromptStep(step)
		) {
			const rendered = v3Renderer.renderCurrentStep({
				state,
				mount: stepMount,
				el,
				getLiveContext: () => ({
					session_id: String(sessionId || ""),
					current_step_id: String(currentStep || ""),
					status: String((state && state.status) || ""),
				}),
			});
			submitButton.disabled = !rendered;
			setText("status", `session_id: ${sessionId}`);
			return;
		}

		const fields = step && Array.isArray(step.fields) ? step.fields : [];
		/** @type {Record<string, boolean>} */
		const supported = {
			toggle: true,
			confirm: true,
			number: true,
			select: true,
			table_edit: true,
			text: true,
			multi_select_indexed: true,
		};

		for (const fld of fields) {
			const ftype = fieldType(fld);
			if (!supported[ftype]) {
				renderUnsupported(ftype, fld);
			}
			stepMount.appendChild(renderField(fld, currentStep));
		}

		submitButton.disabled = fields.length === 0;
		setText("status", `session_id: ${sessionId}`);
	}

	/**
	 * @param {AM2ImportStartConflict | null} conflict
	 * @returns {void}
	 */
	function setPendingStartConflict(conflict) {
		pendingStartConflict = conflict;
		const hasPending = !!pendingStartConflict;
		if (ui.resumeExisting)
			ui.resumeExisting.classList.toggle("is-hidden", !hasPending);
		if (ui.startNew) ui.startNew.classList.toggle("is-hidden", !hasPending);
		if (ui.cancelPendingStart)
			ui.cancelPendingStart.classList.toggle("is-hidden", !hasPending);
	}

	/**
	 * @param {unknown} err
	 * @returns {AM2ImportStartConflict | null}
	 */
	function readStartConflict(err) {
		const fetchErr = /** @type {AM2FetchError | null} */ (
			err instanceof Error ? err : null
		);
		const data =
			fetchErr &&
			fetchErr.data &&
			typeof fetchErr.data === "object" &&
			!Array.isArray(fetchErr.data)
				? /** @type {AM2JsonObject} */ (fetchErr.data)
				: null;
		const errorValue = data ? data["error"] : null;
		const error =
			errorValue && typeof errorValue === "object" && !Array.isArray(errorValue)
				? /** @type {AM2JsonObject} */ (errorValue)
				: null;
		if (!error || String(error["code"] || "") !== "SESSION_START_CONFLICT")
			return null;
		const detailsValue = error["details"];
		const details = Array.isArray(detailsValue) ? detailsValue : [];
		const firstDetail = details.length > 0 ? details[0] : null;
		const metaValue =
			firstDetail &&
			typeof firstDetail === "object" &&
			!Array.isArray(firstDetail)
				? firstDetail["meta"]
				: null;
		const meta =
			metaValue && typeof metaValue === "object" && !Array.isArray(metaValue)
				? /** @type {AM2JsonObject} */ (metaValue)
				: null;
		if (!meta) return null;
		return {
			session_id: String(meta.session_id || ""),
			root: String(meta.root || rootInput.value || ""),
			path: String(meta.relative_path || pathInput.value || ""),
			mode: String(meta.mode || modeSelect.value || ""),
		};
	}

	/**
	 * @param {string} [intent]
	 * @returns {Promise<void>}
	 */
	async function startSession(intent) {
		const selectedMode = String(modeSelect.value || "").trim();
		if (!selectedMode) throw new Error("Mode must be explicitly selected.");
		/** @type {AM2ImportSessionStartRequest} */
		const body = {
			root: String(rootInput.value || ""),
			path: String(pathInput.value || ""),
			mode: selectedMode,
		};
		if (typeof intent === "string" && intent) body.intent = intent;
		try {
			const r = await fetchJSON("/import/ui/session/start", {
				method: "POST",
				headers: { "content-type": "application/json" },
				body: JSON.stringify(body),
			});
			sessionId = r && typeof r.session_id === "string" ? r.session_id : null;
			if (!sessionId) throw new Error("missing session_id");
			setPendingStartConflict(null);
			return;
		} catch (e) {
			const conflict = readStartConflict(e);
			if (!conflict) throw e;
			sessionId = null;
			setPendingStartConflict(conflict);
			const conflictMsg =
				`Existing session detected: ${conflict.session_id}. ` +
				"Choose Resume existing, Start new, or Cancel.";
			setText("status", conflictMsg);
		}
	}

	startButton.addEventListener("click", async () => {
		try {
			await startSession();
			if (sessionId) await refresh();
		} catch (e) {
			setText("status", errorMessage(e));
		}
	});

	if (ui.resumeExisting) {
		ui.resumeExisting.addEventListener("click", async () => {
			try {
				await startSession("resume");
				await refresh();
			} catch (e) {
				setText("status", errorMessage(e));
			}
		});
	}

	if (ui.startNew) {
		ui.startNew.addEventListener("click", async () => {
			try {
				await startSession("new");
				await refresh();
			} catch (e) {
				setText("status", errorMessage(e));
			}
		});
	}

	if (ui.cancelPendingStart) {
		ui.cancelPendingStart.addEventListener("click", () => {
			setPendingStartConflict(null);
			setText("status", "Start canceled.");
		});
	}

	reloadButton.addEventListener("click", async () => {
		try {
			await refresh();
		} catch (e) {
			setText("status", errorMessage(e));
		}
	});

	submitButton.addEventListener("click", async () => {
		try {
			await submitStep();
			await refresh();
		} catch (e) {
			setText("status", errorMessage(e));
		}
	});

	refresh().catch((e) => setText("status", errorMessage(e)));
})();
