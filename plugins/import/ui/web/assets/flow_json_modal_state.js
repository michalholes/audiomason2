(() => {
	/** @type {Window} */
	var root = window;

	var dom = root.AM2FlowJSONModalDOM;
	var clip = root.AM2FlowJSONClipboard;
	var fileIO = root.AM2FlowJSONFileIO;
	if (!dom || !clip || !fileIO) {
		return;
	}

	/** @param {AM2JsonValue | undefined} obj */
	function pretty(obj) {
		return JSON.stringify(obj, null, 2);
	}

	/** @template T
	 * @param {T} obj
	 * @returns {T}
	 */
	function deepClone(obj) {
		return JSON.parse(JSON.stringify(obj));
	}

	/** @returns {AM2FlowSnapshot | null} */
	function snapshot() {
		var flowEditor = root.AM2FlowEditorState;
		return flowEditor && flowEditor.getSnapshot
			? flowEditor.getSnapshot()
			: null;
	}

	/** @param {AM2JsonObject} target
	 * @param {AM2JsonObject} source
	 */
	function replaceObject(target, source) {
		Object.keys(target).forEach((key) => {
			delete target[key];
		});
		Object.keys(source).forEach((key) => {
			target[key] = source[key];
		});
	}

	/** @param {AM2JsonObject | null | undefined} definition
	 * @returns {AM2JsonObject}
	 */
	function sanitizeWizard(definition) {
		var next = deepClone(definition || {});
		if (next && next._am2_ui) {
			delete next._am2_ui;
		}
		return next;
	}

	/** @param {AM2JsonObject | null | undefined} config
	 * @returns {AM2JsonObject}
	 */
	function sanitizeConfig(config) {
		var next = deepClone(config || {});
		if (next && next.ui) {
			delete next.ui;
		}
		return next;
	}

	/** @param {string} message */
	function confirmDiscard(message) {
		if (typeof root.confirm !== "function") {
			return true;
		}
		return root.confirm(message);
	}

	/** @param {string} message */
	function setModalError(message) {
		dom.setStatus("", "");
		dom.setError(String(message || ""));
	}

	/** @param {string} message */
	function setModalStatus(message) {
		dom.setError("");
		dom.setStatus(String(message || ""), "ok");
	}

	/** @type {{ artifact: AM2FlowJSONArtifact, lastLoadedText: string }} */
	var state = {
		artifact: "config",
		lastLoadedText: "",
	};

	/** @param {AM2FlowJSONArtifact} artifact */
	function driverFor(artifact) {
		if (artifact === "wizard") {
			return {
				key: "wizard",
				title: "Wizard JSON",
				subtitle:
					"WizardDefinition draft JSON. Save updates the draft. " +
					"Apply for future runs validates, saves, and activates it.",
				readCurrent: () => {
					var snap = snapshot();
					return sanitizeWizard((snap && snap.wizardDraft) || {});
				},
				stage: /** @param {AM2JsonObject} parsed */ (parsed) => {
					var flowEditor = root.AM2FlowEditorState;
					if (!flowEditor || !flowEditor.mutateWizard) {
						throw new Error("wizard draft bridge unavailable");
					}
					var next = sanitizeWizard(parsed || {});
					flowEditor.mutateWizard((draft) => {
						replaceObject(draft, next);
					});
				},
				reload: async () => {
					var api = root.AM2DSLEditorV3;
					if (api && api.reloadAll) {
						return (await api.reloadAll({ skipConfirm: true })) !== false;
					}
					var adapter = root.AM2FlowEditor && root.AM2FlowEditor.wizard;
					if (!adapter || !adapter.reload) {
						throw new Error("wizard reload unavailable");
					}
					return (await adapter.reload()) !== false;
				},
				save: async () => {
					var adapter = root.AM2FlowEditor && root.AM2FlowEditor.wizard;
					if (!adapter || !adapter.save) {
						throw new Error("wizard save unavailable");
					}
					return (await adapter.save()) !== false;
				},
				apply: async () => {
					var api = root.AM2DSLEditorV3;
					if (!api || !api.activateDefinition) {
						throw new Error("wizard activate unavailable");
					}
					return (await api.activateDefinition()) !== false;
				},
			};
		}
		return {
			key: "config",
			title: "FlowConfig JSON",
			subtitle:
				"FlowConfig draft JSON for runtime defaults and optional-step behavior. " +
				"Save updates the draft. Apply for future runs validates, saves, " +
				"and activates it.",
			readCurrent: () => {
				var snap = snapshot();
				return sanitizeConfig((snap && snap.configDraft) || {});
			},
			stage: /** @param {AM2JsonObject} parsed */ (parsed) => {
				var flowEditor = root.AM2FlowEditorState;
				if (!flowEditor || !flowEditor.mutateConfig) {
					throw new Error("config draft bridge unavailable");
				}
				var next = sanitizeConfig(parsed || {});
				flowEditor.mutateConfig((draft) => {
					replaceObject(draft, next);
				});
			},
			reload: async () => {
				var adapter = root.AM2FlowEditor && root.AM2FlowEditor.config;
				if (!adapter || !adapter.reload) {
					throw new Error("config reload unavailable");
				}
				return (await adapter.reload()) !== false;
			},
			save: async () => {
				var adapter = root.AM2FlowEditor && root.AM2FlowEditor.config;
				if (!adapter || !adapter.save) {
					throw new Error("config save unavailable");
				}
				return (await adapter.save()) !== false;
			},
			apply: async () => {
				var adapter = root.AM2FlowEditor && root.AM2FlowEditor.config;
				if (!adapter || !adapter.activate) {
					throw new Error("config activate unavailable");
				}
				return (await adapter.activate()) !== false;
			},
		};
	}

	function currentDriver() {
		return driverFor(state.artifact || "config");
	}

	function modalDirty() {
		return dom.getValue() !== state.lastLoadedText;
	}

	function stageFromEditor() {
		var driver = currentDriver();
		var parsed = JSON.parse(dom.getValue() || "{}");
		driver.stage(parsed);
	}

	/** @param {AM2FlowJSONArtifact} artifact */
	function prettyCurrent(artifact) {
		return pretty(driverFor(artifact).readCurrent());
	}

	function syncFromState() {
		var text = prettyCurrent(state.artifact);
		state.lastLoadedText = text;
		dom.setValue(text);
		return text;
	}

	/** @param {{
	 * 	artifact: AM2FlowJSONArtifact,
	 * 	title: string,
	 * 	subtitle: string,
	 * 	text: string,
	 * }} loaded
	 * @param {boolean=} openState
	 */
	function commitLoadedArtifact(loaded, openState) {
		state.artifact = loaded.artifact;
		state.lastLoadedText = loaded.text;
		dom.setArtifactMeta(loaded.title, loaded.subtitle);
		dom.setValue(loaded.text);
		if (typeof openState === "boolean") {
			dom.setOpen(openState);
		}
	}

	function confirmRereadDiscards() {
		if (state.artifact && modalDirty()) {
			if (
				!confirmDiscard("Discard modal changes and re-read the server draft?")
			) {
				return false;
			}
		}
		var snap = snapshot();
		if (snap && snap.draftDirty === true) {
			if (
				!confirmDiscard(
					"Discard current unsaved Flow Editor changes and re-read the server draft?",
				)
			) {
				return false;
			}
		}
		return true;
	}

	/** @param {AM2FlowJSONArtifact} artifact */
	async function reloadArtifact(artifact) {
		var driver = driverFor(artifact);
		var ok = await driver.reload();
		if (!ok) {
			return null;
		}
		return {
			artifact: artifact,
			title: driver.title,
			subtitle: driver.subtitle,
			text: prettyCurrent(artifact),
		};
	}

	async function rereadFromServer() {
		var loaded = null;
		if (!confirmRereadDiscards()) {
			return false;
		}
		dom.clearFeedback();
		loaded = await reloadArtifact(state.artifact);
		if (!loaded) {
			setModalError("Re-read failed.");
			return false;
		}
		commitLoadedArtifact(loaded);
		setModalStatus("Draft re-read from server.");
		return true;
	}

	async function saveDraft() {
		var ok = false;
		try {
			dom.clearFeedback();
			stageFromEditor();
			ok = await currentDriver().save();
			if (!ok) {
				setModalError("Save failed.");
				return false;
			}
			syncFromState();
			setModalStatus("Draft saved.");
			return true;
		} catch (err) {
			setModalError(String(err || "Save failed."));
			return false;
		}
	}

	async function applyForFutureRuns() {
		var ok = false;
		try {
			dom.clearFeedback();
			stageFromEditor();
			ok = await currentDriver().apply();
			if (!ok) {
				setModalError("Apply for future runs failed.");
				return false;
			}
			syncFromState();
			setModalStatus("Applied for future runs.");
			return true;
		} catch (err) {
			setModalError(String(err || "Apply for future runs failed."));
			return false;
		}
	}

	function abortChanges() {
		dom.setValue(state.lastLoadedText);
		setModalStatus("Modal changes discarded.");
		return true;
	}

	function cancelModal() {
		dom.setOpen(false);
		dom.clearFeedback();
		return true;
	}

	/** @param {KeyboardEvent | null | undefined} event */
	function closeViaEscape(event) {
		if (!event || event.key !== "Escape" || !dom.isOpen()) {
			return;
		}
		cancelModal();
	}

	function copySelected() {
		var text = dom.getSelectedText();
		if (!text) {
			setModalError("No text selected.");
			return Promise.resolve(false);
		}
		return clip.copyText(text).then(
			() => {
				setModalStatus("Selected JSON copied.");
				return true;
			},
			(err) => {
				setModalError(String(err || "Copy selected failed."));
				return false;
			},
		);
	}

	function copyAll() {
		return clip.copyText(dom.getValue()).then(
			() => {
				setModalStatus("Full JSON copied.");
				return true;
			},
			(err) => {
				setModalError(String(err || "Copy all failed."));
				return false;
			},
		);
	}

	async function openFromFile() {
		var result = null;
		if (
			modalDirty() &&
			!confirmDiscard("Discard current modal changes and open JSON from file?")
		) {
			return false;
		}
		try {
			result = await fileIO.openTextFile(state.artifact);
			if (!result || result.cancelled === true) {
				return false;
			}
			dom.setValue(String(result.text || ""));
			setModalStatus("JSON loaded from file.");
			return true;
		} catch (err) {
			setModalError(String(err || "Open from file failed."));
			return false;
		}
	}

	async function saveToFile() {
		try {
			await fileIO.saveTextFile(state.artifact, dom.getValue());
			setModalStatus("JSON saved to file.");
			return true;
		} catch (err) {
			setModalError(String(err || "Save to file failed."));
			return false;
		}
	}

	/** @param {AM2FlowJSONArtifact} artifact */
	async function openModal(artifact) {
		var loaded = null;
		/** @type {AM2FlowJSONArtifact} */
		var nextArtifact = artifact === "wizard" ? "wizard" : "config";
		var wasOpen = dom.isOpen();
		var stepModal = root.AM2FlowStepModalState;
		if (stepModal && stepModal.isOpen && stepModal.isOpen() === true) {
			setModalError(
				"Close the open step modal before opening whole-artifact JSON.",
			);
			return false;
		}
		if (!confirmRereadDiscards()) {
			return false;
		}
		dom.clearFeedback();
		try {
			loaded = await reloadArtifact(nextArtifact);
			if (!loaded) {
				if (wasOpen === true) {
					setModalError("Re-read failed.");
				}
				return false;
			}
			commitLoadedArtifact(loaded, true);
			setModalStatus("Draft re-read from server.");
			return true;
		} catch (err) {
			if (wasOpen === true) {
				setModalError(String(err || "Re-read failed."));
			}
			return false;
		}
	}

	/**
	 * @param {HTMLElement | null | undefined} node
	 * @param {() => boolean | Promise<boolean>} handler
	 */
	function bind(node, handler) {
		if (!node || !node.addEventListener) {
			return;
		}
		node.addEventListener("click", () => {
			void handler();
		});
	}

	bind(dom.ui.reread, rereadFromServer);
	bind(dom.ui.abort, abortChanges);
	bind(dom.ui.save, saveDraft);
	bind(dom.ui.openFromFile, openFromFile);
	bind(dom.ui.saveToFile, saveToFile);
	bind(dom.ui.close, cancelModal);
	bind(dom.ui.cancel, cancelModal);
	bind(dom.ui.copySelected, copySelected);
	bind(dom.ui.copyAll, copyAll);
	bind(dom.ui.apply, applyForFutureRuns);
	if (typeof root.addEventListener === "function") {
		root.addEventListener("keydown", closeViaEscape);
	}

	root.AM2FlowJSONModalState = {
		abortChanges: abortChanges,
		isOpen: function isOpen() {
			return dom.isOpen();
		},
		applyForFutureRuns: applyForFutureRuns,
		cancelModal: cancelModal,
		copyAll: copyAll,
		copySelected: copySelected,
		openFromFile: openFromFile,
		openModal: openModal,
		rereadFromServer: rereadFromServer,
		saveDraft: saveDraft,
		saveToFile: saveToFile,
		_syncFromState: syncFromState,
	};
})();
