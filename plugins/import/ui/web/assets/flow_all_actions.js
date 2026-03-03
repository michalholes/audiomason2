(function () {
	"use strict";

	function $(id) {
		return document.getElementById(id);
	}

	const ui = {
		status: $("flowAllStatus"),
		reloadAll: $("flowReloadAll"),
		validateAll: $("flowValidateAll"),
		saveAll: $("flowSaveAll"),
		resetAll: $("flowResetAll"),
	};

	function setStatus(msg, kind) {
		if (!ui.status) return;
		ui.status.textContent = String(msg || "");
		ui.status.classList.toggle("is-ok", kind === "ok");
		ui.status.classList.toggle("is-bad", kind === "bad");
	}

	if (!window.AM2FlowEditorState && window.FlowEditorState) {
		window.AM2FlowEditorState = new window.FlowEditorState();
	}

	window.AM2FlowEditor = window.AM2FlowEditor || {};
	const AM2 = window.AM2FlowEditor;
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

	function getAdapters() {
		const cfg = AM2.config || window.AM2FlowConfigEditor;
		const wiz = AM2.wizard || window.AM2WizardDefinitionEditor;
		return { cfg: cfg, wiz: wiz };
	}

	function getWizardFailureDetail() {
		const FE = window.AM2FlowEditorState;
		const snap = FE && FE.getSnapshot ? FE.getSnapshot() : null;
		const wd = snap && snap.wizardDraft ? snap.wizardDraft : null;
		const uiState = wd && wd._am2_ui ? wd._am2_ui : null;
		const v = uiState && uiState.validation ? uiState.validation : null;
		const server = v && Array.isArray(v.server) ? v.server : [];
		const local = v && Array.isArray(v.local) ? v.local : [];
		const msg = (server[0] || local[0] || "").trim();
		return msg ? msg : "";
	}

	async function doReloadAll() {
		invalidateValidation();
		setStatus("", "");
		const { cfg, wiz } = getAdapters();
		if (wiz && wiz.reload) await wiz.reload();
		else if (wiz && wiz.reloadAll) await wiz.reloadAll();
		if (cfg && cfg.reload) await cfg.reload();
	}

	async function doResetAll() {
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
			window.alert(detail);
		} else {
			setStatus(`Validate All: FAILED (${failed.join(", ")})`, "bad");
		}
		return false;
	}

	async function doSaveAll() {
		if (AM2.__allValid !== true) {
			setStatus("Save blocked: run Validate All first.", "bad");
			setSaveEnabled();
			return;
		}
		setStatus("Saving...", "");

		const H = window.AM2EditorHTTP;
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

		const FE2 = window.AM2FlowEditorState;
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

	const FE = window.AM2FlowEditorState;
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
