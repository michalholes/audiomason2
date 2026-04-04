/// <reference path="../../../../../types/am2-import-ui-globals.d.ts" />
(() => {
	/** @type {Window} */
	var root = window;

	/** @type {AM2FlowJSONFileIOHooks} */
	var hooks = {};

	/** @param {AM2FlowJSONArtifact} artifact */
	function fileNameForArtifact(artifact) {
		return artifact === "wizard"
			? "wizard_definition_draft.json"
			: "flow_config_draft.json";
	}

	/** @param {unknown} err */
	function isCancelledError(err) {
		return !!(
			err &&
			typeof err === "object" &&
			("name" in err ? String(err.name || "") === "AbortError" : false)
		);
	}

	/** @param {AM2FlowJSONOpenResult | string | null} result
	 * @returns {AM2FlowJSONOpenResult}
	 */
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

	/** @param {File} file */
	function readFileAsText(file) {
		if (typeof file.text === "function") {
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
			if (typeof root.showOpenFilePicker !== "function") {
				throw new Error("Open from file unavailable in this browser.");
			}
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
			var reading = false;
			/** @type {((ev: FocusEvent) => void) | null} */
			var focusHandler = null;
			/** @type {number | null} */
			var focusSettleTimer = null;
			var focusSettleDeadline = 0;
			var schedule =
				typeof root.setTimeout === "function"
					? root.setTimeout.bind(root)
					: null;
			var cancelScheduled =
				typeof root.clearTimeout === "function"
					? root.clearTimeout.bind(root)
					: null;
			var now = typeof Date.now === "function" ? Date.now.bind(Date) : Date.now;
			var focusSettleWindowMs = 1000;
			var focusSettlePollMs = 25;

			function hasSelectedFile() {
				return !!(input.files && input.files[0]);
			}

			function clearFocusSettleTimer() {
				if (focusSettleTimer == null) {
					return;
				}
				if (cancelScheduled) {
					cancelScheduled(focusSettleTimer);
				}
				focusSettleTimer = null;
			}

			/** @param {AM2FlowJSONOpenResult | null} result
			 * @param {unknown} err
			 */
			function finish(result, err) {
				if (settled) {
					return;
				}
				settled = true;
				clearFocusSettleTimer();
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

			function finishFallbackExhausted() {
				finish(
					null,
					new Error(
						"Open from file failed after dialog close without a selected file.",
					),
				);
			}

			function consumeSelectedFile() {
				var file = null;
				if (settled || reading) {
					return true;
				}
				file = hasSelectedFile() && input.files ? input.files[0] : null;
				if (!file) {
					return false;
				}
				reading = true;
				clearFocusSettleTimer();
				Promise.resolve(readFileAsText(file)).then(
					(text) => {
						finish(
							{
								cancelled: false,
								text: String(text || ""),
							},
							undefined,
						);
					},
					(err) => {
						finish(null, err || new Error("Open from file failed."));
					},
				);
				return true;
			}

			function scheduleFocusSettleCheck() {
				var remaining = 0;
				if (settled || consumeSelectedFile()) {
					return;
				}
				clearFocusSettleTimer();
				remaining = focusSettleDeadline - now();
				if (remaining <= 0) {
					finishFallbackExhausted();
					return;
				}
				if (!schedule) {
					finishFallbackExhausted();
					return;
				}
				focusSettleTimer = schedule(
					() => {
						focusSettleTimer = null;
						scheduleFocusSettleCheck();
					},
					Math.min(focusSettlePollMs, remaining),
				);
			}

			function startFocusSettleWindow() {
				if (settled || reading) {
					return;
				}
				focusSettleDeadline = now() + focusSettleWindowMs;
				scheduleFocusSettleCheck();
			}

			input.type = "file";
			input.accept = ".json,application/json,text/plain,.jsonl,.txt";
			input.style.display = "none";
			input.addEventListener("change", () => {
				if (!consumeSelectedFile()) {
					finishFallbackExhausted();
				}
			});
			input.addEventListener("cancel", () => {
				clearFocusSettleTimer();
				finish({ cancelled: true, text: "" }, undefined);
			});
			if (typeof root.addEventListener === "function") {
				focusHandler = () => {
					startFocusSettleWindow();
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

	/** @param {AM2FlowJSONArtifact} artifact
	 * @param {string} text
	 */
	async function defaultSaveTextFile(artifact, text) {
		var blobCtor = typeof Blob === "function" ? Blob : null;
		var urlApi = typeof URL === "function" ? URL : null;
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

	/** @param {AM2FlowJSONFileIOHooks} nextHooks */
	function setHooks(nextHooks) {
		hooks.openTextFile =
			nextHooks && typeof nextHooks.openTextFile === "function"
				? nextHooks.openTextFile
				: undefined;
		hooks.saveTextFile =
			nextHooks && typeof nextHooks.saveTextFile === "function"
				? nextHooks.saveTextFile
				: undefined;
		return true;
	}

	/** @param {AM2FlowJSONArtifact} artifact */
	function openTextFile(artifact) {
		var handler = hooks.openTextFile || defaultOpenTextFile;
		return Promise.resolve(handler(artifact)).then(normalizeOpenResult);
	}

	/** @param {AM2FlowJSONArtifact} artifact
	 * @param {string} text
	 */
	function saveTextFile(artifact, text) {
		var handler = hooks.saveTextFile || defaultSaveTextFile;
		return Promise.resolve(handler(artifact, String(text || "")));
	}

	root.AM2FlowJSONFileIO = {
		fileNameForArtifact: fileNameForArtifact,
		normalizeOpenResult: normalizeOpenResult,
		openTextFile: openTextFile,
		saveTextFile: saveTextFile,
		setHooks: setHooks,
	};
})();
