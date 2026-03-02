(() => {
	function el(id) {
		return document.getElementById(id);
	}

	function setText(id, text) {
		var node = el(id);
		if (!node) return;
		node.textContent = String(text || "");
	}

	function record(list, item, max) {
		if (!Array.isArray(list)) return;
		list.push(item);
		if (max && list.length > max) list.splice(0, list.length - max);
	}

	function tryGetLocalStorage() {
		try {
			return window.localStorage;
		} catch (e) {
			return null;
		}
	}

	function recordClientStatus(kind, message) {
		var store = tryGetLocalStorage();
		if (!store) return;
		var item = {
			ts: nowIso(),
			kind: String(kind || ""),
			msg: String(message || ""),
		};
		var raw = "[]";
		var arr = [];
		try {
			raw = store.getItem("patchhub.client_status_log") || "[]";
			try {
				arr = JSON.parse(raw) || [];
			} catch (e) {
				arr = [];
			}
			arr.push(item);
			if (arr.length > 200) arr = arr.slice(arr.length - 200);
			store.setItem("patchhub.client_status_log", JSON.stringify(arr));
		} catch (e) {
			// ignore
		}
	}
	function nowIso() {
		try {
			return new Date().toISOString();
		} catch (e) {
			return "";
		}
	}

	function uiStatus(message) {
		var node = el("uiStatusBar");
		if (!node) return;
		var msg = String(message || "");
		msg = msg.replace(/\s*\n\s*/g, " ").trim();
		if (!msg) return;
		if (node.textContent === msg) return;
		node.textContent = msg;
	}

	function log(kind, message, details) {
		var msg = String(message || "");
		if (details) msg += ` (${String(details)})`;
		try {
			if (kind === "error") console.error("[PatchHub]", msg);
			else if (kind === "warn") console.warn("[PatchHub]", msg);
			else console.log("[PatchHub]", msg);
		} catch (e) {
			// ignore
		}
		uiStatus(msg);
		recordClientStatus(kind, msg);
	}

	const registry = {};
	const diag = [];
	const once = { missing: {}, fault: {}, load: {} };

	function ensureModule(name) {
		if (!registry[name]) {
			registry[name] = {
				state: "missing",
				last_error: "",
				capabilities: [],
			};
		}
		return registry[name];
	}

	function degradedNote(moduleName, state, details) {
		var msg = `Degraded mode: ${String(moduleName)} ${String(state)}`;
		if (details) msg += ` (${String(details)})`;
		return msg;
	}

	const pending = {};
	const deferCaps = {
		openLiveStream: true,
		closeLiveStream: true,
		renderLiveLog: true,
		updateProgressFromEvents: true,
		updateProgressPanelFromEvents: true,
		refreshStats: true,
		renderActiveJob: true,
	};

	function enqueue(capabilityName, args) {
		var cap = String(capabilityName || "");
		if (!cap) return;
		pending[cap] = pending[cap] || [];
		pending[cap].push(args || []);
		record(diag, { ts: nowIso(), kind: "deferred", cap }, 50);
	}

	function flushPending(caps) {
		if (!Array.isArray(caps) || !caps.length) return;
		for (let i = 0; i < caps.length; i++) {
			const cap = String(caps[i] || "");
			const calls = pending[cap];
			if (!calls || !calls.length) continue;
			delete pending[cap];
			for (let j = 0; j < calls.length; j++) {
				try {
					call(cap, ...(calls[j] || []));
				} catch (e) {
					// ignore
				}
			}
		}
	}

	const defaults = {
		getLiveJobId: () => null,
		loadLiveJobId: () => null,
		jobSummaryCommit: (s) => String(s || ""),
		jobSummaryPatchName: (s) => String(s || ""),
		jobSummaryDurationSeconds: () => "",
		loadUiVisibility: () => {
			var store = tryGetLocalStorage();
			if (!store) return undefined;
			var rv = null;
			var jv = null;
			try {
				rv = store.getItem("amp.ui.runsVisible");
				jv = store.getItem("amp.ui.jobsVisible");
				if (rv === "1") defaults.setRunsVisible(true);
				if (jv === "1") defaults.setJobsVisible(true);
			} catch (e) {}
			return undefined;
		},
		saveRunsVisible: (v) => {
			var store = tryGetLocalStorage();
			if (!store) return undefined;
			try {
				store.setItem("amp.ui.runsVisible", v ? "1" : "0");
			} catch (e) {}
			return undefined;
		},
		saveJobsVisible: (v) => {
			var store = tryGetLocalStorage();
			if (!store) return undefined;
			try {
				store.setItem("amp.ui.jobsVisible", v ? "1" : "0");
			} catch (e) {}
			return undefined;
		},
		setRunsVisible: (v) => {
			var visible = !!v;
			var wrap = el("runsWrap");
			var btn = el("runsCollapse");
			if (wrap) wrap.classList.toggle("hidden", !visible);
			if (btn) btn.textContent = visible ? "Hide" : "Show";
			return undefined;
		},
		setJobsVisible: (v) => {
			var visible = !!v;
			var wrap = el("jobsWrap");
			var btn = el("jobsCollapse");
			if (wrap) wrap.classList.toggle("hidden", !visible);
			if (btn) btn.textContent = visible ? "Hide" : "Show";
			return undefined;
		},
		setLiveStreamStatus: (s) => setText("liveStreamStatus", String(s || "")),
		openLiveStream: (jobId) => {
			enqueue("openLiveStream", [jobId]);
			return undefined;
		},
		closeLiveStream: () => {
			enqueue("closeLiveStream", []);
			return undefined;
		},
		renderLiveLog: () => {
			enqueue("renderLiveLog", []);
			return undefined;
		},
		updateProgressFromEvents: () => {
			enqueue("updateProgressFromEvents", []);
			return undefined;
		},
		updateProgressPanelFromEvents: () => {
			enqueue("updateProgressPanelFromEvents", []);
			return undefined;
		},
		refreshStats: () => {
			enqueue("refreshStats", []);
			return undefined;
		},
		renderActiveJob: () => {
			enqueue("renderActiveJob", []);
			return undefined;
		},
	};

	function register(moduleName, exportsObj, meta) {
		var m = ensureModule(moduleName);
		var ex = {};
		var caps = [];
		try {
			ex = exportsObj || {};
			caps = Object.keys(ex);
			m.state = "ready";
			m.last_error = "";
			m.capabilities = caps.slice(0);
			m.exports = ex;
			m.meta = meta || {};
			flushPending(caps);
		} catch (e) {
			m.state = "faulted";
			m.last_error = String((e && e.message) || e || "");
			record(
				diag,
				{
					ts: nowIso(),
					kind: "register",
					module: moduleName,
					error: m.last_error,
				},
				50,
			);
		}
	}

	function hasOwn(obj, key) {
		return Object.hasOwn(obj, key);
	}

	function findCapability(capabilityName) {
		var name = String(capabilityName || "");
		var keys = Object.keys(registry);
		for (let i = 0; i < keys.length; i++) {
			const mod = registry[keys[i]];
			if (!mod || mod.state !== "ready" || !mod.exports) continue;
			if (hasOwn(mod.exports, name)) {
				return { moduleName: keys[i], handler: mod.exports[name] };
			}
		}
		return null;
	}

	function has(capabilityName) {
		return !!findCapability(capabilityName);
	}

	function call(capabilityName, ...args) {
		var cap = String(capabilityName || "");
		var hit = findCapability(cap);
		var mod = null;
		var note = "";
		if (!hit) {
			record(diag, { ts: nowIso(), kind: "missing", cap }, 50);
			if (deferCaps[cap]) {
				enqueue(cap, args);
				return undefined;
			}
			// Defaults are first-class fallback behavior; do not label as degraded.
			if (hasOwn(defaults, cap)) {
				try {
					return defaults[cap].apply(null, args);
				} catch (e) {
					if (!once.fault[`default:${cap}`]) {
						once.fault[`default:${cap}`] = true;
						log("error", degradedNote("default", "faulted", cap));
					}
					return undefined;
				}
			}
			if (!once.missing[cap]) {
				once.missing[cap] = true;
				log("warn", degradedNote("capability", "missing", cap));
			}
			return undefined;
		}

		try {
			return hit.handler.apply(null, args);
		} catch (e) {
			mod = ensureModule(hit.moduleName);
			// Do not hard-disable the whole module on a single handler failure.
			// Record the error and keep the module available so the UI can recover.
			mod.last_error = String((e && e.message) || e || "");
			record(
				diag,
				{
					ts: nowIso(),
					kind: "fault",
					module: hit.moduleName,
					cap,
					error: mod.last_error,
				},
				50,
			);
			note = degradedNote(hit.moduleName, "faulted", mod.last_error);
			if (!once.fault[`${hit.moduleName}:${cap}`]) {
				once.fault[`${hit.moduleName}:${cap}`] = true;
				log("error", note);
			}
			if (cap === "renderLiveLog") setText("liveLog", note);
			else if (cap.indexOf("progress") >= 0) setText("progressSummary", note);
			return undefined;
		}
	}

	function loadScript(url, moduleName) {
		var m = ensureModule(moduleName);
		m.state = "loading";
		m.last_error = "";

		return new Promise((resolve) => {
			let s = null;
			try {
				s = document.createElement("script");
				s.src = String(url || "");
				s.async = true;
				s.onload = () => {
					setTimeout(() => {
						if (m.state === "loading") {
							m.state = "faulted";
							m.last_error = "loaded but not registered";
							record(
								diag,
								{
									ts: nowIso(),
									kind: "load_no_register",
									module: moduleName,
									url,
								},
								50,
							);
							if (!once.load[moduleName]) {
								once.load[moduleName] = true;
								log(
									"error",
									degradedNote(
										moduleName,
										"faulted",
										"loaded but not registered",
									),
								);
							}
						}
					}, 0);
					resolve(true);
				};
				s.onerror = () => {
					m.state = "missing";
					m.last_error = "load failed";
					record(
						diag,
						{ ts: nowIso(), kind: "load_error", module: moduleName, url },
						50,
					);
					if (!once.load[moduleName]) {
						once.load[moduleName] = true;
						log(
							"error",
							degradedNote(moduleName, "missing", "script load failed"),
						);
					}
					resolve(false);
				};
				document.head.appendChild(s);
			} catch (e) {
				m.state = "missing";
				m.last_error = "load exception";
				record(
					diag,
					{ ts: nowIso(), kind: "load_exception", module: moduleName },
					50,
				);
				resolve(false);
			}
		});
	}

	window.addEventListener("error", (ev) => {
		try {
			const msg = (ev && ev.message) || "window error";
			log("error", `Unhandled error: ${String(msg)}`);
		} catch (e) {
			// ignore
		}
	});

	window.addEventListener("unhandledrejection", (ev) => {
		try {
			const r = ev && ev.reason;
			const msg = (r && r.message) || String(r || "unhandled rejection");
			log("error", `Unhandled rejection: ${msg}`);
		} catch (e) {
			// ignore
		}
	});

	function observeStatusBar() {
		var node = el("uiStatusBar");
		if (!node || typeof MutationObserver === "undefined") return;
		var obs = null;
		try {
			obs = new MutationObserver(() => {
				var msg = String(node.textContent || "").trim();
				if (!msg) return;
				recordClientStatus("status", msg);
				record(diag, { ts: nowIso(), kind: "status", msg }, 50);
			});
			obs.observe(node, {
				childList: true,
				characterData: true,
				subtree: true,
			});
		} catch (e) {
			// ignore
		}
	}

	observeStatusBar();

	var W = /** @type {any} */ (window);

	W.PH = {
		register,
		has,
		call,
		loadScript,
		_diag: diag,
		_registry: registry,
	};

	W.uiCall = (name, ...args) => {
		try {
			return W.PH.call(name, ...args);
		} catch (e) {
			return undefined;
		}
	};
})();
