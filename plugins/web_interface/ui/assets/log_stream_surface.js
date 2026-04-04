/// <reference path="../../../../am2-globals.d.ts" />
(() => {
	/** @typedef {AM2WebContent} AM2LogWebContent */
	/** @typedef {AM2WebDebugRecord} AM2LogWebDebugRecord */
	/** @typedef {AM2WebNotifyFn} AM2LogWebNotifyFn */
	/** @typedef {AM2WebSurfaceDeps} AM2LogWebSurfaceDeps */
	/** @param {AM2LogWebContent | null | undefined} content */
	function resolveSurfaceKind(content) {
		const kind =
			content && typeof content.stream_kind === "string"
				? content.stream_kind.trim().toLowerCase()
				: "";
		return kind === "logbus" ? "logbus" : "eventbus";
	}

	/** @param {string} kind */
	function selectedFilename(kind) {
		return `${kind}_selected.txt`;
	}

	/** @param {string} kind */
	function allFilename(kind) {
		return `${kind}_all.txt`;
	}

	/** @param {string} text */
	async function copyTextWithFallback(text) {
		const payload = String(text || "");
		try {
			if (navigator.clipboard && navigator.clipboard.writeText) {
				await navigator.clipboard.writeText(payload);
				return true;
			}
		} catch {
			// fall through to deterministic textarea fallback
		}
		let ta = null;
		try {
			if (!document || !document.body || !document.createElement) return false;
			ta = document.createElement("textarea");
			ta.value = payload;
			ta.setAttribute("readonly", "true");
			ta.style.position = "absolute";
			ta.style.left = "-9999px";
			document.body.appendChild(ta);
			ta.select();
			return Boolean(document.execCommand && document.execCommand("copy"));
		} catch {
			return false;
		} finally {
			if (ta && ta.parentNode) ta.parentNode.removeChild(ta);
		}
	}

	/** @param {string} filename @param {string} text */
	function downloadText(filename, text) {
		const blobCtor = typeof window.Blob === "function" ? window.Blob : null;
		const urlApi = window.URL;
		if (!blobCtor || !urlApi || typeof urlApi.createObjectURL !== "function") {
			throw new Error("Save to file unavailable in this browser.");
		}
		if (!document || !document.createElement) {
			throw new Error("Save to file unavailable in this browser.");
		}
		let href = "";
		const link = document.createElement("a");
		const revoke =
			typeof urlApi.revokeObjectURL === "function"
				? urlApi.revokeObjectURL
				: null;
		try {
			href = urlApi.createObjectURL(
				new blobCtor([String(text || "")], {
					type: "text/plain;charset=utf-8",
				}),
			);
			link.href = href;
			link.download = filename;
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

	/** @param {Node} node */
	function readScopedSelection(node) {
		const sel = window.getSelection ? window.getSelection() : null;
		if (!sel || sel.rangeCount < 1) return "";
		const text = String(sel.toString() || "");
		if (!text) return "";
		const anchorNode = sel.anchorNode;
		const focusNode = sel.focusNode;
		if (!anchorNode || !focusNode) return "";
		if (!node.contains(anchorNode) || !node.contains(focusNode)) return "";
		return text;
	}

	function createDebugFeedShell(
		/** @type {Function} */ el,
		/** @type {string} */ hintText,
		/** @type {string} */ height,
	) {
		const root = el("div");
		const controls = el("div", { class: "row" });
		const filterInput = el("input", {
			class: "input",
			type: "text",
			placeholder: "Filter...",
		});
		filterInput.style.maxWidth = "420px";
		const pauseBtn = el("button", { class: "btn", text: "Pause" });
		const clearBtn = el("button", { class: "btn danger", text: "Clear" });
		const exportBtn = el("button", { class: "btn", text: "Export JSONL" });
		controls.append(filterInput, pauseBtn, clearBtn, exportBtn);
		root.append(controls, el("div", { class: "hint", text: hintText }));
		const box = el("div", { class: "logBox" });
		box.style.height = height;
		box.style.whiteSpace = "normal";
		root.appendChild(box);
		return { root, box, filterInput, pauseBtn, clearBtn, exportBtn };
	}

	function debugRecordMatches(
		/** @type {AM2LogWebDebugRecord} */ rec,
		/** @type {string} */ filterText,
		/** @type {string[]} */ fields,
	) {
		if (!filterText) return true;
		const hay = fields
			.map((field) => {
				const value = rec && typeof rec === "object" ? rec[field] : "";
				return typeof value === "string"
					? value
					: value == null
						? ""
						: String(value);
			})
			.join("\n")
			.toLowerCase();
		return hay.includes(filterText);
	}

	function snapshotDebugRecords(
		/** @type {Function} */ ensureBuffer,
		/** @type {string} */ filterText,
		/** @type {string[]} */ fields,
	) {
		const buf = ensureBuffer();
		const filter = String(filterText || "")
			.trim()
			.toLowerCase();
		const out = [];
		for (let i = buf.length - 1; i >= 0; i--) {
			const rec = buf[i];
			if (debugRecordMatches(rec, filter, fields)) out.push(rec);
		}
		return out;
	}

	function renderEmptyDebugState(
		/** @type {HTMLElement} */ box,
		/** @type {Function} */ clear,
		/** @type {Function} */ el,
		/** @type {string} */ emptyText,
	) {
		clear(box);
		box.appendChild(el("div", { class: "hint", text: emptyText }));
	}

	function downloadJsonLines(
		/** @type {string} */ filename,
		/** @type {string[]} */ lines,
	) {
		downloadText(filename, `${lines.join("\n")}\n`);
	}

	function startDebugFeedLoop(
		/** @type {HTMLElement} */ root,
		/** @type {() => boolean} */ isPaused,
		/** @type {() => void} */ renderOnce,
	) {
		renderOnce();
		const timer = setInterval(() => {
			if (!isPaused()) renderOnce();
		}, 500);
		const stop = () => clearInterval(timer);
		root.addEventListener("DOMNodeRemoved", stop, { once: true });
		window.addEventListener("popstate", stop, { once: true });
	}

	function renderJsErrorRow(
		/** @type {AM2LogWebDebugRecord} */ rec,
		/** @type {AM2LogWebNotifyFn} */ notify,
		/** @type {Function} */ el,
	) {
		const row = el("div");
		row.style.borderBottom = "1px solid rgba(255,255,255,0.06)";
		row.style.padding = "8px 0";
		const top = el("div", { class: "row" });
		top.style.margin = "0 0 6px 0";
		const meta = el("div", {
			class: "hint",
			text: `${rec.ts || ""}  ${rec.kind || ""}`.trim(),
		});
		meta.style.flex = "1";
		const copyBtn = el("button", { class: "btn", text: "Copy" });
		copyBtn.addEventListener("click", async () => {
			const ok = await copyTextWithFallback(JSON.stringify(rec, null, 2));
			if (typeof notify === "function") notify(ok ? "Copied." : "Copy failed.");
		});
		top.append(meta, copyBtn);
		const pre = el("pre");
		pre.style.margin = "0";
		pre.style.whiteSpace = "pre-wrap";
		pre.style.fontFamily =
			"ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas," +
			" 'Liberation Mono', 'Courier New', monospace";
		pre.style.fontSize = "12px";
		const parts = [];
		if (rec.message) parts.push(String(rec.message));
		if (rec.source) parts.push(`source: ${rec.source}`);
		if (rec.line !== null || rec.col !== null) {
			parts.push(`loc: ${rec.line ?? ""}:${rec.col ?? ""}`);
		}
		if (rec.stack) parts.push(String(rec.stack));
		pre.textContent = parts.join("\n");
		row.append(top, pre);
		return row;
	}

	function renderUiDebugRow(
		/** @type {AM2LogWebDebugRecord} */ rec,
		/** @type {AM2LogWebNotifyFn} */ notify,
		/** @type {Function} */ el,
		/** @type {Function} */ showModal,
	) {
		const row = el("div");
		row.style.borderBottom = "1px solid rgba(255,255,255,0.06)";
		row.style.padding = "8px 0";
		const top = el("div", { class: "row" });
		top.style.margin = "0 0 6px 0";
		const channel = rec.channel || "";
		const kind = rec.kind || "";
		const meta = el("div", {
			class: "hint",
			text: `${rec.ts || ""}  ${channel} ${kind}`.trim(),
		});
		meta.style.flex = "1";
		const detailsBtn = el("button", { class: "btn", text: "Details" });
		const copyBtn = el("button", { class: "btn", text: "Copy" });
		detailsBtn.addEventListener("click", () => {
			showModal(
				`${channel} ${kind}`.trim(),
				JSON.stringify(rec, null, 2),
				notify,
			);
		});
		copyBtn.addEventListener("click", async () => {
			const ok = await copyTextWithFallback(JSON.stringify(rec, null, 2));
			if (typeof notify === "function") notify(ok ? "Copied." : "Copy failed.");
		});
		top.append(meta, detailsBtn, copyBtn);
		row.appendChild(top);
		const msg =
			rec.message ||
			(rec.status
				? `${rec.method || ""} ${rec.url || ""} -> ${rec.status}`
				: "");
		row.appendChild(el("div", { class: "mono", text: String(msg || "") }));
		if (rec.response_text) {
			const pre = el("pre");
			pre.style.marginTop = "6px";
			pre.style.whiteSpace = "pre-wrap";
			pre.style.wordBreak = "break-word";
			pre.textContent = String(rec.response_text);
			row.appendChild(pre);
		}
		return row;
	}

	Reflect.set(window, "AMWebLogStreamSurface", {
		/**
		 * @param {AM2LogWebContent} content
		 * @param {AM2LogWebNotifyFn} notify
		 * @param {AM2LogWebSurfaceDeps} deps
		 */
		async render(content, notify, deps) {
			const { API, el } = deps;
			const kind = resolveSurfaceKind(content);
			const wrap = el("div", { class: "logWrap" });
			const controls = el("div", { class: "row" });
			const copySelectedBtn = el("button", {
				class: "btn",
				text: "Copy selected to clipboard",
			});
			const copyAllBtn = el("button", {
				class: "btn",
				text: "Copy all to clipboard",
			});
			const saveSelectedBtn = el("button", {
				class: "btn",
				text: "Save selected",
			});
			const saveAllBtn = el("button", { class: "btn", text: "Save all" });
			const flushBtn = el("button", { class: "btn", text: "Flush" });
			controls.appendChild(copySelectedBtn);
			controls.appendChild(copyAllBtn);
			controls.appendChild(saveSelectedBtn);
			controls.appendChild(saveAllBtn);
			controls.appendChild(flushBtn);
			wrap.appendChild(controls);

			const pre = el("pre", { class: "logBox" });
			wrap.appendChild(pre);

			let buffer = "";
			/** @type {EventSource | null} */
			let eventSource = null;
			const observer = new MutationObserver(() => {
				if (document.body.contains(wrap)) return;
				if (eventSource) eventSource.close();
				observer.disconnect();
			});
			observer.observe(document.body, { childList: true, subtree: true });

			function renderBuffer() {
				pre.textContent = buffer;
				pre.scrollTop = pre.scrollHeight;
			}

			/** @param {string} text */
			function replaceBuffer(text) {
				buffer = String(text || "");
				renderBuffer();
			}

			/** @param {string} line */
			function appendLine(line) {
				buffer += `${String(line || "")}\n`;
				renderBuffer();
			}

			/** @param {string} text */
			async function copyPayload(text) {
				const ok = await copyTextWithFallback(text);
				if (typeof notify === "function") {
					notify(ok ? "Copied." : "Copy failed.");
				}
			}

			function requireScopedSelection() {
				const text = readScopedSelection(pre);
				if (text) return text;
				if (typeof notify === "function") {
					notify("Select text inside this log box.");
				}
				return "";
			}

			copySelectedBtn.addEventListener("click", async () => {
				const text = requireScopedSelection();
				if (text) await copyPayload(text);
			});
			copyAllBtn.addEventListener("click", async () => {
				await copyPayload(buffer);
			});
			saveSelectedBtn.addEventListener("click", () => {
				const text = requireScopedSelection();
				if (!text) return;
				try {
					downloadText(selectedFilename(kind), text);
					if (typeof notify === "function") notify("Saved.");
				} catch (e) {
					if (typeof notify === "function") notify(String(e));
				}
			});
			saveAllBtn.addEventListener("click", () => {
				try {
					downloadText(allFilename(kind), buffer);
					if (typeof notify === "function") notify("Saved.");
				} catch (e) {
					if (typeof notify === "function") notify(String(e));
				}
			});
			flushBtn.addEventListener("click", () => {
				replaceBuffer("");
				if (typeof notify === "function") notify("Flushed.");
			});

			try {
				if (
					content.tail_source &&
					content.tail_source.type === "api" &&
					typeof content.tail_source.path === "string"
				) {
					const t = await API.getJson(content.tail_source.path);
					if (t && typeof t.text === "string") {
						const tail = t.text.endsWith("\n") ? t.text : `${t.text}\n`;
						replaceBuffer(tail);
					}
				}
			} catch {
				// ignore tail bootstrap failures and keep the stream surface alive
			}

			const src = content.source;
			if (src && src.type === "sse" && typeof src.path === "string") {
				eventSource = new EventSource(src.path);
				eventSource.onmessage = /** @param {MessageEvent<string>} ev */ (
					ev,
				) => {
					appendLine(ev.data);
				};
				eventSource.onerror = () => {
					// keep box, EventSource retries automatically
				};
			} else {
				appendLine("(log stream source not configured)");
			}

			return wrap;
		},
	});
	Reflect.set(window, "AMWebAppDebugSurface", {
		/**
		 * @param {AM2LogWebContent} content
		 * @param {AM2LogWebNotifyFn} notify
		 * @param {{
		 * 	el: Function,
		 * 	clear: Function,
		 * 	ensureJsErrorBuffer: Function,
		 * }} deps
		 */
		async renderJsErrorFeed(content, notify, deps) {
			const { el, clear, ensureJsErrorBuffer } = deps;
			ensureJsErrorBuffer();
			let paused = false;
			let filterText = "";
			const shell = createDebugFeedShell(
				el,
				"Captures window.onerror and unhandledrejection (session-local).",
				"420px",
			);
			const fields = ["ts", "kind", "message", "stack", "source"];
			const renderOnce = () => {
				const items = snapshotDebugRecords(
					ensureJsErrorBuffer,
					filterText,
					fields,
				);
				if (!items.length) {
					renderEmptyDebugState(shell.box, clear, el, "No errors captured.");
					return;
				}
				clear(shell.box);
				for (const rec of items) {
					shell.box.appendChild(renderJsErrorRow(rec, notify, el));
				}
			};
			shell.filterInput.addEventListener("input", () => {
				filterText = String(shell.filterInput.value || "");
				renderOnce();
			});
			shell.pauseBtn.addEventListener("click", () => {
				paused = !paused;
				shell.pauseBtn.textContent = paused ? "Resume" : "Pause";
				if (!paused) renderOnce();
			});
			shell.clearBtn.addEventListener("click", () => {
				try {
					const buf = ensureJsErrorBuffer();
					buf.length = 0;
				} catch {}
				renderOnce();
			});
			shell.exportBtn.addEventListener("click", () => {
				try {
					const items = snapshotDebugRecords(
						ensureJsErrorBuffer,
						filterText,
						fields,
					);
					downloadJsonLines(
						"am_js_errors.jsonl",
						items.map((item) => JSON.stringify(item)),
					);
				} catch (e) {
					if (typeof notify === "function") notify(String(e));
				}
			});
			startDebugFeedLoop(shell.root, () => paused, renderOnce);
			return shell.root;
		},
		/**
		 * @param {AM2LogWebContent} content
		 * @param {AM2LogWebNotifyFn} notify
		 * @param {{
		 * 	el: Function,
		 * 	clear: Function,
		 * 	ensureUiLogBuffer: Function,
		 * 	showModal: Function,
		 * }} deps
		 */
		async renderUiDebugFeed(content, notify, deps) {
			const { el, clear, ensureUiLogBuffer, showModal } = deps;
			ensureUiLogBuffer();
			let paused = false;
			let filterText = "";
			const shell = createDebugFeedShell(
				el,
				"Debug mode: browser-side errors and HTTP failures (session-local).",
				"520px",
			);
			const fields = [
				"ts",
				"channel",
				"kind",
				"message",
				"url",
				"method",
				"response_text",
			];
			const renderOnce = () => {
				const items = snapshotDebugRecords(
					ensureUiLogBuffer,
					filterText,
					fields,
				);
				if (!items.length) {
					renderEmptyDebugState(
						shell.box,
						clear,
						el,
						"No debug records captured.",
					);
					return;
				}
				clear(shell.box);
				for (const rec of items) {
					shell.box.appendChild(renderUiDebugRow(rec, notify, el, showModal));
				}
				try {
					shell.box.scrollTop = shell.box.scrollHeight;
				} catch {}
			};
			shell.filterInput.addEventListener("input", () => {
				filterText = String(shell.filterInput.value || "");
				if (!paused) renderOnce();
			});
			shell.pauseBtn.addEventListener("click", () => {
				paused = !paused;
				shell.pauseBtn.textContent = paused ? "Resume" : "Pause";
				if (!paused) renderOnce();
			});
			shell.clearBtn.addEventListener("click", () => {
				const buf = ensureUiLogBuffer();
				buf.splice(0, buf.length);
				renderOnce();
			});
			shell.exportBtn.addEventListener("click", () => {
				const items = snapshotDebugRecords(
					ensureUiLogBuffer,
					filterText,
					fields,
				);
				downloadJsonLines(
					"audiomason_ui_debug.jsonl",
					items.map((item) => JSON.stringify(item)),
				);
			});
			startDebugFeedLoop(shell.root, () => paused, renderOnce);
			return shell.root;
		},
	});
})();
