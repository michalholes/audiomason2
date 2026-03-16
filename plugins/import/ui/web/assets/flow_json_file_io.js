(() => {
	var root = /** @type {any} */ (window);

	var hooks = {
		openTextFile: null,
		saveTextFile: null,
	};

	function fileNameForArtifact(artifact) {
		return artifact === "wizard"
			? "wizard_definition_draft.json"
			: "flow_config_draft.json";
	}

	function isCancelledError(err) {
		return !!(
			err &&
			typeof err === "object" &&
			("name" in err ? String(err.name || "") === "AbortError" : false)
		);
	}

	function normalizeOpenResult(result) {
		if (result == null) {
			return { cancelled: true, text: "" };
		}
		if (typeof result === "object" && result.cancelled === true) {
			return { cancelled: true, text: "" };
		}
		if (typeof result === "object" && "text" in result) {
			return {
				cancelled: false,
				text: String(result.text || ""),
			};
		}
		return {
			cancelled: false,
			text: String(result),
		};
	}

	function readFileAsText(file) {
		if (file && typeof file.text === "function") {
			return file.text();
		}
		return new Promise((resolve, reject) => {
			if (typeof FileReader !== "function") {
				reject(new Error("Open from file unavailable in this browser."));
				return;
			}
			var reader = new FileReader();
			reader.onload = () => {
				resolve(String(reader.result || ""));
			};
			reader.onerror = () => {
				reject(reader.error || new Error("Open from file failed."));
			};
			reader.readAsText(file);
		});
	}

	async function openWithPicker() {
		var handles = null;
		var file = null;
		try {
			handles = await root.showOpenFilePicker({
				excludeAcceptAllOption: false,
				multiple: false,
				types: [
					{
						description: "JSON files",
						accept: {
							"application/json": [".json"],
							"text/plain": [".json", ".jsonl", ".txt"],
						},
					},
				],
			});
			if (!handles || !handles.length || !handles[0]) {
				return { cancelled: true, text: "" };
			}
			file = await handles[0].getFile();
			if (!file) {
				return { cancelled: true, text: "" };
			}
			return {
				cancelled: false,
				text: await readFileAsText(file),
			};
		} catch (err) {
			if (isCancelledError(err)) {
				return { cancelled: true, text: "" };
			}
			throw err;
		}
	}

	function openWithInput() {
		return new Promise((resolve, reject) => {
			var input = document.createElement("input");
			var settled = false;
			var focusHandler = null;
			var focusCancelTimer = null;
			var schedule =
				typeof root.setTimeout === "function"
					? root.setTimeout.bind(root)
					: null;
			var cancelScheduled =
				typeof root.clearTimeout === "function"
					? root.clearTimeout.bind(root)
					: null;
			var focusCancelDelayMs = 150;

			function hasSelectedFile() {
				return !!(input.files && input.files[0]);
			}

			function clearFocusCancelTimer() {
				if (focusCancelTimer == null) {
					return;
				}
				if (cancelScheduled) {
					cancelScheduled(focusCancelTimer);
				}
				focusCancelTimer = null;
			}

			function finish(result, err) {
				if (settled) {
					return;
				}
				settled = true;
				clearFocusCancelTimer();
				if (focusHandler && typeof root.removeEventListener === "function") {
					root.removeEventListener("focus", focusHandler, true);
				}
				if (document.body && input.parentNode === document.body) {
					document.body.removeChild(input);
				}
				if (err) {
					reject(err);
					return;
				}
				resolve(result);
			}

			function scheduleFocusCancelCheck() {
				if (settled || hasSelectedFile()) {
					return;
				}
				clearFocusCancelTimer();
				if (!schedule) {
					finish({ cancelled: true, text: "" });
					return;
				}
				focusCancelTimer = schedule(() => {
					focusCancelTimer = null;
					if (settled || hasSelectedFile()) {
						return;
					}
					finish({ cancelled: true, text: "" });
				}, focusCancelDelayMs);
			}

			input.type = "file";
			input.accept = ".json,application/json,text/plain,.jsonl,.txt";
			input.style.display = "none";
			input.addEventListener("change", async () => {
				clearFocusCancelTimer();
				var file = hasSelectedFile() ? input.files[0] : null;
				if (!file) {
					finish({ cancelled: true, text: "" });
					return;
				}
				try {
					finish({
						cancelled: false,
						text: await readFileAsText(file),
					});
				} catch (err) {
					finish(null, err || new Error("Open from file failed."));
				}
			});
			input.addEventListener("cancel", () => {
				clearFocusCancelTimer();
				finish({ cancelled: true, text: "" });
			});
			if (typeof root.addEventListener === "function") {
				focusHandler = () => {
					scheduleFocusCancelCheck();
				};
				root.addEventListener("focus", focusHandler, true);
			}
			if (document.body && document.body.appendChild) {
				document.body.appendChild(input);
			}
			if (typeof input.click !== "function") {
				finish(null, new Error("Open from file unavailable in this browser."));
				return;
			}
			input.click();
		});
	}

	async function defaultOpenTextFile() {
		if (typeof root.showOpenFilePicker === "function") {
			return openWithPicker();
		}
		return openWithInput();
	}

	async function defaultSaveTextFile(artifact, text) {
		var blobCtor = typeof root.Blob === "function" ? root.Blob : null;
		var urlApi = root.URL;
		if (!blobCtor || !urlApi || typeof urlApi.createObjectURL !== "function") {
			throw new Error("Save to file unavailable in this browser.");
		}
		var href = "";
		var link = document.createElement("a");
		var revoke =
			typeof urlApi.revokeObjectURL === "function"
				? urlApi.revokeObjectURL
				: null;
		try {
			href = urlApi.createObjectURL(
				new blobCtor([String(text || "")], { type: "application/json" }),
			);
			link.href = href;
			link.download = fileNameForArtifact(artifact);
			link.style.display = "none";
			if (document.body && document.body.appendChild) {
				document.body.appendChild(link);
			}
			if (typeof link.click !== "function") {
				throw new Error("Save to file unavailable in this browser.");
			}
			link.click();
		} finally {
			if (document.body && link.parentNode === document.body) {
				document.body.removeChild(link);
			}
			if (href && revoke) {
				revoke.call(urlApi, href);
			}
		}
	}

	function setHooks(nextHooks) {
		hooks.openTextFile =
			nextHooks && typeof nextHooks.openTextFile === "function"
				? nextHooks.openTextFile
				: null;
		hooks.saveTextFile =
			nextHooks && typeof nextHooks.saveTextFile === "function"
				? nextHooks.saveTextFile
				: null;
		return true;
	}

	function openTextFile(artifact) {
		var handler = hooks.openTextFile || defaultOpenTextFile;
		return Promise.resolve(handler(artifact)).then(normalizeOpenResult);
	}

	function saveTextFile(artifact, text) {
		var handler = hooks.saveTextFile || defaultSaveTextFile;
		return Promise.resolve(handler(artifact, String(text || "")));
	}

	root.AM2FlowJSONFileIO = {
		fileNameForArtifact: fileNameForArtifact,
		openTextFile: openTextFile,
		saveTextFile: saveTextFile,
		setHooks: setHooks,
	};
})();
