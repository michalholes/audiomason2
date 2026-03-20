(() => {
	function resolveSurfaceKind(content) {
		const kind =
			content && typeof content.stream_kind === "string"
				? content.stream_kind.trim().toLowerCase()
				: "";
		return kind === "logbus" ? "logbus" : "eventbus";
	}

	function selectedFilename(kind) {
		return `${kind}_selected.txt`;
	}

	function allFilename(kind) {
		return `${kind}_all.txt`;
	}

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

	Reflect.set(window, "AMWebLogStreamSurface", {
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

			function replaceBuffer(text) {
				buffer = String(text || "");
				renderBuffer();
			}

			function appendLine(line) {
				buffer += `${String(line || "")}\n`;
				renderBuffer();
			}

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
				if (content.tail_source && content.tail_source.type === "api") {
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
			if (src && src.type === "sse") {
				eventSource = new EventSource(src.path);
				eventSource.onmessage = (ev) => {
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
})();
