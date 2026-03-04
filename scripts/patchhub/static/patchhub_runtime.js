// PatchHub client runtime (touchable).
// Provides PH namespace: module registry, safe call access, and ordered script load.

(() => {
	/** @type {any} */
	var W = window;
	var BOOT = W.PH_BOOT || null;

	function nowIso() {
		try {
			return new Date().toISOString();
		} catch (e) {
			return "";
		}
	}

	function logStatus(kind, message) {
		var msg = String(message || "");
		try {
			if (kind === "error") console.error("[PatchHub]", msg);
			else if (kind === "warn") console.warn("[PatchHub]", msg);
			else console.log("[PatchHub]", msg);
		} catch (e) {
			// ignore
		}
		try {
			if (BOOT && typeof BOOT.recordClientStatus === "function") {
				BOOT.recordClientStatus(kind, msg);
			}
		} catch (e) {
			// ignore
		}
	}

	function setDegraded(reason) {
		try {
			if (BOOT && typeof BOOT.setDegradedOnce === "function") {
				BOOT.setDegradedOnce(reason);
			}
		} catch (e) {
			// ignore
		}
	}

	function record(list, item, max) {
		if (!Array.isArray(list)) return;
		list.push(item);
		if (max && list.length > max) list.splice(0, list.length - max);
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

	function register(moduleName, exportsObj) {
		var name = String(moduleName || "");
		var m = ensureModule(name);
		m.state = "ready";
		m.exports = exportsObj || {};
		m.capabilities = Object.keys(m.exports || {});
		record(diag, { ts: nowIso(), kind: "register", module: name }, 50);
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
		if (!hit) {
			record(diag, { ts: nowIso(), kind: "missing", cap }, 50);
			if (!once.missing[cap]) {
				once.missing[cap] = true;
				logStatus("warn", degradedNote("capability", "missing", cap));
				setDegraded(`capability missing: ${cap}`);
			}
			return undefined;
		}

		try {
			return hit.handler.apply(null, args);
		} catch (e) {
			const mod = ensureModule(hit.moduleName);
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
			const note = degradedNote(hit.moduleName, "faulted", mod.last_error);
			if (!once.fault[`${hit.moduleName}:${cap}`]) {
				once.fault[`${hit.moduleName}:${cap}`] = true;
				logStatus("error", note);
				setDegraded(`capability fault: ${cap}`);
			}
			return undefined;
		}
	}

	function loadScript(url, moduleName) {
		var u = String(url || "");
		var name = String(moduleName || "");
		var m = ensureModule(name);
		m.state = "loading";
		m.last_error = "";
		logStatus("status", `load-start ${name} ${u}`);
		return new Promise((resolve) => {
			/** @type {HTMLScriptElement | null} */
			var s = null;
			try {
				s = document.createElement("script");
				s.src = u;
				s.async = false;
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
									module: name,
									url: u,
								},
								50,
							);
							if (!once.load[name]) {
								once.load[name] = true;
								logStatus(
									"error",
									degradedNote(name, "faulted", "loaded but not registered"),
								);
								setDegraded(`module load-no-register: ${name}`);
							}
						}
					}, 0);
					logStatus("status", `load-ok ${name}`);
					resolve(true);
				};
				s.onerror = () => {
					m.state = "missing";
					m.last_error = "load failed";
					record(
						diag,
						{ ts: nowIso(), kind: "load_error", module: name, url: u },
						50,
					);
					if (!once.load[name]) {
						once.load[name] = true;
						logStatus(
							"error",
							degradedNote(name, "missing", "script load failed"),
						);
						setDegraded(`module load-failed: ${name}`);
					}
					resolve(false);
				};
				document.head.appendChild(s);
			} catch (e) {
				m.state = "missing";
				m.last_error = "load exception";
				record(
					diag,
					{ ts: nowIso(), kind: "load_exception", module: name },
					50,
				);
				setDegraded(`module load-exception: ${name}`);
				resolve(false);
			}
		});
	}

	W.PH = {
		register,
		has,
		call,
		loadScript,
		_diag: diag,
		_registry: registry,
	};
})();
