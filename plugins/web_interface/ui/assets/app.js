/// <reference path="../../../../am2-globals.d.ts" />
const _amWin = /** @type {Window} */ (window),
	_amUiAssetsBaseUrl = "/ui/assets/";

async function fetchJSON(
	/** @type {string} */ url,
	/** @type {RequestInit | undefined} */ opts,
) {
	const r = await fetch(url, opts || {});
	if (!r.ok) {
		const t = await r.text();
		throw new Error(r.status + " " + r.statusText + ": " + t);
	}
	const ct = r.headers.get("content-type") || "";
	if (ct.includes("application/json")) {
		return await r.json();
	}
	const t = await r.text();
	try {
		return JSON.parse(t);
	} catch {
		return { text: t };
	}
}

_amWin.__AM_APP_LOADED__ = true;

function _amFpKeyForBook(/** @type {AM2Book} */ book) {
	if (book && typeof book === "object") {
		if (typeof book.fingerprint === "string" && book.fingerprint)
			return book.fingerprint;
		if (typeof book.fp === "string" && book.fp) return book.fp;
		const meta = asObj(book.meta);
		if (meta && typeof meta.fingerprint === "string" && meta.fingerprint)
			return meta.fingerprint;
	}
	return "";
}

function _amNormalizeFpKey(/** @type {unknown} */ key) {
	if (typeof key !== "string") return "";
	return key.trim();
}

function asObj(/** @type {unknown} */ v) {
	return v && typeof v === "object" && !Array.isArray(v)
		? /** @type {AM2MaybeObj} */ (v)
		: null;
}

function _amEnsureUiLogBuffer() {
	if (!_amWin.__AM_UI_LOGS__ || !Array.isArray(_amWin.__AM_UI_LOGS__)) {
		_amWin.__AM_UI_LOGS__ = [];
	}
	return _amWin.__AM_UI_LOGS__;
}

function _amPushUiLog(/** @type {AM2WebDebugRecord} */ rec) {
	try {
		const buf = _amEnsureUiLogBuffer();
		buf.push(rec);
		if (buf.length > 4000) buf.splice(0, buf.length - 4000);
	} catch {}
}

function _amEnsureJsErrorBuffer() {
	if (!_amWin.__AM_JS_ERRORS__ || !Array.isArray(_amWin.__AM_JS_ERRORS__)) {
		_amWin.__AM_JS_ERRORS__ = [];
	}
	return _amWin.__AM_JS_ERRORS__;
}

function _amPushJsError(/** @type {AM2WebDebugRecord} */ rec) {
	try {
		const buf = _amEnsureJsErrorBuffer();
		buf.push(rec);
		if (buf.length > 2000) buf.splice(0, buf.length - 2000);

		_amPushUiLog({ ...rec, channel: "js" });
	} catch (e) {}
}

_amWin._amPushJsError = _amPushJsError;
_amWin._amPushJSError = _amPushJsError;

function _amPushAnyJsError(/** @type {AM2WebDebugRecord} */ rec) {
	try {
		const fn =
			typeof _amWin._amPushJSError === "function"
				? _amWin._amPushJSError
				: typeof _amWin._amPushJsError === "function"
					? _amWin._amPushJsError
					: null;
		if (fn) fn(rec);
	} catch {}
}

function _amFormatHeaders(/** @type {AM2Hdr} */ h) {
	try {
		const out = /** @type {Record<string, string>} */ ({});
		if (!h) return out;
		if (typeof h.forEach === "function") {
			h.forEach((/** @type {string} */ v, /** @type {string} */ k) => {
				out[String(k)] = String(v);
			});
			return out;
		}
		if (typeof h === "object") {
			for (const [k, v] of Object.entries(h)) out[String(k)] = String(v);
		}
		return out;
	} catch {
		return /** @type {Record<string, string>} */ ({});
	}
}

function _dbgModal(
	/** @type {AM2Str} */ title,
	/** @type {AM2Str} */ detailsText,
	/** @type {AM2MaybeN} */ notify,
) {
	try {
		const overlay = document.createElement("div");
		overlay.style.position = "fixed";
		overlay.style.left = "0";
		overlay.style.top = "0";
		overlay.style.right = "0";
		overlay.style.bottom = "0";
		overlay.style.background = "rgba(0,0,0,0.55)";
		overlay.style.display = "flex";
		overlay.style.alignItems = "center";
		overlay.style.justifyContent = "center";
		overlay.style.zIndex = "10000";

		const box = document.createElement("div");
		box.className = "modalBox";
		box.style.background = "#1b2230";
		box.style.border = "1px solid rgba(255,255,255,0.15)";
		box.style.borderRadius = "12px";
		box.style.padding = "16px";
		box.style.minWidth = "340px";
		box.style.maxWidth = "760px";
		box.style.color = "#fff";
		box.style.boxShadow = "0 10px 30px rgba(0,0,0,0.35)";

		const t = document.createElement("div");
		t.className = "subTitle";
		t.textContent = String(title || "Debug");
		box.appendChild(t);

		const pre = document.createElement("pre");
		pre.style.whiteSpace = "pre-wrap";
		pre.style.wordBreak = "break-word";
		pre.style.maxHeight = "360px";
		pre.style.overflow = "auto";
		pre.style.border = "1px solid rgba(255,255,255,0.08)";
		pre.style.borderRadius = "10px";
		pre.style.padding = "10px";
		pre.style.marginTop = "10px";
		pre.textContent = String(detailsText || "");
		box.appendChild(pre);

		const row = document.createElement("div");
		row.className = "buttonRow";
		row.style.gap = "8px";
		row.style.marginTop = "12px";

		const closeBtn = document.createElement("button");
		closeBtn.className = "btn";
		closeBtn.textContent = "Close";

		const copyBtn = document.createElement("button");
		copyBtn.className = "btn";
		copyBtn.textContent = "Copy";

		closeBtn.addEventListener("click", () => {
			try {
				document.body.removeChild(overlay);
			} catch {}
		});
		overlay.addEventListener("click", (ev) => {
			if (ev.target === overlay) {
				try {
					document.body.removeChild(overlay);
				} catch {}
			}
		});
		copyBtn.addEventListener("click", async () => {
			try {
				if (navigator.clipboard && navigator.clipboard.writeText) {
					await navigator.clipboard.writeText(String(detailsText || ""));
					if (typeof notify === "function") notify("Copied.");
					return;
				}
			} catch {
				// ignore
			}
			if (typeof notify === "function") notify("Copy failed.");
		});

		row.appendChild(copyBtn);
		row.appendChild(closeBtn);
		box.appendChild(row);

		overlay.appendChild(box);
		document.body.appendChild(overlay);
	} catch {
		// ignore
	}
}

function _amInstallDebugFetchCapture(/** @type {AM2MaybeN} */ notify) {
	if (_amWin.__AM_FETCH_CAPTURE_INSTALLED__) return;
	_amWin.__AM_FETCH_CAPTURE_INSTALLED__ = true;
	const orig = window.fetch;
	if (typeof orig !== "function") return;

	window.fetch = async (input, init) => {
		const ts = new Date().toISOString();
		let url = "";
		let method = "GET";
		let reqHeaders = /** @type {Record<string, string>} */ ({});
		let reqBody = null;
		try {
			if (typeof input === "string") url = input;
			else if (input && typeof input === "object" && "url" in input)
				url = String(input.url || "");
			if (init && typeof init === "object") {
				method = init.method ? String(init.method) : method;
				reqHeaders = _amFormatHeaders(init.headers);
				if (typeof init.body === "string") reqBody = init.body.slice(0, 4000);
			} else if (input && typeof input === "object" && "method" in input) {
				method = input.method ? String(input.method) : method;
			}
		} catch {
			// ignore
		}

		let stack = null;
		try {
			stack = String(new Error().stack || "");
		} catch {
			stack = null;
		}

		try {
			const r = await orig(input, init);
			if (r && r.ok) return r;

			const status = r && typeof r.status === "number" ? r.status : 0;
			const statusText =
				r && typeof r.statusText === "string" ? r.statusText : "";
			const respHeaders = r && r.headers ? _amFormatHeaders(r.headers) : {};

			let respText = "";
			try {
				const c = r && typeof r.clone === "function" ? r.clone() : null;
				if (c) respText = (await c.text()).slice(0, 8000);
			} catch {
				respText = "";
			}

			const rec = /** @type {AM2WebDebugRecord & AM2JsonObject} */ ({
				ts,
				channel: "http",
				kind: "response_not_ok",
				method,
				url,
				status,
				status_text: statusText,
				request_headers: reqHeaders,
				request_body: reqBody,
				response_headers: respHeaders,
				response_text: (respText || "").trim(),
				stack,
			});
			rec.message = `${method} ${url} -> ${status} ${statusText}`.trim();
			_amPushUiLog(rec);

			if (typeof notify === "function")
				notify(`HTTP ${status} ${statusText}`.trim());
			_dbgModal(
				`HTTP ${status} ${statusText}`.trim(),
				JSON.stringify(rec, null, 2),
				notify,
			);
			return r;
		} catch (e) {
			const msg =
				e && typeof e === "object" && "message" in e
					? String(e.message)
					: String(e);
			const rec = {
				ts,
				channel: "http",
				kind: "fetch_exception",
				method,
				url,
				message: msg,
				request_headers: reqHeaders,
				request_body: reqBody,
				stack,
			};
			_amPushUiLog(rec);
			if (typeof notify === "function") notify("HTTP request failed.");
			_dbgModal("HTTP request failed", JSON.stringify(rec, null, 2), notify);
			throw e;
		}
	};
}

window.addEventListener("unhandledrejection", (ev) => {
	const r = ev ? ev.reason : null;
	const isErr = r && typeof r === "object" && "stack" in r;
	const msg =
		r && typeof r === "object" && "message" in r
			? String(r.message)
			: String(r ?? "");
	_amPushAnyJsError({
		ts: new Date().toISOString(),
		kind: "unhandledrejection",
		message: msg,
		stack: isErr ? String(r.stack || "") : null,
		source: null,
		line: null,
		col: null,
	});
});

window.onerror = (msg, src, line, col, err) => {
	const e = err && typeof err === "object" ? err : null;
	_amPushAnyJsError({
		ts: new Date().toISOString(),
		kind: "error",
		message: String(msg ?? ""),
		stack: e && e.stack ? String(e.stack) : null,
		source: src ? String(src) : null,
		line: typeof line === "number" ? line : null,
		col: typeof col === "number" ? col : null,
	});
	return false;
};
(async () => {
	const API = /** @type {AM2WebApi} */ ({
		async _readErrorDetail(/** @type {Response} */ r) {
			const status = r && typeof r.status === "number" ? r.status : 0;
			let raw = "";
			try {
				raw = (await r.text()).slice(0, 800);
			} catch {}
			raw = (raw || "").trim();
			if (!raw) return `${status}`;
			try {
				const obj = JSON.parse(raw);
				if (obj && typeof obj === "object" && "detail" in obj) {
					const d = obj.detail;
					if (typeof d === "string") return `${status} ${d}`;
					return `${status} ${JSON.stringify(d)}`;
				}
			} catch {}
			return `${status} ${raw}`;
		},
		async getJson(/** @type {string} */ path) {
			const r = await fetch(path, { headers: { Accept: "application/json" } });
			if (!r.ok) {
				const d = await API._readErrorDetail(r);
				throw new Error(`GET ${path} -> ${d}`);
			}
			return await r.json();
		},
		async sendJson(
			/** @type {AM2Str} */ method,
			/** @type {AM2Str} */ path,
			/** @type {AM2MaybeJ} */ body,
		) {
			const r = await fetch(path, {
				method,
				headers: {
					"Content-Type": "application/json",
					Accept: "application/json",
				},
				body: body === undefined ? undefined : JSON.stringify(body),
			});
			if (!r.ok) {
				const d = await API._readErrorDetail(r);
				throw new Error(`${method} ${path} -> ${d}`);
			}
			const ct = r.headers.get("content-type") || "";
			if (ct.includes("application/json")) return await r.json();
			return { ok: true };
		},
	});

	/** @type {(tag: string,
	 * attrs?: AM2WebElAttrs | null,
	 * children?: AM2WebChild[] | null,
	 * ) => AM2WebUiElement} */
	function el(tag, attrs, children) {
		const node = document.createElement(tag);
		if (attrs) {
			for (const [k, v] of Object.entries(attrs)) {
				if (k === "class") node.className = String(v);
				else if (k === "text") node.textContent = String(v);
				else if (k.startsWith("on") && typeof v === "function")
					node.addEventListener(k.slice(2), v);
				else node.setAttribute(k, String(v));
			}
		}
		(children || []).forEach((/** @type {AM2WebChild} */ c) => {
			node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
		});
		return /** @type {AM2WebUiElement} */ (node);
	}

	function clear(/** @type {Node | null} */ node) {
		if (!node) return;
		while (node.firstChild) node.removeChild(node.firstChild);
	}

	/** @type {Promise<AM2WebAppDragdropBindingsModule> | null} */
	let _amStepRowDragdropBindingsPromise = null;

	function _amLoadStepRowDragdropBindings() {
		if (!_amStepRowDragdropBindingsPromise) {
			_amStepRowDragdropBindingsPromise =
				/** @type {Promise<AM2WebAppDragdropBindingsModule>} */ (
					new Function("p", "return import(p)")(
						`${_amUiAssetsBaseUrl}app_dragdrop_bindings.js`,
					)
				);
		}
		return _amStepRowDragdropBindingsPromise;
	}

	function fmtTs(/** @type {AM2JsonValue | undefined} */ v) {
		if (typeof v !== "number") return String(v ?? "");
		if (v > 1e12) v = Math.floor(v / 1000);
		const d = new Date(v * 1000);
		if (isNaN(d.getTime())) return String(v);
		return d.toLocaleString();
	}

	function fpKeyForBook(/** @type {AM2Book} */ book) {
		if (book && typeof book === "object") {
			if (typeof book.fingerprint === "string" && book.fingerprint)
				return book.fingerprint;
			if (typeof book.fp === "string" && book.fp) return book.fp;
			const meta = asObj(book.meta);
			if (meta && typeof meta.fingerprint === "string" && meta.fingerprint)
				return meta.fingerprint;
			if (typeof book.rel_path === "string" && book.rel_path)
				return book.rel_path;
			if (typeof book.path === "string" && book.path) return book.path;
		}
		return "";
	}

	async function renderStatList(/** @type {AM2Content} */ content) {
		const box = el("div", { class: "statList" });
		const src = content.source;
		const data =
			src && src.type === "api" && typeof src.path === "string"
				? await API.getJson(src.path)
				: {};
		for (const f of content.fields || []) {
			const key = f.key;
			let value = key && data && typeof data === "object" ? data[key] : "";
			if (key && key.endsWith("_ts")) value = fmtTs(value);
			box.appendChild(
				el("div", { class: "statRow" }, [
					el("div", { class: "statLabel", text: f.label || key }),
					el("div", {
						class: "statValue",
						text: value === undefined ? "" : String(value),
					}),
				]),
			);
		}
		return box;
	}

	async function renderTable(/** @type {AM2Table} */ content) {
		const src = content.source;
		const data =
			src && src.type === "api" && typeof src.path === "string"
				? await API.getJson(src.path)
				: { items: [] };
		const items = /** @type {AM2Item[]} */ (
			Array.isArray(data.items) ? data.items : []
		);
		const cols = Array.isArray(content.columns) ? content.columns : [];
		const table = el("table", { class: "table" });
		const thead = el("thead");
		const trh = el("tr");
		cols.forEach((/** @type {{ header?: string, key?: string }} */ c) => {
			trh.appendChild(el("th", { text: c.header || c.key }));
		});
		thead.appendChild(trh);
		table.appendChild(thead);
		const tbody = el("tbody");
		items.forEach((/** @type {AM2JsonObject} */ row) => {
			const tr = el("tr");
			cols.forEach((/** @type {AM2WebTableColumn} */ c) => {
				const key = c.key;
				let v = key && row ? row[key] : "";
				if (key && key.endsWith("_ts")) v = fmtTs(v);
				tr.appendChild(el("td", { text: v === undefined ? "" : String(v) }));
			});
			tbody.appendChild(tr);
		});
		table.appendChild(tbody);
		return el("div", { class: "tableWrap" }, [table]);
	}

	async function renderButtonRow(
		/** @type {AM2Content} */ content,
		/** @type {AM2N} */ notify,
	) {
		const wrap = el("div", { class: "buttonRow" });
		(Array.isArray(content.buttons) ? content.buttons : []).forEach(
			(/** @type {AM2Btn} */ b) => {
				const btn = el("button", { class: "btn", text: b.label || "Action" });
				btn.addEventListener("click", () => {
					if (
						b &&
						b.action &&
						b.action.type === "download" &&
						typeof b.action.href === "string"
					) {
						window.location.href = b.action.href;
					}
				});
				wrap.appendChild(btn);
			},
		);
		return wrap;
	}

	async function renderJsonEditor(
		/** @type {AM2Content} */ content,
		/** @type {AM2N} */ notify,
	) {
		const src = content.source;
		const data =
			src && src.type === "api" && typeof src.path === "string"
				? await API.getJson(src.path)
				: { data: {}, info: "" };
		const textarea = el("textarea", { class: "jsonEditor" });
		textarea.value = JSON.stringify(data.data || {}, null, 2) + "\n";
		const info = el("div", {
			class: "hint",
			text: `Source: ${data.info || ""}`,
		});

		const saveBtn = el("button", { class: "btn", text: "Save" });
		saveBtn.addEventListener("click", async () => {
			try {
				const payload = JSON.parse(textarea.value || "{}");
				const a = content.save_action || {};
				if (a.type !== "api" || typeof a.path !== "string") {
					throw new Error("save_action must be api");
				}
				await API.sendJson((a.method || "PUT").toUpperCase(), a.path, payload);
				notify("Saved.");
			} catch (e) {
				notify(String(e));
			}
		});

		return el("div", { class: "jsonEditorWrap" }, [
			info,
			textarea,
			el("div", { class: "buttonRow" }, [saveBtn]),
		]);
	}

	async function renderYamlEditor(
		/** @type {AM2Content} */ content,
		/** @type {AM2N} */ notify,
	) {
		const info = el("div", { class: "hint", text: "" });
		const textarea = el("textarea", { class: "jsonEditor" }); // reuse styling
		const saveBtn = el("button", { class: "btn", text: "Save" });

		async function load() {
			try {
				const src = content.source || {};
				if (src.type !== "api" || typeof src.path !== "string") {
					throw new Error("source must be api");
				}
				const data = await API.getJson(src.path);
				if (data && typeof data.info === "string")
					info.textContent = `Source: ${data.info}`;
				textarea.value = data && typeof data.yaml === "string" ? data.yaml : "";
				const yamlText = String(textarea.value || "");
				if (!yamlText.endsWith("\n")) textarea.value = `${yamlText}\n`;
			} catch (e) {
				info.textContent = String(e);
			}
		}

		saveBtn.addEventListener("click", async () => {
			try {
				const a = content.save_action || {};
				if (a.type !== "api" || typeof a.path !== "string") {
					throw new Error("save_action must be api");
				}
				await API.sendJson((a.method || "PUT").toUpperCase(), a.path, {
					yaml: String(textarea.value || ""),
				});
				notify("Saved.");
				await load();
			} catch (e) {
				notify(String(e));
			}
		});

		await load();
		return el("div", { class: "jsonEditorWrap" }, [
			info,
			textarea,
			el("div", { class: "buttonRow" }, [saveBtn]),
		]);
	}

	async function renderLogStream(
		/** @type {AM2Content} */ content,
		/** @type {AM2N} */ notify,
	) {
		const surface = Reflect.get(window, "AMWebLogStreamSurface");
		if (!surface || typeof surface.render !== "function") {
			throw new Error("AMWebLogStreamSurface.render is not available");
		}
		return await surface.render(content, notify, { API, el, clear });
	}

	async function _amGetAppDebugSurface() {
		const surface = Reflect.get(window, "AMWebAppDebugSurface");
		if (!surface || typeof surface !== "object") {
			throw new Error("AMWebAppDebugSurface is not available");
		}
		return surface;
	}

	async function renderJsErrorFeed(
		/** @type {AM2Content} */ content,
		/** @type {AM2N} */ notify,
	) {
		const surface = await _amGetAppDebugSurface();
		if (typeof surface.renderJsErrorFeed !== "function") {
			throw new Error(
				"AMWebAppDebugSurface.renderJsErrorFeed is not available",
			);
		}
		return await surface.renderJsErrorFeed(content, notify, {
			el,
			clear,
			ensureJsErrorBuffer: _amEnsureJsErrorBuffer,
		});
	}

	async function renderUiDebugFeed(
		/** @type {AM2Content} */ content,
		/** @type {AM2N} */ notify,
	) {
		const surface = await _amGetAppDebugSurface();
		if (typeof surface.renderUiDebugFeed !== "function") {
			throw new Error(
				"AMWebAppDebugSurface.renderUiDebugFeed is not available",
			);
		}
		return await surface.renderUiDebugFeed(content, notify, {
			el,
			clear,
			ensureUiLogBuffer: _amEnsureUiLogBuffer,
			showModal: _dbgModal,
		});
	}

	async function renderJobsLogViewer(
		/** @type {AM2Content} */ content,
		/** @type {AM2N} */ notify,
	) {
		const surface = Reflect.get(window, "AMWebJobsBrowserSurface");
		if (!surface || typeof surface.render !== "function") {
			throw new Error("AMWebJobsBrowserSurface.render is not available");
		}
		return await surface.render(content, notify, { API, el, clear });
	}

	async function renderPluginManager(
		/** @type {AM2Upload} */ content,
		/** @type {AM2N} */ notify,
	) {
		const wrap = el("div");
		const header = el("div", { class: "row" });
		const refreshBtn = el("button", { class: "btn", text: "Refresh" });
		header.appendChild(refreshBtn);
		const up = el("input", { type: "file" });
		up.multiple = true;
		up.setAttribute("webkitdirectory", "");
		up.setAttribute("directory", "");
		header.appendChild(up);
		const uploadBtn = el("button", { class: "btn", text: "Upload .zip" });
		header.appendChild(uploadBtn);
		wrap.appendChild(header);

		const tableBox = el("div");
		wrap.appendChild(tableBox);

		async function load() {
			tableBox.innerHTML = "";
			let data;
			try {
				data = await API.getJson(content.source?.path || "/api/plugins");
			} catch (e) {
				tableBox.appendChild(el("div", { class: "hint", text: String(e) }));
				return;
			}
			const items = /** @type {AM2UploadItem[]} */ (
				Array.isArray(data.items) ? data.items : []
			);
			const table = el("table", { class: "table" });
			const thead = el("thead");
			const trh = el("tr");
			["name", "version", "source", "enabled", "interfaces", "actions"].forEach(
				(/** @type {string} */ h) => {
					trh.appendChild(el("th", { text: h }));
				},
			);
			thead.appendChild(trh);
			table.appendChild(thead);
			const tbody = el("tbody");
			for (const p of items) {
				const tr = el("tr");
				tr.appendChild(el("td", { text: String(p.name || "") }));
				tr.appendChild(el("td", { text: String(p.version || "") }));
				tr.appendChild(el("td", { text: String(p.source || "") }));
				tr.appendChild(el("td", { text: String(!!p.enabled) }));
				tr.appendChild(
					el("td", {
						text: Array.isArray(p.interfaces) ? p.interfaces.join(", ") : "",
					}),
				);
				const actions = el("td");
				const enBtn = el("button", {
					class: "btn",
					text: p.enabled ? "Disable" : "Enable",
				});
				enBtn.addEventListener("click", async () => {
					try {
						await API.sendJson(
							"POST",
							`/api/plugins/${encodeURIComponent(String(p.name || ""))}/${
								p.enabled ? "disable" : "enable"
							}`,
							{},
						);
						await load();
					} catch (e) {
						notify(String(e));
					}
				});
				const delBtn = el("button", { class: "btn danger", text: "Delete" });
				if (p.source !== "user") {
					delBtn.disabled = true;
				} else {
					delBtn.addEventListener("click", async () => {
						if (!confirm(`Delete plugin '${p.name}'?`)) return;
						try {
							await API.sendJson(
								"DELETE",
								`/api/plugins/${encodeURIComponent(String(p.name || ""))}`,
								undefined,
							);
							await load();
						} catch (e) {
							notify(String(e));
						}
					});
				}
				actions.appendChild(enBtn);
				actions.appendChild(delBtn);
				tr.appendChild(actions);
				tbody.appendChild(tr);
			}
			table.appendChild(tbody);
			tableBox.appendChild(table);
		}

		refreshBtn.addEventListener("click", load);
		uploadBtn.addEventListener("click", async () => {
			if (!up.files || !up.files[0]) {
				notify("Select a zip file.");
				return;
			}
			const fd = new FormData();
			fd.append("file", up.files[0], up.files[0].name);
			try {
				const r = await fetch(content.upload?.path || "/api/plugins/upload", {
					method: "POST",
					body: fd,
				});
				if (!r.ok) throw new Error(`Upload failed: ${r.status}`);
				notify("Uploaded.");
				up.value = "";
				await load();
			} catch (e) {
				notify(String(e));
			}
		});

		await load();
		return wrap;
	}

	async function renderStageManager(
		/** @type {AM2Stage} */ content,
		/** @type {AM2N} */ notify,
	) {
		const wrap = el("div");
		const header = el("div", { class: "row" });
		const refreshBtn = el("button", { class: "btn", text: "Refresh" });
		header.appendChild(refreshBtn);
		const up = el("input", { type: "file" });
		up.multiple = true;
		up.setAttribute("webkitdirectory", "");
		up.setAttribute("directory", "");
		header.appendChild(up);
		const uploadBtn = el("button", { class: "btn", text: "Upload" });
		header.appendChild(uploadBtn);
		wrap.appendChild(header);

		const info = el("div", { class: "hint" });
		wrap.appendChild(info);

		const tableBox = el("div");
		wrap.appendChild(tableBox);

		async function load() {
			tableBox.innerHTML = "";
			let data;
			try {
				data = await API.getJson(content.list_path || "/api/stage");
			} catch (e) {
				tableBox.appendChild(el("div", { class: "hint", text: String(e) }));
				return;
			}
			if (data.dir) {
				info.textContent = data.dir ? `Dir: ${data.dir}` : "";
				info.style.display = "block";
			} else {
				info.textContent = "";
				info.style.display = "none";
			}
			const items = /** @type {AM2UploadItem[]} */ (
				Array.isArray(data.items) ? data.items : []
			);
			const table = el("table", { class: "table" });
			const thead = el("thead");
			const trh = el("tr");
			["name", "size", "mtime_ts", "actions"].forEach(
				(/** @type {string} */ h) => {
					trh.appendChild(el("th", { text: h }));
				},
			);
			thead.appendChild(trh);
			table.appendChild(thead);
			const tbody = el("tbody");
			for (const f of items) {
				const tr = el("tr");
				tr.appendChild(el("td", { text: f.name || "" }));
				tr.appendChild(el("td", { text: String(f.size || 0) }));
				tr.appendChild(el("td", { text: fmtTs(f.mtime_ts) }));
				const actions = el("td");
				const delBtn = el("button", { class: "btn danger", text: "Delete" });
				delBtn.addEventListener("click", async () => {
					if (!confirm(`Delete '${f.name}'?`)) return;
					try {
						await API.sendJson(
							"DELETE",
							`/api/stage/${encodeURIComponent(String(f.name || ""))}`,
							undefined,
						);
						await load();
					} catch (e) {
						notify(String(e));
					}
				});
				actions.appendChild(delBtn);
				tr.appendChild(actions);
				tbody.appendChild(tr);
			}
			table.appendChild(tbody);
			tableBox.appendChild(table);
		}

		refreshBtn.addEventListener("click", load);
		uploadBtn.addEventListener("click", async () => {
			if (!up.files || up.files.length === 0) {
				notify("Select files or a directory.");
				return;
			}
			const fd = new FormData();
			for (const f of Array.from(up.files || [])) {
				const rel =
					f.webkitRelativePath && f.webkitRelativePath.length > 0
						? f.webkitRelativePath
						: f.name;
				fd.append("files", f, f.name);
				fd.append("relpaths", rel);
			}
			try {
				const r = await fetch(content.upload_path || "/api/stage/upload", {
					method: "POST",
					body: fd,
				});
				if (!r.ok) throw new Error(`Upload failed: ${r.status}`);
				notify("Uploaded.");
				up.value = "";
				await load();
			} catch (e) {
				notify(String(e));
			}
		});

		await load();
		return wrap;
	}

	async function renderAmConfig(
		/** @type {AM2Content} */ content,
		/** @type {AM2N} */ notify,
	) {
		const wrap = el("div");

		const BASIC_FIELDS = [
			{ key: "web.host", label: "Web host" },
			{ key: "web.port", label: "Web port" },
			{ key: "web.upload_dir", label: "Web upload dir" },
			{ key: "inbox_dir", label: "Inbox dir" },
			{ key: "outbox_dir", label: "Outbox dir" },
			{ key: "stage_dir", label: "Stage dir" },
			{ key: "logging.level", label: "Logging level" },
		];

		function formatValue(
			/** @type {AM2JsonValue | undefined} */ v,
			/** @type {boolean} */ pretty,
		) {
			if (v === null) return "null";
			if (v === undefined) return "";
			try {
				if (typeof v === "string") return v;
				if (typeof v === "number") return String(v);
				if (typeof v === "boolean") return v ? "true" : "false";
				if (typeof v === "object")
					return JSON.stringify(v, null, pretty ? 2 : 0);
				return String(v);
			} catch {
				return String(v);
			}
		}

		function parseInputValue(/** @type {string | null | undefined} */ raw) {
			const text = String(raw || "");
			try {
				return JSON.parse(text);
			} catch {
				return text;
			}
		}

		function getEntry(
			/** @type {AM2Book} */ snap,
			/** @type {string} */ keyPath,
		) {
			if (!snap || typeof snap !== "object" || Array.isArray(snap))
				return { value: void 0, source: "" };
			const e = snap[keyPath];
			if (!e || typeof e !== "object" || Array.isArray(e))
				return { value: void 0, source: "" };
			const entry = /** @type {{ value?: AM2JsonValue, source?: string }} */ (
				e
			);
			return { value: entry.value, source: String(entry.source || "") };
		}

		async function apiSet(
			/** @type {string} */ keyPath,
			/** @type {string} */ rawValue,
		) {
			const value = parseInputValue(rawValue);
			await API.sendJson("POST", "/api/am/config/set", {
				key_path: keyPath,
				value,
			});
		}

		async function apiReset(/** @type {string} */ keyPath) {
			await API.sendJson("POST", "/api/am/config/unset", { key_path: keyPath });
		}

		function sourceBadge(/** @type {string} */ source) {
			const cls =
				source === "user_config" ? "badge badgeUser" : "badge badgeOther";
			const text = source || "(unknown)";
			return el("span", { class: cls, text });
		}

		function buildRow(
			/** @type {AM2Str} */ keyPath,
			/** @type {AM2Str} */ label,
			/** @type {AM2Entry} */ entry,
			/** @type {AM2AsyncVoid} */ done,
		) {
			const valueText = formatValue(entry.value, false);
			const valueBox = el("div", { class: "configValue", text: valueText });

			const sourceBox = el("div", { class: "configSource" }, [
				sourceBadge(entry.source),
			]);

			const input = el("input", {
				class: "input",
				placeholder: "new value (JSON or string)",
			});

			const setBtn = el("button", { class: "btnPrimary", text: "Set" });
			const resetBtn = el("button", { class: "btn", text: "Reset" });

			setBtn.addEventListener("click", async () => {
				try {
					await apiSet(keyPath, String(input.value || ""));
					notify("Saved.");
					input.value = "";
					await done();
				} catch (e) {
					notify(String(e));
				}
			});

			resetBtn.addEventListener("click", async () => {
				try {
					await apiReset(keyPath);
					notify("Reset.");
					input.value = "";
					await done();
				} catch (e) {
					notify(String(e));
				}
			});

			const actions = el("div", { class: "toolbar" }, [setBtn, resetBtn]);

			const left = el("div", { class: "configColKey" }, [
				el("div", { class: "configKey", text: keyPath }),
				el("div", { class: "configLabel", text: label || "" }),
			]);

			const mid = el("div", { class: "configColValue" }, [valueBox, sourceBox]);
			const right = el("div", { class: "configColEdit" }, [input, actions]);

			return el("div", { class: "configRow" }, [left, mid, right]);
		}

		function groupByPrefix(/** @type {string[]} */ keys) {
			const out = /** @type {Record<string, string[]>} */ ({});
			for (const k of keys) {
				const idx = k.indexOf(".");
				const prefix = idx > 0 ? k.slice(0, idx) : "(root)";
				if (!out[prefix]) out[prefix] = [];
				out[prefix].push(k);
			}
			for (const p of Object.keys(out)) out[p].sort();
			return out;
		}

		const topRow = el("div", { class: "toolbar" });
		const refreshBtn = el("button", { class: "btn", text: "Refresh" });
		topRow.appendChild(refreshBtn);
		wrap.appendChild(topRow);

		const basicTitle = el("div", {
			class: "subTitle",
			text: "Basic configuration",
		});
		const basicBox = el("div", { class: "configBox" });
		wrap.appendChild(basicTitle);
		wrap.appendChild(basicBox);

		const advTitleRow = el("div", { class: "toolbar" }, [
			el("div", { class: "subTitle", text: "Advanced configuration" }),
		]);
		wrap.appendChild(advTitleRow);

		const advControls = el("div", { class: "toolbar" });
		const searchIn = el("input", {
			class: "input",
			placeholder: "Search key_path",
		});
		const overridesOnly = el("input", { type: "checkbox" });
		const overridesLabel = el("label", { class: "toggle" }, [
			overridesOnly,
			el("span", { text: "Show overrides only" }),
		]);
		advControls.appendChild(searchIn);
		advControls.appendChild(overridesLabel);
		wrap.appendChild(advControls);

		const advBox = el("div", { class: "configBox" });
		wrap.appendChild(advBox);

		const rawTitle = el("div", {
			class: "subTitle",
			text: "Raw effective_snapshot",
		});
		const rawPre = el("pre", { class: "codeBlock", text: "" });
		const rawDetails = el("details", { class: "configDetails" }, [
			el("summary", { text: "Show raw snapshot" }),
			rawPre,
		]);
		wrap.appendChild(rawDetails);

		let lastSnap = /** @type {AM2JsonObject} */ ({});

		function renderBasic(/** @type {AM2JsonObject} */ snap) {
			clear(basicBox);
			const hint = el("div", {
				class: "hint",
				text: "Set writes a user override. Reset removes the user override (inherit).",
			});
			basicBox.appendChild(hint);

			for (const f of BASIC_FIELDS) {
				const entry = getEntry(snap, f.key);
				basicBox.appendChild(
					buildRow(f.key, f.label, entry, async () => {
						await load();
					}),
				);
			}
		}

		function renderAdvanced(/** @type {AM2JsonObject} */ snap) {
			clear(advBox);

			const allKeys = Object.keys(snap || {}).sort();
			const query = (searchIn.value || "").trim().toLowerCase();
			const onlyOverrides = !!overridesOnly.checked;

			let keys = allKeys;
			if (query) {
				keys = keys.filter((k) => k.toLowerCase().includes(query));
			}
			if (onlyOverrides) {
				keys = keys.filter((k) => {
					const e = getEntry(snap, k);
					return e.source === "user_config";
				});
			}

			if (!keys.length) {
				advBox.appendChild(el("div", { class: "hint", text: "(no entries)" }));
				return;
			}

			const grouped = groupByPrefix(keys);
			const prefixes = Object.keys(grouped).sort();

			for (const prefix of prefixes) {
				const section = el("details", { class: "configGroup" });
				section.open = true;
				section.appendChild(el("summary", { text: prefix }));
				const body = el("div");
				for (const k of grouped[prefix]) {
					const e = getEntry(snap, k);
					body.appendChild(
						buildRow(k, "", e, async () => {
							await load();
						}),
					);
				}
				section.appendChild(body);
				advBox.appendChild(section);
			}
		}

		async function load() {
			const data = await API.getJson("/api/am/config");
			const snap = asObj(data && data.effective_snapshot) || undefined;
			if (!snap || typeof snap !== "object") {
				throw new Error("effective_snapshot must be an object");
			}
			lastSnap = snap;
			rawPre.textContent = JSON.stringify(snap, null, 2) + "\n";
			renderBasic(snap);
			renderAdvanced(snap);
		}

		refreshBtn.addEventListener("click", async () => {
			try {
				await load();
			} catch (e) {
				notify(String(e));
			}
		});

		searchIn.addEventListener("input", () => {
			try {
				renderAdvanced(lastSnap);
			} catch {
				/* ignore */
			}
		});

		overridesOnly.addEventListener("change", () => {
			try {
				renderAdvanced(lastSnap);
			} catch {
				/* ignore */
			}
		});

		await load();
		return wrap;
	}

	async function renderWizardManager(
		/** @type {AM2Content} */ content,
		/** @type {AM2N} */ notify,
	) {
		const root = el("div", { class: "wizardManager" });

		const header = el("div", { class: "toolbar" }, [
			el("button", { class: "btn", text: "Refresh" }),
			el("button", { class: "btn", text: "New wizard" }),
		]);

		const listPane = el("div", { class: "wizardList" });
		const detailPane = el("div", { class: "wizardDetail" });
		const editorPane = el("div", { class: "wizardEditor" });
		const yamlPane = el("div", { class: "wizardYaml" });

		const main = el("div", { class: "wizardGrid" }, [
			el("div", { class: "wizardCol" }, [listPane]),
			el("div", { class: "wizardColWide" }, [detailPane, editorPane, yamlPane]),
		]);

		root.appendChild(header);
		root.appendChild(main);

		let currentName = /** @type {string | null} */ (null);
		let currentModel = /** @type {AM2WizModel | null} */ (null);

		function setYamlText(/** @type {string} */ txt) {
			clear(yamlPane);
			yamlPane.appendChild(
				el("div", { class: "subTitle", text: "YAML preview" }),
			);
			yamlPane.appendChild(el("pre", { class: "codeBlock", text: txt || "" }));
		}

		async function refreshYamlPreview() {
			if (!currentModel) return;
			try {
				const r = await API.sendJson("POST", "/api/wizards/preview", {
					model: currentModel,
				});
				setYamlText(String(r.yaml || ""));
			} catch (e) {
				setYamlText("Preview failed: " + String(e));
			}
		}

		function renderStepEditor(/** @type {number} */ stepIndex) {
			clear(editorPane);
			if (!currentModel || !currentModel.wizard) return;

			const steps = currentModel.wizard.steps || [];
			const s = steps[stepIndex];
			if (!s) return;

			editorPane.appendChild(
				el("div", { class: "subTitle", text: `Step ${stepIndex + 1}` }),
			);

			const idIn = el("input", { class: "input", value: String(s.id || "") });
			const typeIn = el("input", {
				class: "input",
				value: String(s.type || ""),
			});
			const promptIn = el("input", {
				class: "input",
				value: String(s.prompt || s.label || ""),
			});

			const enabledIn = el("input", { type: "checkbox" });
			enabledIn.checked = s.enabled !== false;

			const tmplSel = el("select", { class: "input" });
			tmplSel.appendChild(el("option", { value: "", text: "(no template)" }));
			const wiz =
				currentModel && currentModel.wizard ? currentModel.wizard : null;
			const tmplMap =
				wiz &&
				wiz._ui &&
				wiz._ui.templates &&
				typeof wiz._ui.templates === "object"
					? wiz._ui.templates
					: {};
			Object.keys(tmplMap || {})
				.sort()
				.forEach((k) => {
					tmplSel.appendChild(el("option", { value: k, text: k }));
				});
			tmplSel.value = String(s.template || "");

			const defaultsTa = el("textarea", {
				class: "textarea",
				text: JSON.stringify(s.defaults || {}, null, 2),
			});
			const whenTa = el("textarea", {
				class: "textarea",
				text: s.when != null ? JSON.stringify(s.when, null, 2) : "",
			});

			const mkRow = (
				/** @type {string} */ label,
				/** @type {HTMLElement} */ inputEl,
			) =>
				el("div", { class: "formRow" }, [
					el("div", { class: "formLabel", text: label }),
					inputEl,
				]);

			editorPane.appendChild(mkRow("id", idIn));
			editorPane.appendChild(mkRow("type", typeIn));
			editorPane.appendChild(mkRow("prompt/label", promptIn));
			editorPane.appendChild(mkRow("enabled", enabledIn));
			editorPane.appendChild(mkRow("template", tmplSel));

			editorPane.appendChild(
				el("div", { class: "subTitle", text: "defaults (JSON)" }),
			);
			editorPane.appendChild(defaultsTa);
			editorPane.appendChild(
				el("div", { class: "subTitle", text: "when/conditions (JSON)" }),
			);
			editorPane.appendChild(whenTa);

			const tmplBar = el("div", { class: "toolbar" });
			const applyTmplBtn = el("button", {
				class: "btn",
				text: "Apply template",
			});
			const saveTmplBtn = el("button", {
				class: "btn",
				text: "Save as template",
			});
			tmplBar.appendChild(applyTmplBtn);
			tmplBar.appendChild(saveTmplBtn);
			editorPane.appendChild(tmplBar);

			idIn.addEventListener("input", () => {
				s.id = idIn.value;
				refreshYamlPreview();
			});
			typeIn.addEventListener("input", () => {
				s.type = typeIn.value;
				refreshYamlPreview();
			});
			promptIn.addEventListener("input", () => {
				s.prompt = promptIn.value;
				s.label = promptIn.value;
				refreshYamlPreview();
			});
			enabledIn.addEventListener("change", () => {
				s.enabled = !!enabledIn.checked;
				refreshYamlPreview();
			});
			tmplSel.addEventListener("change", () => {
				s.template = tmplSel.value || "";
				refreshYamlPreview();
			});

			function parseJsonOrEmpty(
				/** @type {string} */ txt,
				/** @type {string} */ label,
			) {
				const t = String(txt || "").trim();
				if (!t) return null;
				try {
					return JSON.parse(t);
				} catch (e) {
					throw new Error(`Invalid JSON for ${label}`);
				}
			}

			defaultsTa.addEventListener("input", () => {
				try {
					const v = parseJsonOrEmpty(
						String(defaultsTa.value || ""),
						"defaults",
					);
					s.defaults = v === null ? {} : v;
					refreshYamlPreview();
				} catch (e) {
					/* ignore while typing */
				}
			});
			whenTa.addEventListener("input", () => {
				try {
					const v = parseJsonOrEmpty(String(whenTa.value || ""), "when");
					if (v === null) delete s.when;
					else s.when = v;
					refreshYamlPreview();
				} catch (e) {
					/* ignore while typing */
				}
			});

			applyTmplBtn.addEventListener("click", () => {
				const key = tmplSel.value;
				if (!key) return;
				const tpl = /** @type {AM2JsonObject | null} */ (
					tmplMap && tmplMap[key] ? tmplMap[key] : null
				);
				if (!tpl) return;
				const stepRecord = /** @type {AM2JsonObject} */ (s);
				Object.keys(tpl).forEach((k) => {
					if (k === "id") return;
					stepRecord[k] = tpl[k];
				});
				// Refresh inputs from model
				renderStepEditor(stepIndex);
				refreshYamlPreview();
			});

			saveTmplBtn.addEventListener("click", () => {
				const key =
					(s.template && String(s.template).trim()) || prompt("Template name?");
				if (!key) return;
				const currentWizard = currentModel && currentModel.wizard;
				if (!currentWizard) return;
				currentWizard._ui = currentWizard._ui || {};
				currentWizard._ui.templates = currentWizard._ui.templates || {};
				const tpl = /** @type {AM2JsonObject} */ ({});
				const stepRecord = /** @type {AM2JsonObject} */ (s);
				Object.keys(s).forEach((k) => {
					if (k === "id") return;
					if (k === "_ui") return;
					tpl[k] = stepRecord[k];
				});
				currentWizard._ui.templates[key] = tpl;
				s.template = key;
				renderStepEditor(stepIndex);
				refreshYamlPreview();
			});

			const actions = el("div", { class: "toolbar" });
			const upBtn = el("button", { class: "btn", text: "Up" });
			const downBtn = el("button", { class: "btn", text: "Down" });
			const delBtn = el("button", { class: "btnDanger", text: "Delete step" });
			actions.appendChild(upBtn);
			actions.appendChild(downBtn);
			actions.appendChild(delBtn);
			editorPane.appendChild(actions);

			upBtn.addEventListener("click", () => {
				if (stepIndex <= 0) return;
				[steps[stepIndex - 1], steps[stepIndex]] = [
					steps[stepIndex],
					steps[stepIndex - 1],
				];
				renderDetail();
				renderStepEditor(stepIndex - 1);
				refreshYamlPreview();
			});
			downBtn.addEventListener("click", () => {
				if (stepIndex >= steps.length - 1) return;
				[steps[stepIndex + 1], steps[stepIndex]] = [
					steps[stepIndex],
					steps[stepIndex + 1],
				];
				renderDetail();
				renderStepEditor(stepIndex + 1);
				refreshYamlPreview();
			});
			delBtn.addEventListener("click", () => {
				steps.splice(stepIndex, 1);
				renderDetail();
				refreshYamlPreview();
			});
		}

		function renderDetail() {
			const dragdropBindingsPromise = _amLoadStepRowDragdropBindings();
			clear(detailPane);
			clear(editorPane);
			clear(yamlPane);

			if (!currentModel || !currentModel.wizard) {
				detailPane.appendChild(
					el("div", { class: "hint", text: "Select a wizard." }),
				);
				return;
			}

			const wiz = currentModel.wizard;

			detailPane.appendChild(el("div", { class: "subTitle", text: "Wizard" }));
			const nameIn = el("input", {
				class: "input",
				value: String(wiz.name || ""),
			});
			const descIn = el("textarea", {
				class: "textarea",
				text: String(wiz.description || ""),
			});

			const mkRow = (
				/** @type {string} */ label,
				/** @type {HTMLElement} */ inputEl,
			) =>
				el("div", { class: "formRow" }, [
					el("div", { class: "formLabel", text: label }),
					inputEl,
				]);

			detailPane.appendChild(mkRow("Display name", nameIn));
			detailPane.appendChild(mkRow("Description", descIn));

			const wizUi = /** @type {AM2WebWizardUiState} */ (wiz._ui || {});
			wiz._ui = wizUi;
			if (!wizUi.defaults_memory) wizUi.defaults_memory = {};
			const dmTa = el("textarea", {
				class: "textarea",
				text: JSON.stringify(wizUi.defaults_memory || {}, null, 2),
			});
			detailPane.appendChild(
				el("div", { class: "subTitle", text: "Defaults memory (JSON)" }),
			);
			detailPane.appendChild(dmTa);
			dmTa.addEventListener("input", () => {
				try {
					const t = String(dmTa.value || "").trim();
					wizUi.defaults_memory = t ? JSON.parse(t) : {};
					refreshYamlPreview();
				} catch (e) {}
			});

			nameIn.addEventListener("input", () => {
				wiz.name = nameIn.value;
				refreshYamlPreview();
			});
			descIn.addEventListener("input", () => {
				wiz.description = descIn.value;
				refreshYamlPreview();
			});

			const stepsBox = el("div", { class: "stepsBox" });
			stepsBox.appendChild(
				el("div", {
					class: "subTitle",
					text: `Steps (${(wiz.steps || []).length})`,
				}),
			);

			const addBtn = el("button", { class: "btn", text: "Add step" });
			addBtn.addEventListener("click", () => {
				wiz.steps = wiz.steps || [];
				wiz.steps.push({
					id: `step_${wiz.steps.length + 1}`,
					type: "text",
					prompt: "",
				});
				renderDetail();
				refreshYamlPreview();
			});
			stepsBox.appendChild(addBtn);

			(wiz.steps || []).forEach(
				(/** @type {AM2WebWizardStep} */ s, /** @type {number} */ idx) => {
					const label = `${s.id || "step_" + (idx + 1)} : ${s.type || "unknown"}${s.enabled === false ? " [disabled]" : ""}`;
					const row = el("div", { class: "stepRow", text: label });
					row.dataset.stepIndex = String(idx);
					row.draggable = true;
					row.addEventListener("click", () => renderStepEditor(idx));

					void dragdropBindingsPromise.then((dragdropBindings) => {
						dragdropBindings.bindStepRowDragdropHandlers(row, idx, wiz, {
							renderDetail,
							renderStepEditor,
							refreshYamlPreview,
						});
					});

					stepsBox.appendChild(row);
				},
			);

			detailPane.appendChild(stepsBox);

			const saveBar = el("div", { class: "toolbar" });
			const saveBtn = el("button", { class: "btnPrimary", text: "Save" });
			const delBtn = el("button", {
				class: "btnDanger",
				text: "Delete wizard",
			});
			saveBar.appendChild(saveBtn);
			saveBar.appendChild(delBtn);
			detailPane.appendChild(saveBar);

			saveBtn.addEventListener("click", async () => {
				if (!currentName) return;
				try {
					await API.sendJson("POST", "/api/wizards/validate", {
						model: currentModel,
					});

					await API.sendJson(
						"PUT",
						`/api/wizards/${encodeURIComponent(currentName)}`,
						{ model: currentModel },
					);
					notify(`Saved wizard: ${currentName}`);
					await loadList();
				} catch (e) {
					notify(`Save failed: ${String(e)}`);
				}
			});

			delBtn.addEventListener("click", async () => {
				if (!currentName) return;
				try {
					await API.sendJson(
						"DELETE",
						`/api/wizards/${encodeURIComponent(currentName)}`,
					);
					notify(`Deleted wizard: ${currentName}`);
					currentName = null;
					currentModel = null;
					await loadList();
					renderDetail();
				} catch (e) {
					notify(`Delete failed: ${String(e)}`);
				}
			});

			refreshYamlPreview();
		}

		async function loadDetail(/** @type {string} */ name) {
			currentName = name;
			try {
				const w = await API.getJson(`/api/wizards/${encodeURIComponent(name)}`);
				currentModel = /** @type {AM2WizModel | null} */ (asObj(w.model));
				if (!currentModel)
					currentModel = /** @type {AM2WizModel} */ ({
						wizard: { name, description: "", steps: [] },
					});
				renderDetail();
			} catch (e) {
				currentModel = null;
				clear(detailPane);
				detailPane.appendChild(el("div", { class: "error", text: String(e) }));
			}
		}

		async function loadList() {
			clear(listPane);
			listPane.appendChild(el("div", { class: "hint", text: "Loading..." }));
			const r = await API.getJson("/api/wizards");
			const items = /** @type {AM2WizItem[]} */ (
				Array.isArray(r.items) ? r.items : []
			);
			clear(listPane);

			items.forEach((/** @type {AM2WizItem} */ w) => {
				const wizName = (w && (w.name || w.filename || w.id || w.title)) || "";
				const count = (w && (w.step_count != null ? w.step_count : "?")) ?? "?";
				const row = el("div", {
					class: "wizardItem",
					text: `${wizName} (${count})`,
				});
				row.addEventListener("click", () => loadDetail(wizName));
				listPane.appendChild(row);
			});
		}

		header.children[0].addEventListener("click", () => loadList());
		header.children[1].addEventListener("click", async () => {
			const name = prompt("New wizard name (filename without .yaml):");
			if (!name) return;
			const yaml =
				'wizard:\n  name: "' +
				name +
				'"\n  description: ""\n  steps:\n    - id: step_1\n      type: text\n      prompt: ""\n';
			try {
				await API.sendJson("POST", "/api/wizards", { name: name, yaml: yaml });
				await loadList();
				await loadDetail(name);
			} catch (e) {
				notify(`Create failed: ${String(e)}`);
			}
		});

		await loadList();
		renderDetail();
		return root;
	}

	async function renderRootBrowser(
		/** @type {AM2Content} */ content,
		/** @type {AM2N} */ notify,
	) {
		const root = el("div", { class: "rootBrowser" });

		const header = el("div", { class: "row" });
		const rootsSel = el("select");
		const pathInp = el("input", {
			type: "text",
			value: ".",
			placeholder: "path",
		});
		const upBtn = el("button", { class: "btn", text: "Up" });
		const refreshBtn = el("button", { class: "btn", text: "Refresh" });
		header.appendChild(rootsSel);
		header.appendChild(pathInp);
		header.appendChild(upBtn);
		header.appendChild(refreshBtn);
		root.appendChild(header);

		const listBox = el("div", { class: "fileList" });
		root.appendChild(listBox);

		const wizRow = el("div", { class: "row" });
		const wizSel = el("select");
		const modeSel = el("select");
		modeSel.appendChild(
			el("option", { value: "per", text: "Job per selection" }),
		);
		modeSel.appendChild(
			el("option", { value: "batch", text: "Single batch job" }),
		);
		const runBtn = el("button", { class: "btn", text: "Run" });
		wizRow.appendChild(wizSel);
		wizRow.appendChild(modeSel);
		wizRow.appendChild(runBtn);
		root.appendChild(wizRow);

		const formBox = el("div", { class: "wizardForm" });
		root.appendChild(formBox);

		let currentRoot = "";
		let currentPath = ".";
		let selected = new Set();
		let wizardModel = null;

		async function loadRoots() {
			const data = await API.getJson("/api/roots");
			const items = /** @type {AM2WizItem[]} */ (
				Array.isArray(data.items) ? data.items : []
			);
			clear(rootsSel);
			items.forEach((/** @type {AM2WebRootItem} */ it) => {
				const id = String(it && (it.id ?? it.name ?? ""));
				const label = String(it && (it.label ?? it.name ?? it.id ?? ""));
				rootsSel.appendChild(el("option", { value: id, text: label }));
			});
			const first = items[0] || null;
			currentRoot = first ? (first.id ?? first.name ?? "") : "";
			rootsSel.value = currentRoot;
		}

		async function loadWizards() {
			const data = await API.getJson("/api/wizards");
			const items = /** @type {AM2WizItem[]} */ (
				Array.isArray(data.items) ? data.items : []
			);
			clear(wizSel);
			wizSel.appendChild(el("option", { value: "", text: "Select wizard" }));
			items.forEach((/** @type {AM2WizItem} */ it) => {
				const label = String(it.display_name || it.name || "");
				wizSel.appendChild(
					el("option", { value: String(it.name || ""), text: label }),
				);
			});
		}

		function normPath(/** @type {string} */ p) {
			p = String(p || ".").trim();
			if (!p) return ".";
			p = p.replace(/^\/+/, "");
			const parts = p
				.split("/")
				.filter((/** @type {string} */ x) => x && x !== ".");
			if (parts.some((/** @type {string} */ x) => x === ".."))
				throw new Error("invalid path");
			return parts.length ? parts.join("/") : ".";
		}

		async function loadDir() {
			if (!currentRoot) return;
			currentPath = normPath(String(pathInp.value || ""));
			pathInp.value = currentPath;
			selected = new Set();
			const url =
				`/api/fs/list?root=${encodeURIComponent(currentRoot)}&path=${encodeURIComponent(
					currentPath,
				)}` + "&recursive=0";
			const data = await API.getJson(url);
			const items = /** @type {AM2WebFsItem[]} */ (
				Array.isArray(data.items) ? data.items : []
			);
			items.sort(
				(/** @type {AM2WebFsItem} */ a, /** @type {AM2WebFsItem} */ b) => {
					const ad = a.is_dir ? 0 : 1;
					const bd = b.is_dir ? 0 : 1;
					if (ad !== bd) return ad - bd;
					return String(a.path).localeCompare(String(b.path));
				},
			);
			clear(listBox);

			const curRow = el("div", { class: "fileRow" });
			const curChk = el("input", { type: "checkbox" });
			curChk.addEventListener("change", () => {
				const key = currentPath;
				if (curChk.checked) selected.add(key);
				else selected.delete(key);
			});
			curRow.appendChild(curChk);
			curRow.appendChild(
				el("span", { class: "fileName", text: "[current directory]" }),
			);
			listBox.appendChild(curRow);

			items.forEach((/** @type {AM2WebFsItem} */ it) => {
				const row = el("div", { class: "fileRow" });
				const chk = el("input", { type: "checkbox" });
				chk.addEventListener("change", () => {
					if (chk.checked) selected.add(String(it.path || ""));
					else selected.delete(String(it.path || ""));
				});
				const name = String(it.path || "")
					.split("/")
					.pop();
				const nameEl = el("span", { class: "fileName", text: name });
				if (it.is_dir) {
					nameEl.classList.add("isDir");
					nameEl.style.cursor = "pointer";
					nameEl.addEventListener("click", async () => {
						pathInp.value = String(it.path || "");
						await loadDir();
					});
				}
				row.appendChild(chk);
				row.appendChild(nameEl);
				listBox.appendChild(row);
			});
		}

		async function loadWizardModel() {
			wizardModel = null;
			clear(formBox);
			const id = wizSel.value;
			if (!id) return;
			const data = await API.getJson(`/api/wizards/${encodeURIComponent(id)}`);
			wizardModel = /** @type {AM2WizModel | null} */ (
				asObj(data && data.model)
			);
			const wiz = /** @type {AM2WebWizardBody | null} */ (
				asObj(wizardModel && wizardModel.wizard)
			);
			const steps = wiz && Array.isArray(wiz.steps) ? wiz.steps : [];
			const title = wiz && wiz.name ? String(wiz.name) : id;
			formBox.appendChild(
				el("div", { class: "hint", text: `Wizard: ${title}` }),
			);
			steps.forEach((/** @type {AM2WebWizardStep} */ s) => {
				const sid = s.id || s.key || "";
				if (!sid) return;
				const st = String(s.type || "input");
				const row = el("div", { class: "formRow" });
				row.appendChild(el("div", { class: "formLabel", text: sid }));
				if (st === "text") {
					row.appendChild(
						el("div", { class: "hint", text: String(s.prompt || "") }),
					);
					formBox.appendChild(row);
					return;
				}
				if (st === "confirm") {
					const inp = el("input", { type: "checkbox" });
					inp.dataset.stepId = sid;
					row.appendChild(inp);
					row.appendChild(
						el("span", { class: "hint", text: String(s.prompt || "") }),
					);
					formBox.appendChild(row);
					return;
				}
				if (st === "choice" || st === "select") {
					const sel = el("select");
					sel.dataset.stepId = sid;
					(Array.isArray(s.options) ? s.options : []).forEach(
						(/** @type {AM2JsonValue} */ o) => {
							const obj = /** @type {AM2ValLabel | null} */ (asObj(o));
							const v = obj
								? String(obj.value !== undefined ? obj.value : "")
								: String(o);
							const lbl = obj
								? String(obj.label !== undefined ? obj.label : v)
								: String(o);
							sel.appendChild(el("option", { value: v, text: lbl }));
						},
					);
					row.appendChild(sel);
					formBox.appendChild(row);
					return;
				}
				const inp = el("input", { type: "text" });
				inp.dataset.stepId = sid;
				row.appendChild(inp);
				if (s.prompt)
					row.appendChild(
						el("span", { class: "hint", text: String(s.prompt) }),
					);
				formBox.appendChild(row);
			});
		}

		function collectPayload() {
			const payload = /** @type {AM2JsonObject} */ ({});
			Array.from(formBox.querySelectorAll("input,select")).forEach(
				(/** @type {Element} */ n) => {
					const field = /** @type {HTMLInputElement | HTMLSelectElement} */ (n);
					const sid = field.dataset.stepId;
					if (!sid) return;
					if (
						field.tagName.toLowerCase() === "input" &&
						field.getAttribute("type") === "checkbox"
					) {
						payload[sid] =
							field instanceof HTMLInputElement ? !!field.checked : false;
					} else {
						payload[sid] = field.value;
					}
				},
			);
			return payload;
		}

		rootsSel.addEventListener("change", async () => {
			currentRoot = String(rootsSel.value || "");
			pathInp.value = ".";
			await loadDir();
		});
		refreshBtn.addEventListener("click", () => loadDir());
		upBtn.addEventListener("click", async () => {
			const p = normPath(String(pathInp.value || ""));
			if (p === ".") return;
			const parts = p.split("/");
			parts.pop();
			pathInp.value = parts.length ? parts.join("/") : ".";
			await loadDir();
		});
		pathInp.addEventListener("keydown", (/** @type {KeyboardEvent} */ ev) => {
			if (ev.key === "Enter") loadDir();
		});
		wizSel.addEventListener("change", () => loadWizardModel());

		runBtn.addEventListener("click", async () => {
			try {
				const wid = wizSel.value;
				if (!wid) throw new Error("select a wizard");
				if (!selected.size) throw new Error("select at least one target");
				const paths = Array.from(selected.values());
				const payload = collectPayload();
				const mode = modeSel.value;
				const jobIds = /** @type {string[]} */ ([]);
				if (mode === "batch") {
					const body = {
						wizard_id: wid,
						targets: paths.map((p) => ({ root: currentRoot, path: p })),
						payload,
					};
					const r = await API.sendJson("POST", "/api/jobs/wizard", body);
					const jobId = String(r.job_id || "");
					await API.sendJson(
						"POST",
						`/api/jobs/${encodeURIComponent(jobId)}/run`,
						{},
					);
					jobIds.push(jobId);
				} else {
					for (const p of paths) {
						const body = {
							wizard_id: wid,
							target_root: currentRoot,
							target_path: p,
							payload,
						};
						const r = await API.sendJson("POST", "/api/jobs/wizard", body);
						const jobId = String(r.job_id || "");
						await API.sendJson(
							"POST",
							`/api/jobs/${encodeURIComponent(jobId)}/run`,
							{},
						);
						jobIds.push(jobId);
					}
				}
				notify(`Started: ${jobIds.join(", ")}`);
			} catch (e) {
				notify(String(e));
			}
		});

		await loadRoots();
		await loadWizards();
		await loadDir();
		return root;
	}

	const CONTENT_RENDERERS = {
		stat_list: renderStatList,
		table: renderTable,
		log_stream: renderLogStream,
		js_error_feed: renderJsErrorFeed,
		ui_debug_feed: renderUiDebugFeed,
		button_row: renderButtonRow,
		json_editor: renderJsonEditor,
		yaml_editor: renderYamlEditor,
		plugin_manager: renderPluginManager,
		stage_manager: renderStageManager,
		wizard_manager: renderWizardManager,
		root_browser: renderRootBrowser,
		am_config: renderAmConfig,
		jobs_log_viewer: renderJobsLogViewer,
	};

	async function renderContent(
		/** @type {AM2Content} */ content,
		/** @type {AM2N} */ notify,
	) {
		const contentType = typeof content.type === "string" ? content.type : "";
		const fn = Reflect.get(CONTENT_RENDERERS, contentType);
		return fn
			? await fn(content, notify)
			: el("div", {
					class: "hint",
					text: `Unsupported content type: ${contentType}`,
				});
	}

	async function renderLayout(
		/** @type {AM2Layout} */ layout,
		/** @type {AM2N} */ notify,
	) {
		if (!layout || layout.type !== "grid") {
			return el("div", { class: "hint", text: "Unsupported layout." });
		}
		const cols = layout.cols || 12;
		const gap = layout.gap || 12;
		const grid = el("div", { class: "grid" });
		grid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
		grid.style.gap = `${gap}px`;

		const children = Array.isArray(layout.children) ? layout.children : [];
		for (const node of children) {
			const colSpan = node.colSpan || cols;

			const card = el("div", { class: "card" });
			card.style.gridColumn = `span ${colSpan}`;

			// Always render a title row (even if empty) to keep card padding/borders consistent.
			const titleText =
				node.type === "card" ? node.title || "" : node.title || node.type || "";
			card.appendChild(el("div", { class: "cardTitle", text: titleText }));

			const body = el("div", { class: "cardBody" }, [
				el("div", { class: "hint", text: "Loading..." }),
			]);
			card.appendChild(body);
			grid.appendChild(card);

			try {
				clear(body);
				const contentObj = node.type === "card" ? node.content || {} : node;
				body.appendChild(await renderContent(contentObj, notify));
			} catch (e) {
				clear(body);
				body.appendChild(el("div", { class: "error", text: String(e) }));
			}
		}

		if (!children.length) {
			grid.appendChild(
				el("div", { class: "hint", text: "No layout children." }),
			);
		}
		return grid;
	}

	async function loadNav() {
		try {
			const nav = await API.getJson("/api/ui/nav");
			return /** @type {AM2WebNavItem[]} */ (
				Array.isArray(nav.items) ? nav.items : []
			);
		} catch (e) {
			console.error(e);
			return [{ title: "Dashboard", route: "/", page_id: "dashboard" }];
		}
	}

	function routeToPageId(
		/** @type {string} */ pathname,
		/** @type {AM2WebNavItem[]} */ navItems,
	) {
		const hit = navItems.find(
			(/** @type {AM2WebNavItem} */ i) => i.route === pathname,
		);
		if (hit) return String(hit.page_id || "dashboard");
		if (pathname === "/") return "dashboard";
		return String(navItems[0] ? navItems[0].page_id : "dashboard");
	}

	async function renderApp() {
		const root = /** @type {HTMLElement} */ (
			document.getElementById("app") || document.body
		);
		const toast = /** @type {HTMLElement} */ (
			document.getElementById("toast") || document.body
		);
		const notify = (/** @type {string} */ msg) => {
			toast.textContent = msg;
			toast.classList.add("show");
			setTimeout(() => toast.classList.remove("show"), 2500);
		};

		const navItems = await loadNav();

		// Debug mode should expose everything through the UI (no DevTools required).
		const debugEnabled =
			Array.isArray(navItems) &&
			navItems.some(
				(/** @type {AM2WebNavItem} */ i) =>
					i && (i.page_id === "debug_js" || i.route === "/debug-js"),
			);
		if (debugEnabled) {
			_amInstallDebugFetchCapture(notify);
		}

		const sidebar = el("div", { class: "sidebar" });
		sidebar.appendChild(el("div", { class: "brand", text: "AudioMason" }));
		const nav = el("div", { class: "nav" });
		navItems.forEach((/** @type {AM2WebNavItem} */ item) => {
			const a = el("a", {
				class: "navItem",
				href: item.route,
				text: item.title,
			});
			a.addEventListener("click", (/** @type {MouseEvent} */ ev) => {
				ev.preventDefault();
				if (item && item.route === "/import") {
					window.location.href = "/import/ui/";
					return;
				}
				history.pushState({}, "", item.route);
				renderRoute();
			});
			nav.appendChild(a);
		});
		sidebar.appendChild(nav);

		const main = el("div", { class: "main" });
		const header = el("div", { class: "header" }, [
			el("div", { class: "headerTitle", text: "" }),
			el("div", { class: "headerRight" }, [
				el("a", { class: "link", href: "/api/ui/schema", text: "schema" }),
			]),
		]);
		main.appendChild(header);
		const content = el("div", { class: "content" }, []);
		main.appendChild(content);

		clear(root);
		root.appendChild(sidebar);
		root.appendChild(main);

		async function renderRoute() {
			const pathname = window.location.pathname.replace(/\/+$/, "") || "/";
			// update active
			Array.from(nav.querySelectorAll(".navItem")).forEach(
				(/** @type {Element} */ n) => {
					n.classList.toggle("active", n.getAttribute("href") === pathname);
				},
			);

			const pageId = routeToPageId(pathname, navItems);
			let page;
			try {
				page = await API.getJson(`/api/ui/page/${encodeURIComponent(pageId)}`);
			} catch (e) {
				notify(String(e));
				page = /** @type {AM2WebPage} */ ({
					title: "Error",
					layout: { type: "grid", cols: 12, gap: 12, children: [] },
				});
			}

			const titleNode = /** @type {HTMLElement | null} */ (
				header.querySelector(".headerTitle")
			);
			if (titleNode) titleNode.textContent = String(page.title || pageId);
			clear(content);
			const layout = /** @type {AM2Layout} */ (
				page.layout || { type: "grid", cols: 12, gap: 12, children: [] }
			);
			content.appendChild(await renderLayout(layout, notify));
		}

		window.addEventListener("popstate", () => {
			void renderRoute();
		});
		await renderRoute();
	}

	try {
		await renderApp();
	} catch (e) {
		console.error(e);
		const root = document.getElementById("app") || document.body;
		root.innerHTML = "";
		const pre = document.createElement("pre");
		pre.style.whiteSpace = "pre-wrap";
		pre.textContent = "UI failed to start: " + String(e);
		root.appendChild(pre);
	}
})();
