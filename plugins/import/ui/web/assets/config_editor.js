(() => {
	const H = window["AM2EditorHTTP"];
	if (!H) return;

	function $(id) {
		return document.getElementById(id);
	}

	const ui = {
		ta: /** @type {HTMLTextAreaElement|null} */ ($("cfgJson")),
		err: $("cfgError"),
		history: $("cfgHistory"),
		reload: $("cfgReload"),
		validate: $("cfgValidate"),
		save: $("cfgSave"),
		reset: $("cfgReset"),
		activate: $("cfgActivate"),

		stepPanel: $("flowStepPanel"),
		stepHeader: $("flowStepHeader"),
		stepBehavior: $("flowStepBehavior"),
		stepInput: $("flowStepInput"),
		stepOutput: $("flowStepOutput"),
		stepSideEffects: $("flowStepSideEffects"),
		stepForm: $("flowStepForm"),
		stepApply: $("flowStepApply"),
		stepError: $("flowStepError"),
		clearStep: $("flowClearStep"),
		stepValidate: $("flowStepValidate"),
		stepSave: $("flowStepSave"),
		stepActivate: $("flowStepActivate"),
		stepApplyBtn: $("flowStepApplyNow"),
		stepDiff: $("flowStepDiff"),
		stepShowHistory: $("flowStepShowHistory"),
		stepHistory: $("flowStepHistory"),
	};

	if (!ui.ta) return;

	const unifiedMode = !!ui.stepPanel;

	let baselineConfig = null;

	function deepClone(x) {
		return x === undefined ? undefined : JSON.parse(JSON.stringify(x));
	}

	function snapshot() {
		const FE = window["AM2FlowEditorState"];
		return FE && FE.getSnapshot ? FE.getSnapshot() : null;
	}

	const stepCache = {};

	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	function historyRow(item) {
		const row = document.createElement("div");
		row.className = "historyItem";
		const meta = document.createElement("div");
		meta.className = "historyMeta";
		const id = document.createElement("div");
		id.textContent = String(item.id || "");
		const ts = document.createElement("div");
		ts.textContent = String(item.timestamp || "");
		meta.appendChild(id);
		meta.appendChild(ts);
		const btn = document.createElement("button");
		btn.className = "btn";
		btn.textContent = "Rollback";
		btn.addEventListener("click", async () => {
			await rollback(String(item.id || ""));
		});
		row.appendChild(meta);
		row.appendChild(btn);
		return row;
	}

	async function loadHistory() {
		const out = await H.requestJSON("/import/ui/config/history");
		if (!out.ok) {
			H.renderError(ui.err, out.data);
			return;
		}
		clear(ui.history);
		const items = out.data && out.data.items ? out.data.items : [];
		(Array.isArray(items) ? items : []).forEach((it) => {
			ui.history.appendChild(historyRow(it || {}));
		});
	}

	async function reload() {
		H.renderError(ui.err, null);
		const out = await H.requestJSON("/import/ui/config");
		if (!out.ok) {
			H.renderError(ui.err, out.data);
			return false;
		}
		const cfg = out.data && out.data.config ? out.data.config : {};
		baselineConfig = deepClone(cfg);
		ui.ta.value = H.pretty(cfg);
		const FE = window["AM2FlowEditorState"];
		if (FE && FE.loadAll && FE.getSnapshot) {
			const snap = FE.getSnapshot();
			FE.loadAll({ wizardDefinition: snap.wizardDraft, flowConfig: cfg });
		}
		await loadHistory();
		if (unifiedMode) renderSelectedStep();
		return true;
	}

	async function validateOnly() {
		H.renderError(ui.err, null);
		let payloadCfg = /** @type {any} */ ({});
		if (unifiedMode) {
			const s = snapshot();
			payloadCfg = (s && s.configDraft) || {};
		} else {
			try {
				payloadCfg = JSON.parse(ui.ta.value || "{}");
			} catch (e) {
				ui.err.textContent = String(e || "parse error");
				return false;
			}
		}
		if (payloadCfg && typeof payloadCfg === "object") {
			delete (/** @type {any} */ (payloadCfg).ui);
		}
		const out = await H.requestJSON("/import/ui/config/validate", {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: JSON.stringify({ config: payloadCfg }),
		});
		if (!out.ok) {
			H.renderError(ui.err, out.data);
			return false;
		}
		baselineConfig = deepClone(out.data.config || {});
		ui.ta.value = H.pretty(out.data.config || {});

		const FE = window["AM2FlowEditorState"];
		if (FE && FE.markValidated && FE.getSnapshot) {
			const snap = FE.getSnapshot();
			FE.markValidated({
				canonicalWizardDefinition: snap.wizardDraft,
				canonicalFlowConfig: out.data.config || {},
				validationEnvelope: { ok: true },
			});
		}

		if (unifiedMode) renderSelectedStep();
		return true;
	}

	async function save() {
		H.renderError(ui.err, null);
		if (unifiedMode) {
			const ok = await validateOnly();
			if (!ok) return false;
		}
		let payloadCfg = /** @type {any} */ ({});
		if (unifiedMode) {
			const s = snapshot();
			payloadCfg = (s && s.configDraft) || {};
		} else {
			try {
				payloadCfg = JSON.parse(ui.ta.value || "{}");
			} catch (e) {
				ui.err.textContent = String(e || "parse error");
				return false;
			}
		}
		if (payloadCfg && typeof payloadCfg === "object") {
			delete (/** @type {any} */ (payloadCfg).ui);
		}
		const out = await H.requestJSON("/import/ui/config", {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: JSON.stringify({ config: payloadCfg }),
		});
		if (!out.ok) {
			H.renderError(ui.err, out.data);
			return false;
		}
		baselineConfig = deepClone(out.data.config || {});
		ui.ta.value = H.pretty(out.data.config || {});

		const FE = window["AM2FlowEditorState"];
		if (FE && FE.loadAll && FE.getSnapshot) {
			const snap = FE.getSnapshot();
			FE.loadAll(
				{
					wizardDefinition: snap.wizardDraft,
					flowConfig: out.data.config || {},
				},
				{ preserveValidation: true },
			);
		}

		await loadHistory();
		if (unifiedMode) renderSelectedStep();
		return true;
	}

	async function reset() {
		H.renderError(ui.err, null);
		const out = await H.requestJSON("/import/ui/config/reset", {
			method: "POST",
		});
		if (!out.ok) {
			H.renderError(ui.err, out.data);
			return false;
		}
		baselineConfig = deepClone(out.data.config || {});
		ui.ta.value = H.pretty(out.data.config || {});

		const FE = window["AM2FlowEditorState"];
		if (FE && FE.loadAll && FE.getSnapshot) {
			const snap = FE.getSnapshot();
			FE.loadAll({
				wizardDefinition: snap.wizardDraft,
				flowConfig: out.data.config || {},
			});
		}

		await loadHistory();
		if (unifiedMode) renderSelectedStep();
		return true;
	}

	async function activate() {
		H.renderError(ui.err, null);
		// Ensure a draft exists on disk before activation.
		const ok = await save();
		if (!ok) return false;
		const out = await H.requestJSON("/import/ui/config/activate", {
			method: "POST",
		});
		if (!out.ok) {
			H.renderError(ui.err, out.data);
			return false;
		}
		await reload();
		return true;
	}

	async function rollback(id) {
		H.renderError(ui.err, null);
		const out = await H.requestJSON("/import/ui/config/rollback", {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: JSON.stringify({ id: id }),
		});
		if (!out.ok) {
			H.renderError(ui.err, out.data);
			return;
		}
		baselineConfig = deepClone(out.data.config || {});
		ui.ta.value = H.pretty(out.data.config || {});

		const FE = window["AM2FlowEditorState"];
		if (FE && FE.loadAll && FE.getSnapshot) {
			const snap = FE.getSnapshot();
			FE.loadAll({
				wizardDefinition: snap.wizardDraft,
				flowConfig: out.data.config || {},
			});
		}

		await loadHistory();
		if (unifiedMode) renderSelectedStep();
	}

	function stableFields(schema) {
		const root = schema && typeof schema === "object" ? schema : {};
		const fields = Array.isArray(root.fields) ? root.fields : [];
		return fields.filter((f) => f && typeof f.key === "string" && f.key);
	}

	function safeDefaultsRoot(cfg) {
		if (!cfg || typeof cfg !== "object") return {};
		if (!cfg.defaults || typeof cfg.defaults !== "object") cfg.defaults = {};
		return cfg.defaults;
	}

	function currentConfig() {
		const s = snapshot();
		return deepClone((s && s.configDraft) || {});
	}

	function emitChanged() {
		try {
			window.dispatchEvent(new CustomEvent("am2:cfg:changed", { detail: {} }));
		} catch (e) {}
	}

	function setStepValue(stepId, key, value) {
		const FE = window["AM2FlowEditorState"];
		if (FE && FE.mutateConfig) {
			FE.mutateConfig((cfg) => {
				const defaults = safeDefaultsRoot(cfg);
				if (!defaults[stepId] || typeof defaults[stepId] !== "object")
					defaults[stepId] = {};
				defaults[stepId][key] = value;
			});
		}

		if (!unifiedMode) {
			ui.ta.value = H.pretty(currentConfig());
			emitChanged();
		}
		updateApplyStatus(stepId);
	}

	function unsetStepValue(stepId, key) {
		const FE = window["AM2FlowEditorState"];
		if (FE && FE.mutateConfig) {
			FE.mutateConfig((cfg) => {
				const defaults = safeDefaultsRoot(cfg);
				const obj = defaults[stepId];
				if (!obj || typeof obj !== "object") return;
				if (Object.hasOwn(obj, key)) {
					delete obj[key];
				}
				if (!Object.keys(obj).length) {
					delete defaults[stepId];
				}
			});
		}

		if (!unifiedMode) {
			ui.ta.value = H.pretty(currentConfig());
			emitChanged();
		}
		updateApplyStatus(stepId);
	}

	function clearStepDefaults(stepId) {
		if (!stepId) return;
		const FE = window["AM2FlowEditorState"];
		if (FE && FE.mutateConfig) {
			FE.mutateConfig((cfg) => {
				const defaults = safeDefaultsRoot(cfg);
				if (defaults && defaults[stepId]) delete defaults[stepId];
			});
		}
		if (!unifiedMode) {
			ui.ta.value = H.pretty(currentConfig());
			emitChanged();
		}
		renderSelectedStep();
	}

	function updateApplyStatus(stepId) {
		if (!ui.stepApply) return;
		if (!stepId) {
			ui.stepApply.textContent = "";
			return;
		}
		const keys = getAppliedKeys(stepId);
		ui.stepApply.textContent = keys.length
			? "Applied keys: " + keys.join(", ")
			: "No settings applied";
	}

	function getAppliedKeys(stepId) {
		const cfg = currentConfig();
		const defaults = safeDefaultsRoot(cfg);
		const o = defaults[stepId];
		if (!o || typeof o !== "object") return [];
		return Object.keys(o).sort();
	}

	function _shortVal(v) {
		if (v === null) return "null";
		if (v === undefined) return "(none)";
		if (typeof v === "string")
			return v.length > 64 ? v.slice(0, 61) + "..." : v;
		if (typeof v === "number" || typeof v === "boolean") return String(v);
		try {
			const s = JSON.stringify(v);
			return s && s.length > 64 ? s.slice(0, 61) + "..." : s;
		} catch (e) {
			return "(unprintable)";
		}
	}

	function _validateField(field, value) {
		const key = String(field && field.key ? field.key : "");
		const typ = field && field.type ? String(field.type) : "string";
		const required = !!(field && field.required);
		if (!key) return "";
		if (required) {
			if (value === undefined) return "Required";
			if (typ === "string" && String(value || "") === "") return "Required";
		}
		if (value === undefined) return "";
		if (typ === "number" || typ === "int") {
			if (typeof value !== "number" || Number.isNaN(value))
				return "Must be a number";
			if (typeof field.min === "number" && value < field.min)
				return "Min " + String(field.min);
			if (typeof field.max === "number" && value > field.max)
				return "Max " + String(field.max);
		}
		if (typ === "bool") {
			if (typeof value !== "boolean") return "Must be true/false";
		}
		const choices = Array.isArray(field.options)
			? field.options
			: Array.isArray(field.choices)
				? field.choices
				: null;
		if (choices && choices.length) {
			const s = String(value);
			if (choices.map((x) => String(x)).indexOf(s) === -1)
				return "Invalid option";
		}
		if (typ === "json") {
			if (typeof value !== "object" || value === null)
				return "Must be JSON object";
		}
		return "";
	}

	function inputForField(field, stepId) {
		const wrap = document.createElement("div");
		wrap.className = "flowField";

		const labelRow = document.createElement("div");
		labelRow.className = "flowFieldLabelRow";

		const label = document.createElement("label");
		label.className = "flowFieldLabel";
		label.textContent = String(field.key || "");

		const btnReset = document.createElement("button");
		btnReset.type = "button";
		btnReset.className = "btn btnSmall";
		btnReset.textContent = "Reset";
		btnReset.addEventListener("click", () => {
			unsetStepValue(stepId, String(field.key || ""));
			renderSelectedStep();
		});

		labelRow.appendChild(label);
		labelRow.appendChild(btnReset);

		const meta = document.createElement("div");
		meta.className = "flowFieldMeta";
		const req = field.required ? "required" : "optional";
		const typ = field.type ? String(field.type) : "string";

		const cfg = currentConfig();
		const defaults = safeDefaultsRoot(cfg);
		const obj = defaults[stepId];
		const hasOverride =
			obj && typeof obj === "object" && Object.hasOwn(obj, field.key);
		const cur = hasOverride ? obj[field.key] : undefined;
		const defVal = Object.hasOwn(field, "default") ? field.default : undefined;
		const effective = hasOverride ? cur : defVal;

		meta.textContent =
			req +
			" - " +
			typ +
			" | default: " +
			_shortVal(defVal) +
			" | effective: " +
			_shortVal(effective) +
			" | override: " +
			(hasOverride ? "yes" : "no");

		let inp = null;
		let rawJsonText = "";
		const err = document.createElement("div");
		err.className = "flowFieldError";

		const choices = Array.isArray(field.options)
			? field.options
			: Array.isArray(field.choices)
				? field.choices
				: null;

		function setErr(msg) {
			err.textContent = String(msg || "");
		}

		function applyValue(v) {
			const msg = _validateField(field, v);
			setErr(msg);
			if (!msg) {
				setStepValue(stepId, String(field.key || ""), v);
			}
		}

		if (choices && choices.length) {
			inp = document.createElement("select");
			inp.className = "flowFieldInput";
			choices.forEach((c) => {
				const opt = document.createElement("option");
				opt.value = String(c);
				opt.textContent = String(c);
				inp.appendChild(opt);
			});
			const v0 = hasOverride ? cur : defVal;
			inp.value = v0 === undefined ? "" : String(v0);
			inp.addEventListener("change", () => {
				applyValue(String(inp.value || ""));
			});
		} else if (typ === "bool") {
			inp = document.createElement("input");
			inp.className = "flowFieldInput";
			inp.type = "checkbox";
			inp.checked = typeof effective === "boolean" ? effective : !!effective;
			inp.addEventListener("change", () => {
				applyValue(!!inp.checked);
			});
		} else if (typ === "number" || typ === "int") {
			inp = document.createElement("input");
			inp.className = "flowFieldInput";
			inp.type = "number";
			if (typeof field.min === "number") inp.min = String(field.min);
			if (typeof field.max === "number") inp.max = String(field.max);
			if (typeof field.step === "number") inp.step = String(field.step);
			const v0 = typeof effective === "number" ? String(effective) : "";
			inp.value = v0;
			inp.addEventListener("input", () => {
				if (inp.value === "") {
					applyValue(undefined);
					return;
				}
				const n = Number(inp.value);
				if (!Number.isNaN(n)) applyValue(n);
			});
		} else if (typ === "json") {
			inp = document.createElement("textarea");
			inp.className = "flowFieldInput";
			inp.rows = 4;
			try {
				rawJsonText = JSON.stringify(
					effective === undefined ? {} : effective,
					null,
					2,
				);
			} catch (e) {
				rawJsonText = "{}";
			}
			inp.value = rawJsonText;
			inp.addEventListener("input", () => {
				try {
					const parsed = JSON.parse(String(inp.value || "{}"));
					applyValue(parsed);
				} catch (e) {
					setErr("Invalid JSON");
				}
			});
		} else if (field && (field.multiline || field.format === "textarea")) {
			inp = document.createElement("textarea");
			inp.className = "flowFieldInput";
			inp.rows = 3;
			inp.value = effective === undefined ? "" : String(effective);
			inp.addEventListener("input", () => {
				applyValue(String(inp.value || ""));
			});
		} else {
			inp = document.createElement("input");
			inp.className = "flowFieldInput";
			inp.type = "text";
			inp.value = effective === undefined ? "" : String(effective);
			inp.addEventListener("input", () => {
				applyValue(String(inp.value || ""));
			});
		}

		wrap.appendChild(labelRow);
		wrap.appendChild(meta);
		wrap.appendChild(inp);
		wrap.appendChild(err);
		setErr(_validateField(field, hasOverride ? cur : defVal));
		return wrap;
	}

	function clearNode(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	function setStepError(msg) {
		if (!ui.stepError) return;
		ui.stepError.textContent = String(msg || "");
	}

	async function fetchStepDetails(stepId) {
		const sid = String(stepId || "");
		if (!sid) return null;
		if (stepCache[sid]) return stepCache[sid];
		const out = await H.requestJSON(
			"/import/ui/steps/" + encodeURIComponent(sid),
		);
		if (!out.ok) {
			setStepError("Failed to load step details");
			return null;
		}
		const d = out.data && typeof out.data === "object" ? out.data : {};
		stepCache[sid] = d;
		return d;
	}

	function _objOrEmpty(x) {
		return x && typeof x === "object" ? x : {};
	}

	function renderStepDiff(stepId) {
		if (!ui.stepDiff) return;
		const base = _objOrEmpty(baselineConfig);
		const cur = currentConfig();
		const bDef = _objOrEmpty(_objOrEmpty(base).defaults);
		const cDef = _objOrEmpty(_objOrEmpty(cur).defaults);
		const b = _objOrEmpty(bDef[stepId]);
		const c = _objOrEmpty(cDef[stepId]);
		const bKeys = Object.keys(b).sort();
		const cKeys = Object.keys(c).sort();
		const added = cKeys.filter((k) => bKeys.indexOf(k) === -1);
		const removed = bKeys.filter((k) => cKeys.indexOf(k) === -1);
		const changed = cKeys.filter(
			(k) => bKeys.indexOf(k) !== -1 && String(b[k]) !== String(c[k]),
		);
		const parts = [];
		if (added.length) parts.push("added: " + added.join(", "));
		if (changed.length) parts.push("changed: " + changed.join(", "));
		if (removed.length) parts.push("removed: " + removed.join(", "));
		ui.stepDiff.textContent = parts.length
			? parts.join("\n")
			: "No draft changes for this step.";
	}

	async function loadStepHistory() {
		if (!ui.stepHistory) return;
		const out = await H.requestJSON("/import/ui/config/history");
		if (!out.ok) {
			ui.stepHistory.textContent = "Failed to load history";
			return;
		}
		clear(ui.stepHistory);
		const items = out.data && out.data.items ? out.data.items : [];
		(Array.isArray(items) ? items : []).slice(0, 20).forEach((it) => {
			ui.stepHistory.appendChild(historyRow(it || {}));
		});
	}

	async function renderSelectedStep() {
		if (!unifiedMode) return;
		const s = snapshot();
		const stepId = (s && s.selectedStepId) || null;

		if (!ui.stepHeader || !ui.stepBehavior || !ui.stepForm || !ui.stepApply)
			return;

		setStepError("");

		if (!stepId) {
			ui.stepHeader.textContent = "Step settings (FlowConfig draft)";
			ui.stepBehavior.textContent =
				"Edits modify the FlowConfig draft. Use Validate -> Save -> Activate to apply.";
			if (ui.stepInput) ui.stepInput.textContent = "";
			if (ui.stepOutput) ui.stepOutput.textContent = "";
			if (ui.stepSideEffects) ui.stepSideEffects.textContent = "";
			clearNode(ui.stepForm);
			ui.stepApply.textContent = "";
			return;
		}

		const det = await fetchStepDetails(stepId);
		const title =
			det && (det.displayName || det.title)
				? String(det.displayName || det.title)
				: "";
		const behavior =
			det && det.behavioralSummary ? String(det.behavioralSummary) : "";
		const inC = det && det.inputContract ? String(det.inputContract) : "";
		const outC = det && det.outputContract ? String(det.outputContract) : "";
		const sideFx =
			det && det.sideEffectsDescription
				? String(det.sideEffectsDescription)
				: "";
		const schema = det && det.settings_schema ? det.settings_schema : {};

		ui.stepHeader.textContent = title ? stepId + " - " + title : stepId;
		ui.stepBehavior.textContent =
			"Edits modify the FlowConfig draft. Use Validate -> Save -> Activate to apply.\n\n" +
			behavior;
		if (ui.stepInput) ui.stepInput.textContent = inC;
		if (ui.stepOutput) ui.stepOutput.textContent = outC;
		if (ui.stepSideEffects) ui.stepSideEffects.textContent = sideFx;

		clearNode(ui.stepForm);
		stableFields(schema).forEach((f) => {
			ui.stepForm.appendChild(inputForField(f, stepId));
		});

		if (ui.stepDiff) {
			renderStepDiff(stepId);
		}
		if (ui.stepHistory) {
			// Leave history empty until requested.
		}

		updateApplyStatus(stepId);
	}

	window.addEventListener("am2:wd:selected", async (e) => {
		await renderSelectedStep();
	});

	ui.clearStep &&
		ui.clearStep.addEventListener("click", () => {
			const s = snapshot();
			clearStepDefaults((s && s.selectedStepId) || null);
		});

	ui.stepValidate &&
		ui.stepValidate.addEventListener("click", () => {
			void validateOnly();
		});

	ui.stepSave &&
		ui.stepSave.addEventListener("click", () => {
			void save();
		});

	ui.stepActivate &&
		ui.stepActivate.addEventListener("click", () => {
			void activate();
		});

	async function applyAllForStep() {
		H.renderError(ui.err, null);
		const okV = await validateOnly();
		if (!okV) return false;
		const okS = await save();
		if (!okS) return false;
		const okA = await activate();
		return okA;
	}

	ui.stepApplyBtn &&
		ui.stepApplyBtn.addEventListener("click", () => {
			void applyAllForStep();
		});

	ui.stepShowHistory &&
		ui.stepShowHistory.addEventListener("click", () => {
			void loadStepHistory();
		});

	ui.reload && ui.reload.addEventListener("click", reload);
	ui.validate && ui.validate.addEventListener("click", validateOnly);
	ui.save && ui.save.addEventListener("click", save);
	ui.reset && ui.reset.addEventListener("click", reset);
	ui.activate && ui.activate.addEventListener("click", activate);

	async function renderNow() {
		await renderSelectedStep();
		return true;
	}

	window["AM2FlowConfigEditor"] = {
		reload: reload,
		validate: validateOnly,
		save: save,
		reset: reset,
		activate: activate,
		renderNow: renderNow,
		_debug_getDraft: () => currentConfig(),
	};

	window.AM2FlowEditor = window.AM2FlowEditor || {};
	window.AM2FlowEditor.config = {
		reload: reload,
		validate: validateOnly,
		save: save,
		reset: reset,
		activate: activate,
	};

	const FE = window["AM2FlowEditorState"];
	if (FE && FE.registerConfigRender) {
		FE.registerConfigRender(() => {
			if (unifiedMode) renderSelectedStep();
		});
	}

	reload();
})();
