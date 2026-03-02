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

	const registry = {};
	const diag = [];

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
			setText("liveStreamStatus", degradedNote("live", "missing", jobId));
			setText("liveLog", degradedNote("live", "missing"));
			return undefined;
		},
		closeLiveStream: () => {
			setText("liveStreamStatus", degradedNote("live", "missing"));
			return undefined;
		},
		renderLiveLog: () => {
			setText("liveLog", degradedNote("live", "missing"));
			return undefined;
		},
		updateProgressFromEvents: () => {
			setText("progressSummary", degradedNote("progress", "missing"));
			return undefined;
		},
		updateProgressPanelFromEvents: () => {
			setText("progressSummary", degradedNote("progress", "missing"));
			return undefined;
		},
		refreshStats: () => {
			setText("stats", degradedNote("progress", "missing"));
			return undefined;
		},
		renderActiveJob: () => {
			setText("activeJob", degradedNote("progress", "missing"));
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

	function findCapability(capabilityName) {
		var name = String(capabilityName || "");
		var keys = Object.keys(registry);
		for (let i = 0; i < keys.length; i++) {
			const mod = registry[keys[i]];
			if (!mod || mod.state !== "ready" || !mod.exports) continue;
			if (Object.hasOwn(mod.exports, name)) {
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
			if (Object.hasOwn(defaults, cap)) {
				try {
					return defaults[cap].apply(null, args);
				} catch (e) {
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

	window.PH = {
		register,
		has,
		call,
		loadScript,
		_diag: diag,
		_registry: registry,
	};

	window.uiCall = (name, ...args) => {
		try {
			return window.PH.call(name, ...args);
		} catch (e) {
			return undefined;
		}
	};
})();
