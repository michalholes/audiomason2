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
		loadUiVisibility: () => undefined,
		saveRunsVisible: () => undefined,
		saveJobsVisible: () => undefined,
		setRunsVisible: () => undefined,
		setJobsVisible: () => undefined,
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
		return Object.prototype.hasOwnProperty.call(obj, key);
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
			if (!once.missing[cap]) {
				once.missing[cap] = true;
				log("warn", degradedNote("capability", "missing", cap));
			}
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
			return undefined;
		}

		try {
			return hit.handler.apply(null, args);
		} catch (e) {
			mod = ensureModule(hit.moduleName);
			mod.state = "faulted";
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
		m.state = "missing";
		m.last_error = "";

		return new Promise((resolve) => {
			let s = null;
			try {
				s = document.createElement("script");
				s.src = String(url || "");
				s.async = true;
				s.onload = () => resolve(true);
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
