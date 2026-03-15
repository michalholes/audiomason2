(function () {
	"use strict";

	const W = /** @type {any} */ (window);
	const graphOps = W.AM2DSLEditorGraphOps;
	const registryApi = W.AM2DSLEditorRegistryAPI;
	const formApi = W.AM2FlowStepModalForm;
	const jsonApi = W.AM2FlowStepModalJSON;
	const model = W.AM2FlowStepModalModel;
	if (!graphOps || !registryApi || !formApi || !jsonApi || !model) return;

	function $(id) {
		return document.getElementById(id);
	}

	function deepClone(value) {
		return JSON.parse(JSON.stringify(value));
	}

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
		actionStatus: $("flowStepModalActionStatus"),
		json: /** @type {HTMLTextAreaElement|null} */ (
			$("flowStepModalJsonEditor")
		),
		tabForm: button("flowStepModalTabForm"),
		tabJson: button("flowStepModalTabJson"),
		validate: button("flowStepModalValidate"),
		save: button("flowStepModalSave"),
		restore: button("flowStepModalRestore"),
		close: button("flowStepModalClose"),
	};

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

	function stepSubtitle(step) {
		const primitiveId = String((step && step.op && step.op.primitive_id) || "");
		const version = String(
			(step && step.op && step.op.primitive_version) === undefined
				? ""
				: step.op.primitive_version,
		);
		return primitiveId
			? primitiveId + (version ? " v" + version : "")
			: "Selected step";
	}

	function updateStatusElement(element, text, kind) {
		if (!element) return;
		element.textContent = String(text || "");
		element.classList.toggle("is-ok", kind === "ok");
		element.classList.toggle("is-bad", kind === "bad");
	}

	function setStatus(text, kind) {
		updateStatusElement(ui.status, text, kind);
		updateStatusElement(ui.actionStatus, text, kind);
	}

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
		ui.json.classList.toggle("is-hidden", state.view !== "json");
		if (state.view === "form") {
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
						state.fieldBuffers[spec.fieldId] = String(value || "");
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

	async function openStep(stepId) {
		if (wholeArtifactOpen()) {
			window.alert(
				"Close the whole-artifact JSON editor before opening a step modal.",
			);
			return false;
		}
		if (state.open === true && !canDiscardModalChanges()) return false;
		if (
			String((currentStep() && currentStep().step_id) || "") !==
			String(stepId || "")
		) {
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
			setError(
				String(
					(out && out.data && out.data.error && out.data.error.message) ||
						"Validate failed.",
				),
			);
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
				setError(
					String(
						(validation.data &&
							validation.data.error &&
							validation.data.error.message) ||
							"Validate failed.",
					),
				);
				setStatus("Save failed during validation.", "bad");
				return false;
			}
			const saveOut = await registryApi.saveWizardDefinition(
				validation.data && validation.data.definition
					? validation.data.definition
					: candidate.definition,
			);
			if (!saveOut.ok) {
				setError(
					String(
						(saveOut.data &&
							saveOut.data.error &&
							saveOut.data.error.message) ||
							"Save failed.",
					),
				);
				setStatus("Save failed.", "bad");
				return false;
			}
			const activateOut = await registryApi.activateWizardDefinition();
			if (!activateOut.ok) {
				setError(
					String(
						(activateOut.data &&
							activateOut.data.error &&
							activateOut.data.error.message) ||
							"Activate failed.",
					),
				);
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

	W.AM2FlowStepModalState = {
		closeModal: closeModal,
		isOpen: function () {
			return state.open === true;
		},
		openStep: openStep,
		restoreBaseline: restoreBaseline,
		setView: setView,
		validateStep: validateStep,
	};
})();
