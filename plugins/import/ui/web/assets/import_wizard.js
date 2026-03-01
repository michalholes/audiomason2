(function () {
	"use strict";

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
					: text || r.status + " " + r.statusText;
			const err = new Error(msg);
			err.status = r.status;
			err.data = data;
			throw err;
		}
		return data;
	}

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

	function clear(node) {
		while (node.firstChild) node.removeChild(node.firstChild);
	}

	function setText(id, text) {
		const n = document.getElementById(id);
		if (n) n.textContent = String(text || "");
	}

	function setPre(id, obj) {
		const n = document.getElementById(id);
		if (!n) return;
		n.textContent = obj ? JSON.stringify(obj, null, 2) : "";
	}

	function fieldName(fld) {
		return fld && typeof fld.name === "string" ? fld.name : "";
	}

	function fieldType(fld) {
		return fld && typeof fld.type === "string" ? fld.type : "text";
	}

	function renderUnsupported(ftype, fld) {
		const meta =
			fld && typeof fld === "object" ? JSON.stringify(fld, null, 2) : "";
		const msg =
			"Unsupported field type: " + String(ftype || "") + "\n\n" + meta;
		setText("stepError", msg);
	}

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

	function normalizeItems(fld) {
		const items = fld && Array.isArray(fld.items) ? fld.items : null;
		if (items) return items;
		const opts = fld && Array.isArray(fld.options) ? fld.options : null;
		return opts || [];
	}

	function itemId(it) {
		if (it && typeof it === "object") {
			if (typeof it.item_id === "string") return it.item_id;
			if (typeof it.value === "string") return it.value;
		}
		return String(it || "");
	}

	function itemLabel(it) {
		if (it && typeof it === "object") {
			if (typeof it.label === "string") return it.label;
			if (typeof it.display_label === "string") return it.display_label;
			if (typeof it.value === "string") return it.value;
			if (typeof it.item_id === "string") return it.item_id;
		}
		return String(it || "");
	}

	const ui = {
		root: document.getElementById("root"),
		path: document.getElementById("path"),
		mode: document.getElementById("mode"),
		start: document.getElementById("start"),
		reload: document.getElementById("reload"),
		submit: document.getElementById("submit"),
		startProcessing: document.getElementById("startProcessing"),
		step: document.getElementById("step"),
	};

	function initTabs() {
		const wrap = document.getElementById("tabs");
		if (!wrap) return;
		const btns = Array.from(wrap.querySelectorAll(".tabBtn"));
		const panels = Array.from(document.querySelectorAll(".tabPanel"));

		let flowAutoLoaded = false;

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

	let sessionId = null;
	let flow = null;
	let state = null;
	let sessionEffectiveModel = null;
	let currentStep = null;

	initTabs();

	async function loadFlow() {
		flow = await fetchJSON("/import/ui/flow");
	}

	async function loadState() {
		if (!sessionId) {
			state = null;
			return;
		}
		const sid = encodeURIComponent(sessionId);
		state = await fetchJSON("/import/ui/session/" + sid + "/state");
		sessionEffectiveModel =
			state && typeof state.effective_model === "object"
				? state.effective_model
				: null;
	}

	function _resolvedSteps() {
		const sSteps =
			sessionEffectiveModel && Array.isArray(sessionEffectiveModel.steps)
				? sessionEffectiveModel.steps
				: null;
		if (sSteps) return sSteps;
		return flow && Array.isArray(flow.steps) ? flow.steps : [];
	}

	function _findSessionStep(stepId) {
		const steps =
			sessionEffectiveModel && Array.isArray(sessionEffectiveModel.steps)
				? sessionEffectiveModel.steps
				: [];
		return steps.find((s) => s && s.step_id === stepId) || null;
	}

	function _sessionFieldItems(stepId, field) {
		const step = _findSessionStep(stepId);
		const fields = step && Array.isArray(step.fields) ? step.fields : [];
		const match = fields.find((f) => f && f.name === field) || null;
		const items = match && Array.isArray(match.items) ? match.items : null;
		return items || [];
	}

	function findStep(stepId) {
		const steps = _resolvedSteps();
		return steps.find((s) => s && s.step_id === stepId) || null;
	}

	function renderField(fld, stepId) {
		const name = fieldName(fld);
		const ftype = fieldType(fld);
		const box = el("div", { class: "field" });
		box.appendChild(el("div", { class: "fieldName", text: name }));

		const cur = readAnswer(state, name);

		if (ftype === "toggle" || ftype === "confirm") {
			const row = el("div", { class: "choiceItem" });
			const inp = el("input", { type: "checkbox" });
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
			const inp = el("input", { type: "number" });
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
			const sel = el("select");
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
			const ta = el("textarea", { rows: "10" });
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
				const cb = el("input", { type: "checkbox" });
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
					text: "Selection is sent as " + name + "_ids",
				}),
			);
			return box;
		}

		if (ftype === "text") {
			const inp = el("input");
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

	function collectPayload(stepId) {
		setText("stepError", "");
		const payload = {};

		const nodes = ui.step
			? Array.from(ui.step.querySelectorAll("input,select,textarea"))
			: [];
		const grouped = {};

		nodes.forEach((n) => {
			if (n.dataset.stepId !== stepId) return;
			const ftype = n.dataset.ftype || "";
			const name = n.dataset.field || "";
			if (!name) return;

			if (ftype === "multi_select_indexed") {
				if (!grouped[name]) grouped[name] = [];
				if (n.getAttribute("type") === "checkbox" && n.checked) {
					grouped[name].push(String(n.dataset.itemId || ""));
				}
				return;
			}

			if (
				n.tagName.toLowerCase() === "input" &&
				n.getAttribute("type") === "checkbox"
			) {
				payload[name] = !!n.checked;
				return;
			}

			if (
				n.tagName.toLowerCase() === "input" &&
				n.getAttribute("type") === "number"
			) {
				if (n.value === "") payload[name] = null;
				else payload[name] = Number(n.value);
				return;
			}

			if (n.tagName.toLowerCase() === "textarea") {
				const raw = String(n.value || "");
				try {
					payload[name] = JSON.parse(raw);
				} catch {
					payload[name] = raw;
				}
				return;
			}

			payload[name] = String(n.value || "");
		});

		for (const [name, ids] of Object.entries(grouped)) {
			payload[name + "_ids"] = ids;
		}

		return payload;
	}

	async function submitStep() {
		if (!sessionId || !currentStep) return;
		const sid = encodeURIComponent(sessionId);
		const pid = encodeURIComponent(currentStep);
		const payload = collectPayload(currentStep);
		const r = await fetchJSON("/import/ui/session/" + sid + "/step/" + pid, {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: JSON.stringify(payload),
		});
		if (r && typeof r === "object" && r.error) {
			throw new Error(String(r.error.message || "step submission failed"));
		}
		state = r;
		sessionEffectiveModel =
			state && typeof state.effective_model === "object"
				? state.effective_model
				: null;
	}

	async function startProcessing() {
		if (!sessionId) return;
		const sid = encodeURIComponent(sessionId);
		const r = await fetchJSON(
			"/import/ui/session/" + sid + "/start_processing",
			{
				method: "POST",
				headers: { "content-type": "application/json" },
				body: "{}",
			},
		);
		const ids = r && Array.isArray(r.job_ids) ? r.job_ids.join(", ") : "";
		setText("status", "job_ids: " + ids);
	}

	async function refresh() {
		if (!flow) await loadFlow();
		await loadState();

		setPre("state", state);
		clear(ui.step);

		if (!state) {
			setText("status", "No active session.");
			currentStep = null;
			return;
		}

		currentStep = String(state.current_step_id || "");
		const step = findStep(currentStep);
		const title = step && step.title ? String(step.title) : currentStep;
		ui.step.appendChild(el("div", { class: "hint", text: "Step: " + title }));

		const fields = step && Array.isArray(step.fields) ? step.fields : [];
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
			ui.step.appendChild(renderField(fld, currentStep));
		}

		setText("status", "session_id: " + sessionId);
	}

	async function startSession() {
		const selectedMode = String(ui.mode.value || "").trim();
		if (!selectedMode) throw new Error("Mode must be explicitly selected.");
		const body = {
			root: String(ui.root.value || ""),
			path: String(ui.path.value || ""),
			mode: selectedMode,
		};
		const r = await fetchJSON("/import/ui/session/start", {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: JSON.stringify(body),
		});
		sessionId = r && typeof r.session_id === "string" ? r.session_id : null;
		if (!sessionId) throw new Error("missing session_id");
	}

	ui.start.addEventListener("click", async () => {
		try {
			await startSession();
			await refresh();
		} catch (e) {
			setText("status", String(e && e.message ? e.message : e));
		}
	});

	ui.reload.addEventListener("click", async () => {
		try {
			await refresh();
		} catch (e) {
			setText("status", String(e && e.message ? e.message : e));
		}
	});

	ui.submit.addEventListener("click", async () => {
		try {
			await submitStep();
			await refresh();
		} catch (e) {
			setText("status", String(e && e.message ? e.message : e));
		}
	});

	ui.startProcessing.addEventListener("click", async () => {
		try {
			await startProcessing();
		} catch (e) {
			setText("status", String(e && e.message ? e.message : e));
		}
	});

	refresh().catch((e) =>
		setText("status", String(e && e.message ? e.message : e)),
	);
})();
