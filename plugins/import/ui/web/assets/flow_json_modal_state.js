(() => {
	var root = /** @type {any} */ (window);

	var dom = root.AM2FlowJSONModalDOM;
	var clip = root.AM2FlowJSONClipboard;
	if (!dom || !clip) {
		return;
	}

	function pretty(obj) {
		return JSON.stringify(obj, null, 2);
	}

	function deepClone(obj) {
		return JSON.parse(JSON.stringify(obj));
	}

	function snapshot() {
		var flowEditor = root.AM2FlowEditorState;
		return flowEditor && flowEditor.getSnapshot
			? flowEditor.getSnapshot()
			: null;
	}

	function replaceObject(target, source) {
		Object.keys(target).forEach((key) => {
			delete target[key];
		});
		Object.keys(source).forEach((key) => {
			target[key] = source[key];
		});
	}

	function sanitizeWizard(definition) {
		var next = deepClone(definition || {});
		if (next && next._am2_ui) {
			delete next._am2_ui;
		}
		return next;
	}

	function sanitizeConfig(config) {
		var next = deepClone(config || {});
		if (next && next.ui) {
			delete next.ui;
		}
		return next;
	}

	function confirmDiscard(message) {
		if (typeof root.confirm !== "function") {
			return true;
		}
		return root.confirm(message);
	}

	var state = {
		artifact: "",
		lastLoadedText: "",
	};

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
				stage: (parsed) => {
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
			stage: (parsed) => {
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

	function syncFromState() {
		var current = currentDriver().readCurrent();
		var text = pretty(current);
		state.lastLoadedText = text;
		dom.setValue(text);
		return text;
	}

	function restoreModalSnapshot(snapshotState) {
		var driver = null;
		state.artifact = snapshotState.artifact || "";
		state.lastLoadedText = snapshotState.lastLoadedText || "";
		dom.setValue(snapshotState.value || "");
		dom.clearFeedback();
		if (snapshotState.artifact) {
			driver = driverFor(snapshotState.artifact);
			dom.setArtifactMeta(driver.title, driver.subtitle);
		} else {
			dom.setArtifactMeta("", "");
		}
		dom.setOpen(snapshotState.wasOpen === true);
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

	async function reloadArtifact(artifact) {
		var driver = driverFor(artifact);
		state.artifact = artifact;
		dom.setArtifactMeta(driver.title, driver.subtitle);
		var ok = await driver.reload();
		if (!ok) {
			return false;
		}
		syncFromState();
		return true;
	}

	async function rereadFromServer() {
		if (!confirmRereadDiscards()) {
			return false;
		}
		dom.clearFeedback();
		var ok = await reloadArtifact(currentDriver().key);
		if (!ok) {
			dom.setError("Re-read failed.");
			return false;
		}
		dom.setStatus("Draft re-read from server.", "ok");
		return true;
	}

	async function saveDraft() {
		var ok = false;
		try {
			dom.clearFeedback();
			stageFromEditor();
			ok = await currentDriver().save();
			if (!ok) {
				dom.setError("Save failed.");
				return false;
			}
			syncFromState();
			dom.setStatus("Draft saved.", "ok");
			return true;
		} catch (err) {
			dom.setError(String(err || "Save failed."));
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
				dom.setError("Apply for future runs failed.");
				return false;
			}
			syncFromState();
			dom.setStatus("Applied for future runs.", "ok");
			return true;
		} catch (err) {
			dom.setError(String(err || "Apply for future runs failed."));
			return false;
		}
	}

	function abortChanges() {
		dom.setValue(state.lastLoadedText);
		dom.setError("");
		dom.setStatus("Modal changes discarded.", "ok");
		return true;
	}

	function cancelModal() {
		dom.setOpen(false);
		dom.clearFeedback();
		return true;
	}

	function copySelected() {
		var text = dom.getSelectedText();
		if (!text) {
			dom.setError("No text selected.");
			return Promise.resolve(false);
		}
		return clip.copyText(text).then(
			() => {
				dom.setError("");
				dom.setStatus("Selected JSON copied.", "ok");
				return true;
			},
			(err) => {
				dom.setError(String(err || "Copy selected failed."));
				return false;
			},
		);
	}

	function copyAll() {
		return clip.copyText(dom.getValue()).then(
			() => {
				dom.setError("");
				dom.setStatus("Full JSON copied.", "ok");
				return true;
			},
			(err) => {
				dom.setError(String(err || "Copy all failed."));
				return false;
			},
		);
	}

	async function openModal(artifact) {
		var ok = false;
		var nextArtifact = artifact === "wizard" ? "wizard" : "config";
		var previous = {
			artifact: state.artifact,
			lastLoadedText: state.lastLoadedText,
			value: dom.getValue(),
			wasOpen: dom.isOpen(),
		};
		if (!confirmRereadDiscards()) {
			return false;
		}
		dom.clearFeedback();
		dom.setOpen(true);
		try {
			ok = await reloadArtifact(nextArtifact);
			if (!ok) {
				restoreModalSnapshot(previous);
				if (previous.wasOpen === true) {
					dom.setError("Re-read failed.");
				}
				return false;
			}
			dom.setStatus("Draft re-read from server.", "ok");
			return true;
		} catch (err) {
			restoreModalSnapshot(previous);
			if (previous.wasOpen === true) {
				dom.setError(String(err || "Re-read failed."));
			}
			return false;
		}
	}

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
	bind(dom.ui.cancel, cancelModal);
	bind(dom.ui.copySelected, copySelected);
	bind(dom.ui.copyAll, copyAll);
	bind(dom.ui.apply, applyForFutureRuns);

	root.AM2FlowJSONModalState = {
		abortChanges: abortChanges,
		applyForFutureRuns: applyForFutureRuns,
		cancelModal: cancelModal,
		copyAll: copyAll,
		copySelected: copySelected,
		openModal: openModal,
		rereadFromServer: rereadFromServer,
		saveDraft: saveDraft,
		_syncFromState: syncFromState,
	};
})();
