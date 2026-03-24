(function () {
	"use strict";

	/** @typedef {{
	 * 	reload?: () => Promise<boolean | void>,
	 * 	reloadAll?: () => Promise<boolean | void>,
	 * 	reset?: () => Promise<boolean | void>,
	 * 	resetDefinition?: () => Promise<boolean | void>,
	 * 	save?: () => Promise<boolean | void>,
	 * 	saveDraft?: () => Promise<boolean | void>,
	 * 	validate?: () => Promise<boolean | void>,
	 * 	validateDraft?: () => Promise<boolean | void>,
	 * }} AM2FlowAllWizardAdapter
	 */
	/** @type {Window} */
	const W = window;

	function $(id) {
		return document.getElementById(id);
	}

	const ui = {
		status: $("flowAllStatus"),
		reloadAll: $("flowReloadAll"),
		validateAll: $("flowValidateAll"),
		saveAll: /** @type {HTMLButtonElement|null} */ ($("flowSaveAll")),
		resetAll: $("flowResetAll"),
	};

	function setStatus(msg, kind) {
		if (!ui.status) return;
		ui.status.textContent = String(msg || "");
		ui.status.classList.toggle("is-ok", kind === "ok");
		ui.status.classList.toggle("is-bad", kind === "bad");
	}

	if (!W.AM2FlowEditorState && W.FlowEditorState) {
		W.AM2FlowEditorState = new W.FlowEditorState();
	}

	W.AM2FlowEditor = W.AM2FlowEditor || {};
	/** @type {AM2FlowEditorGlobalApi & { __allValid?: boolean }} */
	const AM2 = W.AM2FlowEditor;
	AM2.__allValid = false;

	function setAllValid(ok) {
		AM2.__allValid = ok === true;
		setSaveEnabled();
	}

	function setSaveEnabled() {
		if (!ui.saveAll) return;
		ui.saveAll.disabled = AM2.__allValid !== true;
		ui.saveAll.classList.toggle("is-disabled", AM2.__allValid !== true);
	}

	function invalidateValidation() {
		setAllValid(false);
	}

	function stepModalOpen() {
		const modal = W.AM2FlowStepModalState;
		return !!(modal && modal.isOpen && modal.isOpen() === true);
	}

	function blockIfStepModalOpen(actionName) {
		if (stepModalOpen()) {
			setStatus(
				"Close the open step modal before running " + actionName + ".",
				"bad",
			);
			return true;
		}
		return false;
	}
	function getAdapters() {
		/** @type {AM2FlowEditorConfigApi | null} */
		const cfg = AM2.config || W.AM2FlowConfigEditor || null;
		/** @type {AM2FlowAllWizardAdapter | null} */
		const wiz = AM2.wizard || W.AM2WizardDefinitionEditor || null;
		return { cfg: cfg, wiz: wiz };
	}

	function getWizardFailureDetail() {
		const FE = W.AM2FlowEditorState;
		const snap = FE && FE.getSnapshot ? FE.getSnapshot() : null;
		const wd = snap && snap.wizardDraft ? snap.wizardDraft : null;
		/** @type {{ validation?: { server?: unknown[], local?: unknown[] } } | null} */
		const uiState =
			wd &&
			typeof wd === "object" &&
			!Array.isArray(wd) &&
			wd._am2_ui &&
			typeof wd._am2_ui === "object" &&
			!Array.isArray(wd._am2_ui)
				? wd._am2_ui
				: null;
		const validation =
			uiState && uiState.validation && typeof uiState.validation === "object"
				? uiState.validation
				: null;
		const server =
			validation && Array.isArray(validation.server) ? validation.server : [];
		const local =
			validation && Array.isArray(validation.local) ? validation.local : [];
		const msg = String(server[0] || local[0] || "").trim();
		return msg ? msg : "";
	}

	async function doReloadAll() {
		if (blockIfStepModalOpen("Reload All")) return;
		invalidateValidation();
		setStatus("", "");
		const { cfg, wiz } = getAdapters();
		if (wiz && wiz.reload) await wiz.reload();
		else if (wiz && wiz.reloadAll) await wiz.reloadAll();
		if (cfg && cfg.reload) await cfg.reload();
	}

	async function doResetAll() {
		if (blockIfStepModalOpen("Reset All")) return;
		invalidateValidation();
		setStatus("Resetting...", "");
		const { cfg, wiz } = getAdapters();
		let okW = true;
		let okC = true;
		if (wiz && wiz.reset) okW = (await wiz.reset()) !== false;
		else if (wiz && wiz.resetDefinition)
			okW = (await wiz.resetDefinition()) !== false;
		if (cfg && cfg.reset) okC = (await cfg.reset()) !== false;
		setStatus(
			okW && okC ? "Reset All: OK" : "Reset All: FAILED",
			okW && okC ? "ok" : "bad",
		);
	}

	async function doValidateAll() {
		if (blockIfStepModalOpen("Validate All")) return false;
		invalidateValidation();
		setStatus("Validating...", "");
		const { cfg, wiz } = getAdapters();

		// Validate Draft artifacts on the server by saving Draft after validation.
		const okW =
			wiz && wiz.save
				? await wiz.save()
				: wiz && wiz.saveDraft
					? await wiz.saveDraft()
					: wiz && wiz.validate
						? await wiz.validate()
						: wiz && wiz.validateDraft
							? await wiz.validateDraft()
							: false;

		const okC =
			cfg && cfg.save
				? await cfg.save()
				: cfg && cfg.validate
					? await cfg.validate()
					: false;

		const ok = !!(okW && okC);
		setAllValid(ok);
		if (ok) {
			setStatus("Validate All: OK", "ok");
			return true;
		}

		const failed = [];
		if (!okW) failed.push("WizardDefinition");
		if (!okC) failed.push("FlowConfig");
		let detail = "";
		if (!okW) detail = getWizardFailureDetail();
		if (detail) {
			setStatus(
				`Validate All: FAILED (${failed.join(", ")}): ${detail}`,
				"bad",
			);
			W.alert(detail);
		} else {
			setStatus(`Validate All: FAILED (${failed.join(", ")})`, "bad");
		}
		return false;
	}

	async function doSaveAll() {
		if (blockIfStepModalOpen("Save All")) return;
		if (AM2.__allValid !== true) {
			setStatus("Save blocked: run Validate All first.", "bad");
			setSaveEnabled();
			return;
		}
		setStatus("Saving...", "");

		const H = W.AM2EditorHTTP;
		if (!H || !H.requestJSON) {
			setStatus("Save failed: missing HTTP client.", "bad");
			return;
		}

		const ok1 = await H.requestJSON("/import/ui/config/activate", {
			method: "POST",
		});
		if (!ok1.ok) {
			setStatus("Save All: FAILED", "bad");
			return;
		}

		const ok2 = await H.requestJSON("/import/ui/wizard-definition/activate", {
			method: "POST",
		});
		if (!ok2.ok) {
			setStatus("Save All: FAILED", "bad");
			return;
		}

		const FE2 = W.AM2FlowEditorState;
		if (FE2 && typeof FE2.clearDirty === "function") {
			FE2.clearDirty();
		} else if (FE2) {
			FE2.draftDirty = false;
		}

		await doReloadAll();
		setAllValid(false);
		setStatus("Save All: OK", "ok");
	}

	window.AM2UI = window.AM2UI || {};
	window.AM2UI.doReloadAll = doReloadAll;

	const FE = W.AM2FlowEditorState;
	if (FE && FE.on) {
		FE.on("wizard_changed", invalidateValidation);
		FE.on("config_changed", invalidateValidation);
		FE.on("selection_changed", invalidateValidation);
		FE.on("validation_changed", invalidateValidation);
	}

	setSaveEnabled();
	ui.reloadAll && ui.reloadAll.addEventListener("click", doReloadAll);
	ui.validateAll && ui.validateAll.addEventListener("click", doValidateAll);
	ui.saveAll && ui.saveAll.addEventListener("click", doSaveAll);
	ui.resetAll && ui.resetAll.addEventListener("click", doResetAll);
})();
