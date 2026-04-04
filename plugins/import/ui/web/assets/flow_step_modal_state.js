/// <reference path="../../../../../types/am2-import-ui-globals.d.ts" />
(function () {
	"use strict";

	/** @typedef {Window & {
	 * 	AM2DSLEditorGraphOps?: AM2DSLEditorGraphOpsApi,
	 * 	AM2DSLEditorRegistryAPI?: AM2DSLEditorRegistryApi,
	 * }} AM2FlowStepModalWindow
	 */
	/** @type {AM2FlowStepModalWindow} */
	const W = window;
	const graphOps = W.AM2DSLEditorGraphOps;
	const registryApi = W.AM2DSLEditorRegistryAPI;
	const formApi = W.AM2FlowStepModalForm;
	const jsonApi = W.AM2FlowStepModalJSON;
	const model = W.AM2FlowStepModalModel;
	const clip = W.AM2FlowJSONClipboard;
	const fileIO = W.AM2FlowJSONFileIO;
	if (!graphOps || !registryApi || !formApi || !jsonApi || !model) return;

	/** @param {string} id
	 * @returns {HTMLElement | null}
	 */
	function $(id) {
		return document.getElementById(id);
	}

	/** @template T
	 * @param {T} value
	 * @returns {T}
	 */
	function deepClone(value) {
		return JSON.parse(JSON.stringify(value));
	}

	/** @param {string} id
	 * @returns {HTMLButtonElement | null}
	 */
	function button(id) {
		return /** @type {HTMLButtonElement|null} */ ($(id));
	}

	const ui = {
		modal: $("flowStepModal"),
		title: $("flowStepModalTitle"),
		subtitle: $("flowStepModalSubtitle"),
		dirty: $("flowStepModalDirtySummary"),
		status: $("flowStepModalStatus"),
		error: $("flowStepModalError"),
		body: $("flowStepModalBody"),
		jsonPanel: $("flowStepModalJsonPanel"),
		actionStatus: $("flowStepModalActionStatus"),
		json: /** @type {HTMLTextAreaElement|null} */ (
			$("flowStepModalJsonEditor")
		),
		jsonReread: button("flowStepModalJsonReread"),
		jsonAbort: button("flowStepModalJsonAbort"),
		jsonSave: button("flowStepModalJsonSave"),
		jsonOpenFromFile: button("flowStepModalJsonOpenFromFile"),
		jsonSaveToFile: button("flowStepModalJsonSaveToFile"),
		jsonCopySelected: button("flowStepModalJsonCopySelected"),
		jsonCopyAll: button("flowStepModalJsonCopyAll"),
		tabForm: button("flowStepModalTabForm"),
		tabJson: button("flowStepModalTabJson"),
		validate: button("flowStepModalValidate"),
		save: button("flowStepModalSave"),
		restore: button("flowStepModalRestore"),
		close: button("flowStepModalClose"),
	};

	/** @type {AM2FlowStepModalStateShape} */
	const state = {
		open: false,
		view: "form",
		selectedLibraryId: "",
		originalStepId: "",
		baselineStep: null,
		workingStep: null,
		fieldBuffers: {},
		jsonBuffer: "",
		jsonDirty: false,
	};

	function currentStep() {
		return graphOps.currentNode ? graphOps.currentNode() : null;
	}

	function wholeArtifactOpen() {
		const modal = W.AM2FlowJSONModalState;
		return !!(modal && modal.isOpen && modal.isOpen() === true);
	}

	/** @param {AM2JsonObject | null | undefined} step
	 * @returns {string}
	 */
	function stepSubtitle(step) {
		const op =
			step && step.op && typeof step.op === "object" && !Array.isArray(step.op)
				? step.op
				: {};
		const primitiveId = String(op.primitive_id || "");
		const version = String(
			op.primitive_version === undefined ? "" : op.primitive_version,
		);
		return primitiveId
			? primitiveId + (version ? " v" + version : "")
			: "Selected step";
	}

	/**
	 * @param {HTMLElement | null | undefined} element
	 * @param {string} text
	 * @param {string} kind
	 */
	function updateStatusElement(element, text, kind) {
		if (!element) return;
		element.textContent = String(text || "");
		element.classList.toggle("is-ok", kind === "ok");
		element.classList.toggle("is-bad", kind === "bad");
	}

	/** @param {string} text
	 * @param {string} kind
	 */
	function setStatus(text, kind) {
		updateStatusElement(ui.status, text, kind);
		updateStatusElement(ui.actionStatus, text, kind);
	}

	/**
	 * @param {AM2EditorHttpPayload | AM2JsonValue | undefined} payload
	 * @param {string} fallback
	 * @returns {string}
	 */
	function extractErrorMessage(payload, fallback) {
		const record =
			typeof payload === "object" && !Array.isArray(payload) && payload
				? payload
				: null;
		const errorValue = record && record.error ? record.error : null;
		if (
			errorValue &&
			typeof errorValue === "object" &&
			!Array.isArray(errorValue) &&
			errorValue.message
		) {
			return String(errorValue.message || fallback);
		}
		return String(fallback);
	}

	/**
	 * @param {AM2EditorHttpPayload | AM2JsonValue | undefined} payload
	 * @param {AM2JsonObject} fallback
	 * @returns {AM2JsonObject}
	 */
	function extractDefinitionPayload(payload, fallback) {
		const record =
			typeof payload === "object" && !Array.isArray(payload) && payload
				? payload
				: null;
		const next = record && record.definition ? record.definition : null;
		return next && typeof next === "object" && !Array.isArray(next)
			? next
			: fallback;
	}

	/** @param {string} text */
	function setError(text) {
		if (!ui.error) return;
		ui.error.textContent = String(text || "");
	}

	function hasUnsavedModalChanges() {
		return (
			model.pendingBufferCount(state) > 0 ||
			model.workingStateDirty(state) === true
		);
	}

	/** @param {string} message
	 * @returns {boolean}
	 */
	function confirmDiscard(message) {
		if (typeof window.confirm !== "function") return true;
		return window.confirm(message);
	}

	function stepFileName() {
		const raw = String(
			(state.workingStep && state.workingStep.step_id) || "selected_step",
		);
		const safe = raw.replace(/[^A-Za-z0-9._-]+/g, "_");
		return safe ? safe + ".json" : "selected_step.json";
	}

	function jsonEditorValue() {
		if (ui.json) {
			return String(ui.json.value || "");
		}
		return state.jsonDirty
			? String(state.jsonBuffer || "")
			: JSON.stringify(state.workingStep || {}, null, 2);
	}

	function selectedJSONText() {
		if (!ui.json) return "";
		const start = ui.json.selectionStart || 0;
		const end = ui.json.selectionEnd || 0;
		if (start === end) return "";
		return String(ui.json.value || "").slice(start, end);
	}

	/** @param {string} nextText */
	function writeJSONBuffer(nextText) {
		state.jsonBuffer = String(nextText || "");
		state.jsonDirty = true;
		if (ui.json) {
			ui.json.value = state.jsonBuffer;
		}
		updateDirtySummary();
	}

	/**
	 * @param {string} fileName
	 * @param {string} text
	 */
	function downloadJSONFile(fileName, text) {
		const blobCtor = typeof window.Blob === "function" ? window.Blob : null;
		const urlApi = window.URL;
		if (!blobCtor || !urlApi || typeof urlApi.createObjectURL !== "function") {
			throw new Error("Save to file unavailable in this browser.");
		}
		const link = document.createElement("a");
		const href = urlApi.createObjectURL(
			new blobCtor([String(text || "")], { type: "application/json" }),
		);
		try {
			link.href = href;
			link.download = fileName;
			link.style.display = "none";
			document.body && document.body.appendChild(link);
			if (typeof link.click !== "function") {
				throw new Error("Save to file unavailable in this browser.");
			}
			link.click();
		} finally {
			if (document.body && link.parentNode === document.body) {
				document.body.removeChild(link);
			}
			if (typeof urlApi.revokeObjectURL === "function") {
				urlApi.revokeObjectURL(href);
			}
		}
	}

	function confirmRereadDiscards() {
		if (hasUnsavedModalChanges()) {
			if (
				!confirmDiscard(
					"Discard modal changes and re-read the step from server?",
				)
			) {
				return false;
			}
		}
		const flowEditor = W.AM2FlowEditorState;
		const snap =
			flowEditor && flowEditor.getSnapshot ? flowEditor.getSnapshot() : null;
		if (snap && snap.draftDirty === true) {
			if (
				!confirmDiscard(
					"Discard current unsaved Flow Editor changes " +
						"and re-read the step from server?",
				)
			) {
				return false;
			}
		}
		return true;
	}

	function updateDirtySummary() {
		if (!ui.dirty) return;
		const pending = model.pendingBufferCount(state);
		if (pending > 0) {
			ui.dirty.textContent = String(pending) + " pending modal change(s).";
		} else if (model.workingStateDirty(state)) {
			ui.dirty.textContent =
				"Unsaved step changes are ready to validate or save.";
		} else {
			ui.dirty.textContent = "No pending modal changes.";
		}
		ui.dirty.classList.toggle("is-dirty", hasUnsavedModalChanges());
	}

	function reflectOpenState() {
		if (!ui.modal) return;
		ui.modal.classList.toggle("is-hidden", state.open !== true);
		ui.modal.setAttribute(
			"aria-hidden",
			state.open === true ? "false" : "true",
		);
	}

	function refreshTitle() {
		if (ui.title) {
			ui.title.textContent = String(
				(state.workingStep && state.workingStep.step_id) || "Selected step",
			);
		}
		if (ui.subtitle) {
			ui.subtitle.textContent = stepSubtitle(state.workingStep);
		}
	}

	function flushPendingEdits() {
		return model.flushPendingEdits(state, formApi, setError, state.view);
	}

	function renderView() {
		if (!state.open || !ui.body || !ui.json) return;
		ui.body.replaceChildren();
		ui.tabForm && ui.tabForm.classList.toggle("active", state.view === "form");
		ui.tabJson && ui.tabJson.classList.toggle("active", state.view === "json");
		ui.body.classList.toggle("is-hidden", state.view !== "form");
		ui.jsonPanel &&
			ui.jsonPanel.classList.toggle("is-hidden", state.view !== "json");
		if (state.view === "form") {
			if (!state.workingStep) {
				return;
			}
			formApi.renderForm({
				mount: ui.body,
				step: state.workingStep,
				handlers: {
					isFieldDirty: function (fieldId) {
						return model.isFieldDirty(state, fieldId);
					},
					readFieldValue: function (spec) {
						return model.readFieldValue(state, spec);
					},
					onFieldInput: function (spec, value) {
						state.fieldBuffers[String(spec.fieldId || "")] = String(
							value || "",
						);
						updateDirtySummary();
					},
					onFieldApply: function (spec) {
						setError("");
						if (!model.flushField(state, formApi, spec.fieldId, setError))
							return;
						setStatus("Field applied to the modal working state.", "ok");
						refreshTitle();
						updateDirtySummary();
						renderView();
					},
				},
			});
			return;
		}
		jsonApi.renderJSON({
			textarea: ui.json,
			value: state.jsonDirty
				? state.jsonBuffer
				: JSON.stringify(state.workingStep || {}, null, 2),
			onInput: function (value) {
				state.jsonBuffer = String(value || "");
				state.jsonDirty = true;
				updateDirtySummary();
			},
		});
	}

	function canDiscardModalChanges() {
		if (!hasUnsavedModalChanges()) return true;
		return window.confirm("Discard unsaved modal changes?");
	}

	async function rereadStepFromServer() {
		let ok = false;
		let next = null;
		setError("");
		setStatus("", "");
		if (!confirmRereadDiscards()) return false;
		try {
			if (!W.AM2DSLEditorV3 || !W.AM2DSLEditorV3.reloadAll) {
				throw new Error("Step re-read unavailable.");
			}
			ok = (await W.AM2DSLEditorV3.reloadAll({ skipConfirm: true })) !== false;
			if (!ok) {
				setError("Re-read failed.");
				return false;
			}
			if (state.selectedLibraryId && graphOps.setSelectedLibrary) {
				graphOps.setSelectedLibrary(state.selectedLibraryId);
			}
			if (graphOps.setSelectedStep) {
				graphOps.setSelectedStep(state.originalStepId);
			}
			next = currentStep();
			if (!next) {
				setError("Selected step is unavailable after re-read.");
				return false;
			}
			state.baselineStep = deepClone(next);
			state.workingStep = deepClone(next);
			state.fieldBuffers = {};
			model.rebuildJsonBuffer(state);
			setStatus("Step re-read from server.", "ok");
			refreshTitle();
			updateDirtySummary();
			renderView();
			return true;
		} catch (err) {
			setError(String(err || "Re-read failed."));
			return false;
		}
	}

	function abortJSONChanges() {
		state.jsonBuffer = JSON.stringify(state.workingStep || {}, null, 2);
		state.jsonDirty = false;
		setError("");
		setStatus("JSON changes discarded.", "ok");
		updateDirtySummary();
		renderView();
		return true;
	}

	async function openJSONFromFile() {
		let result = null;
		setError("");
		setStatus("", "");
		if (!fileIO || !fileIO.openTextFile) {
			setError("Open from file unavailable.");
			return false;
		}
		if (hasUnsavedModalChanges()) {
			if (
				!confirmDiscard(
					"Discard current modal changes and open JSON from file?",
				)
			) {
				return false;
			}
		}
		try {
			result = await fileIO.openTextFile("wizard");
			if (!result || result.cancelled === true) {
				return false;
			}
			writeJSONBuffer(String(result.text || ""));
			setStatus("JSON loaded from file.", "ok");
			return true;
		} catch (err) {
			setError(String(err || "Open from file failed."));
			return false;
		}
	}

	async function saveJSONToFile() {
		setError("");
		setStatus("", "");
		try {
			downloadJSONFile(stepFileName(), jsonEditorValue());
			setStatus("JSON saved to file.", "ok");
			return true;
		} catch (err) {
			setError(String(err || "Save to file failed."));
			return false;
		}
	}

	function copySelectedJSON() {
		const text = selectedJSONText();
		setError("");
		setStatus("", "");
		if (!text) {
			setError("No text selected.");
			return false;
		}
		if (!clip || !clip.copyText) {
			setError("Copy selected unavailable.");
			return false;
		}
		void clip.copyText(text).then(
			function () {
				setStatus("Selected JSON copied.", "ok");
			},
			function (err) {
				setError(String(err || "Copy selected failed."));
			},
		);
		return true;
	}

	function copyAllJSON() {
		setError("");
		setStatus("", "");
		if (!clip || !clip.copyText) {
			setError("Copy all unavailable.");
			return false;
		}
		void clip.copyText(jsonEditorValue()).then(
			function () {
				setStatus("Full JSON copied.", "ok");
			},
			function (err) {
				setError(String(err || "Copy all failed."));
			},
		);
		return true;
	}

	/** @param {string} stepId
	 * @returns {Promise<boolean>}
	 */
	async function openStep(stepId) {
		if (wholeArtifactOpen()) {
			window.alert(
				"Close the whole-artifact JSON editor before opening a step modal.",
			);
			return false;
		}
		if (state.open === true && !canDiscardModalChanges()) return false;
		const current = currentStep();
		if (String((current && current.step_id) || "") !== String(stepId || "")) {
			graphOps.setSelectedStep(stepId);
		}
		const next = currentStep();
		if (!next) {
			setError("Selected step is unavailable.");
			return false;
		}
		state.open = true;
		state.view = "form";
		state.selectedLibraryId = String(
			graphOps.selectedLibraryId ? graphOps.selectedLibraryId() : "",
		);
		state.originalStepId = String(next.step_id || "");
		state.baselineStep = deepClone(next);
		state.workingStep = deepClone(next);
		state.fieldBuffers = {};
		model.rebuildJsonBuffer(state);
		setStatus("", "");
		setError("");
		refreshTitle();
		updateDirtySummary();
		reflectOpenState();
		renderView();
		return true;
	}

	function closeModal() {
		if (!canDiscardModalChanges()) return false;
		state.open = false;
		state.fieldBuffers = {};
		state.jsonDirty = false;
		reflectOpenState();
		setStatus("", "");
		setError("");
		return true;
	}

	function restoreBaseline() {
		state.workingStep = deepClone(state.baselineStep || {});
		state.fieldBuffers = {};
		model.rebuildJsonBuffer(state);
		setError("");
		setStatus("Step restored to the last stable baseline.", "ok");
		refreshTitle();
		updateDirtySummary();
		renderView();
		return true;
	}

	async function validateStep() {
		setError("");
		setStatus("", "");
		if (!flushPendingEdits()) return false;
		let out = null;
		try {
			out = await registryApi.validateWizardDefinition(
				model.buildCandidateDefinition(state, graphOps).definition,
			);
		} catch (err) {
			setError(String(err || "Validate failed."));
			return false;
		}
		if (!out || !out.ok) {
			setError(extractErrorMessage(out && out.data, "Validate failed."));
			setStatus("Validate failed.", "bad");
			return false;
		}
		setStatus("Validate OK.", "ok");
		refreshTitle();
		updateDirtySummary();
		renderView();
		return true;
	}

	async function saveStep() {
		setError("");
		setStatus("", "");
		if (!flushPendingEdits()) return false;
		const candidate = model.buildCandidateDefinition(state, graphOps);
		try {
			const validation = await registryApi.validateWizardDefinition(
				candidate.definition,
			);
			if (!validation.ok) {
				setError(extractErrorMessage(validation.data, "Validate failed."));
				setStatus("Save failed during validation.", "bad");
				return false;
			}
			const saveOut = await registryApi.saveWizardDefinition(
				extractDefinitionPayload(validation.data, candidate.definition),
			);
			if (!saveOut.ok) {
				setError(extractErrorMessage(saveOut.data, "Save failed."));
				setStatus("Save failed.", "bad");
				return false;
			}
			const activateOut = await registryApi.activateWizardDefinition();
			if (!activateOut.ok) {
				setError(extractErrorMessage(activateOut.data, "Activate failed."));
				setStatus("Save failed during activation.", "bad");
				return false;
			}
			if (W.AM2DSLEditorV3 && W.AM2DSLEditorV3.reloadAll) {
				await W.AM2DSLEditorV3.reloadAll({ skipConfirm: true });
			}
			if (state.selectedLibraryId && graphOps.setSelectedLibrary) {
				graphOps.setSelectedLibrary(state.selectedLibraryId);
			}
			graphOps.setSelectedStep(candidate.nextStepId);
			model.syncFromSavedStep(state, graphOps, candidate.nextStepId);
			setStatus("Step saved for future runs.", "ok");
			updateDirtySummary();
			renderView();
			return true;
		} catch (err) {
			setError(String(err || "Save failed."));
			setStatus("Save failed.", "bad");
			return false;
		}
	}

	/** @param {string} nextView
	 * @returns {boolean}
	 */
	function setView(nextView) {
		if (nextView === state.view) return true;
		setError("");
		if (!flushPendingEdits()) return false;
		state.view = nextView === "json" ? "json" : "form";
		updateDirtySummary();
		renderView();
		return true;
	}

	ui.tabForm &&
		ui.tabForm.addEventListener("click", function () {
			setView("form");
		});
	ui.tabJson &&
		ui.tabJson.addEventListener("click", function () {
			setView("json");
		});
	ui.close &&
		ui.close.addEventListener("click", function () {
			closeModal();
		});
	ui.restore &&
		ui.restore.addEventListener("click", function () {
			restoreBaseline();
		});
	ui.validate &&
		ui.validate.addEventListener("click", function () {
			void validateStep();
		});
	ui.save &&
		ui.save.addEventListener("click", function () {
			void saveStep();
		});
	ui.jsonReread &&
		ui.jsonReread.addEventListener("click", function () {
			void rereadStepFromServer();
		});
	ui.jsonAbort &&
		ui.jsonAbort.addEventListener("click", function () {
			abortJSONChanges();
		});
	ui.jsonSave &&
		ui.jsonSave.addEventListener("click", function () {
			void saveStep();
		});
	ui.jsonOpenFromFile &&
		ui.jsonOpenFromFile.addEventListener("click", function () {
			void openJSONFromFile();
		});
	ui.jsonSaveToFile &&
		ui.jsonSaveToFile.addEventListener("click", function () {
			void saveJSONToFile();
		});
	ui.jsonCopySelected &&
		ui.jsonCopySelected.addEventListener("click", function () {
			copySelectedJSON();
		});
	ui.jsonCopyAll &&
		ui.jsonCopyAll.addEventListener("click", function () {
			copyAllJSON();
		});

	W.AM2FlowStepModalState = {
		closeModal: closeModal,
		isOpen: function () {
			return state.open === true;
		},
		openStep: openStep,
		restoreBaseline: restoreBaseline,
		reReadStep: rereadStepFromServer,
		setView: setView,
		validateStep: validateStep,
	};
})();
