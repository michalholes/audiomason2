// PatchHub app core (refactored split: part files).
var __ph_w = /** @type {any} */ (window);
var PH = __ph_w.PH;
PH.loadScript("/static/patchhub_progress_ui.js", "progress");
PH.loadScript("/static/patchhub_live_ui.js", "live");

__ph_w.AMP_PATCHHUB_UI = __ph_w.AMP_PATCHHUB_UI || {};
const AMP_UI = __ph_w.AMP_PATCHHUB_UI;

var activeJobId = null;
var autoRefreshTimer = null;

var uiStatusLatest = "";

var selectedJobId = null;
var liveStreamJobId = null;
var liveES = null;
var liveEvents = [];
var liveLevel = "normal";

var previewVisible = false;
var runsVisible = false;
var jobsVisible = false;

// Deterministic IDLE visible-tab backoff. ACTIVE mode is not affected.
var IDLE_BACKOFF_MS = [2000, 5000, 15000, 30000, 60000];
var idleBackoffIdx = 0;
var idleNextDueMs = 0;
var idleSigs = { jobs: "", runs: "", hdr: "" };

function setPreviewVisible(v) {
	previewVisible = !!v;
	var wrap = el("previewWrapRight");
	var btn1 = el("previewToggle");
	var btn2 = el("previewCollapse");
	if (wrap) wrap.classList.toggle("hidden", !previewVisible);
	var t = previewVisible ? "Hide" : "Show";
	if (btn1) btn1.textContent = previewVisible ? "Hide preview" : "Preview";
	if (btn2) btn2.textContent = t;
}

function isNearBottom(node, slack) {
	if (!node) return true;
	slack = slack == null ? 20 : slack;
	return node.scrollTop + node.clientHeight >= node.scrollHeight - slack;
}

/**
 * @param {string} id
 * @returns {any}
 */
function el(id) {
	return /** @type {any} */ (document.getElementById(id));
}

function setUiStatus(message) {
	var node = el("uiStatusBar");
	if (!node) return;

	var msg = String(message || "");
	msg = msg.replace(/\s*\n\s*/g, " ").trim();
	uiStatusLatest = msg;
	node.textContent = uiStatusLatest;
}

function setUiError(errorText) {
	setUiStatus(`ERROR: ${String(errorText || "")}`);
}

function pushApiStatus(payload) {
	if (!payload || !payload.status || !Array.isArray(payload.status)) return;
	if (!payload.status.length) return;
	setUiStatus(String(payload.status[payload.status.length - 1] || ""));
}

function setPre(id, obj) {
	var node = el(id);
	if (!node) return;
	if (typeof obj === "string") {
		node.textContent = obj;
		return;
	}
	try {
		node.textContent = JSON.stringify(obj, null, 2);
	} catch (e) {
		node.textContent = String(obj);
	}
}

function setText(id, text) {
	var node = el(id);
	if (!node) return;
	node.textContent = String(text || "");
}

function formatLocalTime(isoUtc) {
	if (!isoUtc) return "";
	var d = new Date(String(isoUtc));
	if (isNaN(d.getTime())) return String(isoUtc);
	return d.toLocaleString(undefined, {
		year: "numeric",
		month: "2-digit",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
		second: "2-digit",
	});
}

function apiGet(path) {
	return fetch(path, { headers: { Accept: "application/json" } }).then((r) =>
		r.text().then((t) => {
			try {
				return JSON.parse(t);
			} catch (e) {
				return {
					ok: false,
					error: "bad json",
					raw: t,
					status: r.status,
				};
			}
		}),
	);
}

var __phEtagCache = {};
var __phInFlight = {};
var __phAborters = {};

function apiAbortKey(key) {
	key = String(key || "");
	var ctl = null;
	try {
		ctl = __phAborters[key];
		if (ctl) ctl.abort();
	} catch (_) {}
	__phAborters[key] = null;
	__phInFlight[key] = null;
}

function apiGetETag(key, path, opts) {
	key = String(key || "");
	path = String(path || "");
	opts = opts || {};

	// Request policy:
	// - mode="periodic": MUST NOT start a second request if one is in-flight.
	// - mode="user" or "latest": abort prior request (deterministic: latest wins).
	var mode = String(opts.mode || "latest")
		.trim()
		.toLowerCase();
	var singleFlight = !!opts.single_flight;

	var cur = __phInFlight[key];
	if (cur && (mode === "periodic" || singleFlight)) return cur;

	if (mode !== "periodic") {
		apiAbortKey(key);
	}

	var ctl = new AbortController();
	__phAborters[key] = ctl;

	var hdr = { Accept: "application/json" };
	var et = __phEtagCache[key];
	if (et) hdr["If-None-Match"] = String(et);

	var p = fetch(path, { headers: hdr, signal: ctl.signal }).then((r) => {
		if (r.status === 304) {
			return { ok: true, unchanged: true, status: 304 };
		}
		return r.text().then((t) => {
			var obj = null;
			try {
				obj = JSON.parse(t);
			} catch (e) {
				obj = { ok: false, error: "bad json", raw: t, status: r.status };
			}
			var newEtag = r.headers.get("ETag");
			if (newEtag) __phEtagCache[key] = String(newEtag);
			return obj;
		});
	});
	__phInFlight[key] = p;
	return p.finally(() => {
		if (__phInFlight[key] === p) {
			__phInFlight[key] = null;
			__phAborters[key] = null;
		}
	});
}

function apiPost(path, body) {
	return fetch(path, {
		method: "POST",
		headers: {
			"Content-Type": "application/json",
			Accept: "application/json",
		},
		body: JSON.stringify(body || {}),
	}).then((r) =>
		r.text().then((t) => {
			try {
				return JSON.parse(t);
			} catch (e) {
				return {
					ok: false,
					error: "bad json",
					raw: t,
					status: r.status,
				};
			}
		}),
	);
}

function joinRel(a, b) {
	a = String(a || "").replace(/\/+$/, "");
	b = String(b || "").replace(/^\/+/, "");
	if (!a) return b;
	if (!b) return a;
	return `${a}/${b}`;
}

function parentRel(p) {
	p = String(p || "").replace(/\/+$/, "");
	var idx = p.lastIndexOf("/");
	if (idx < 0) return "";
	return p.slice(0, idx);
}

function escapeHtml(s) {
	return String(s || "")
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#39;");
}

var cfg = null;
var issueRegex = null;
var fsSelected = "";
var fsChecked = {};
var fsLastRels = [];
var runsCache = [];
var selectedRun = null;
var tailLines = 200;

var dirty = { issueId: false, commitMsg: false, patchPath: false };
var latestToken = "";
var lastAutofillClearedToken = "";
var autofillTimer = null;

var patchStatTimer = null;
var patchStatInFlight = false;

var suppressIdleOutput = false;

var lastParsedRaw = "";
var lastParsed = null;
var parseInFlight = false;
var parseTimer = null;
var parseSeq = 0;

function patchesRootRel() {
	var p =
		cfg && cfg.paths && cfg.paths.patches_root
			? String(cfg.paths.patches_root)
			: "patches";
	return p.replace(/\/+$/, "");
}

function stripPatchesPrefix(path) {
	var pfx = patchesRootRel();
	var p = String(path || "").replace(/^\/+/, "");
	if (p === pfx) return "";
	if (p.indexOf(`${pfx}/`) === 0) return p.slice(pfx.length + 1);
	return p;
}

function normalizePatchPath(p) {
	p = String(p || "")
		.trim()
		.replace(/^\/+/, "");
	if (!p) return "";

	var pfx = patchesRootRel();
	if (p === pfx) return pfx;
	if (p.indexOf(`${pfx}/`) === 0) return p;
	return joinRel(pfx, p);
}

function clearRunFieldsBecauseMissingPatch() {
	if (el("issueId")) el("issueId").value = "";
	if (el("commitMsg")) el("commitMsg").value = "";
	if (el("patchPath")) el("patchPath").value = "";
	validateAndPreview();
}

function tickMissingPatchClear() {
	if (patchStatInFlight) return;
	if (!el("patchPath")) return;

	var full = normalizePatchPath(String(el("patchPath").value || ""));
	var rel = stripPatchesPrefix(full);

	patchStatInFlight = true;
	apiGet(`/api/fs/stat?path=${encodeURIComponent(rel)}`)
		.then((r) => {
			patchStatInFlight = false;
			if (!r || r.ok === false) return;
			if (r.exists === false) clearRunFieldsBecauseMissingPatch();
		})
		.catch(() => {
			patchStatInFlight = false;
		});
}

function setFsHint(msg) {
	var h = el("fsHint");
	if (h) h.textContent = msg || "";
}

function fsUpdateSelCount() {
	var n = 0;
	for (var k in fsChecked) {
		if (Object.hasOwn(fsChecked, k)) n += 1;
	}
	var node = el("fsSelCount");
	if (node) {
		node.textContent = n ? `selected: ${String(n)}` : "";
	}
	return n;
}

function fsClearSelection() {
	fsChecked = {};
	fsUpdateSelCount();
}

function fsDownloadSelected() {
	var paths = [];
	for (var k in fsChecked) {
		if (Object.hasOwn(fsChecked, k)) paths.push(k);
	}
	if (!paths.length) {
		setFsHint("select at least one item");
		return;
	}
	paths.sort();

	fetch("/api/fs/archive", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ paths: paths }),
	})
		.then((r) => {
			if (!r.ok) {
				return r.text().then((t) => {
					setFsHint(`archive failed: ${String(t || r.status)}`);
				});
			}
			return r.blob().then((blob) => {
				var url = URL.createObjectURL(blob);
				var a = document.createElement("a");
				a.href = url;
				a.download = "selection.zip";
				document.body.appendChild(a);
				a.click();
				a.remove();
				setTimeout(() => {
					URL.revokeObjectURL(url);
				}, 1000);
			});
		})
		.catch((e) => {
			setFsHint(`archive failed: ${String(e)}`);
		});
}

function setParseHint(msg) {
	setText("parseHint", msg || "");
}

function getRawCommand() {
	var n = el("rawCommand");
	if (!n) return "";
	return String(n.value || "").trim();
}

function clearParsedState() {
	lastParsedRaw = "";
	lastParsed = null;
	parseInFlight = false;
}

function triggerParse(raw) {
	raw = String(raw || "").trim();
	if (!raw) {
		clearParsedState();
		setParseHint("");
		validateAndPreview();
		return;
	}

	parseInFlight = true;
	lastParsedRaw = "";
	lastParsed = null;
	setParseHint("Parsing...");
	setUiStatus("parse_command: started");
	validateAndPreview();

	parseSeq += 1;
	var mySeq = parseSeq;
	apiPost("/api/parse_command", { raw: raw }).then((r) => {
		if (mySeq !== parseSeq) return;
		parseInFlight = false;

		if (!r || r.ok === false) {
			clearParsedState();
			setParseHint(`Parse failed: ${String((r && r.error) || "")}`);
			setUiError(String((r && r.error) || "parse failed"));
			validateAndPreview();
			return;
		}

		pushApiStatus(r);

		lastParsedRaw = raw;
		lastParsed = r;
		setParseHint("");
		if (r.parsed && typeof r.parsed === "object") {
			if (r.parsed.mode) el("mode").value = String(r.parsed.mode);
			if (r.parsed.issue_id != null) {
				el("issueId").value = String(r.parsed.issue_id || "");
			}
			if (r.parsed.commit_message != null) {
				el("commitMsg").value = String(r.parsed.commit_message || "");
			}
			if (r.parsed.patch_path != null) {
				el("patchPath").value = String(r.parsed.patch_path || "");
			}
		}

		validateAndPreview();
	});
}

function scheduleParseDebounced(raw) {
	if (parseTimer) {
		clearTimeout(parseTimer);
		parseTimer = null;
	}
	parseTimer = setTimeout(() => {
		parseTimer = null;
		triggerParse(raw);
	}, 350);
}

function refreshFs() {
	var path = el("fsPath").value || "";
	apiGet(`/api/fs/list?path=${encodeURIComponent(path)}`).then((r) => {
		if (!r || r.ok === false) {
			setPre("fsList", r);
			return;
		}
		var items = r.items || [];
		fsLastRels = [];
		var html = items
			.map((it) => {
				var name = it.name;
				var isDir = !!it.is_dir;
				var rel = joinRel(path, name);
				fsLastRels.push(rel);

				var displayName = isDir ? `${name}/` : name;
				var isSelected = fsSelected === rel;
				var cls = `item fsitem${isSelected ? " selected" : ""}`;
				var checked = fsChecked[rel] ? " checked" : "";

				var dl = "";
				if (!isDir) {
					dl =
						'<button class="btn btn-small btn-inline fsDl" data-rel="' +
						escapeHtml(rel) +
						'">Download</button>';
				}

				return (
					'<div class="' +
					cls +
					'" data-rel="' +
					escapeHtml(rel) +
					'" data-isdir="' +
					(isDir ? "1" : "0") +
					'">' +
					'<input class="fsChk" type="checkbox" data-rel="' +
					escapeHtml(rel) +
					'" aria-label="Select" ' +
					checked +
					" />" +
					'<span class="name">' +
					escapeHtml(displayName) +
					"</span>" +
					'<span class="actions"><span class="muted">' +
					String(it.size || 0) +
					"</span>" +
					dl +
					"</span>" +
					"</div>"
				);
			})
			.join("");

		el("fsList").innerHTML = html || '<div class="muted">(empty)</div>';
		fsUpdateSelCount();

		Array.from(el("fsList").querySelectorAll(".fsChk")).forEach((node) => {
			node.addEventListener("click", (ev) => {
				ev.stopPropagation();
				var rel = node.getAttribute("data-rel") || "";
				if (!rel) return;
				if (node.checked) {
					fsChecked[rel] = true;
				} else {
					delete fsChecked[rel];
				}
				fsUpdateSelCount();
			});
		});

		Array.from(el("fsList").querySelectorAll(".fsDl")).forEach((node) => {
			node.addEventListener("click", (ev) => {
				ev.stopPropagation();
				var rel = node.getAttribute("data-rel") || "";
				if (!rel) return;
				window.location.href = `/api/fs/download?path=${encodeURIComponent(rel)}`;
			});
		});

		Array.from(el("fsList").querySelectorAll(".fsitem .name")).forEach(
			(node) => {
				node.addEventListener("click", () => {
					var item = node.parentElement;
					var rel = item.getAttribute("data-rel") || "";
					var isDir = (item.getAttribute("data-isdir") || "0") === "1";
					if (isDir) {
						el("fsPath").value = rel;
						fsSelected = "";
						setFsHint("");
						refreshFs();
						return;
					}

					fsSelected = rel;
					setFsHint(`focused: ${rel}`);

					if (/\.(zip|patch|diff)$/i.test(rel)) {
						el("patchPath").value = normalizePatchPath(rel);

						let m = null;
						if (issueRegex) {
							try {
								m = issueRegex.exec(rel);
							} catch (e) {
								m = null;
							}
						}
						if (!m) {
							m = /(?:issue_|#)(\d+)/i.exec(rel) || /(\d{3,6})/.exec(rel);
						}
						if (m && m[1] && !String(el("issueId").value || "").trim()) {
							el("issueId").value = String(m[1]);
						}
						validateAndPreview();
					}

					refreshFs();
				});
			},
		);
	});
}

// Refactor: split large sections into part files to satisfy monolith gate.
// NOTE: document.write is used to preserve synchronous execution order during initial parse.
document.write('<script src="/static/app_part_runs.js"></script>');
document.write('<script src="/static/app_part_jobs.js"></script>');
document.write('<script src="/static/app_part_queue_upload.js"></script>');
document.write('<script src="/static/app_part_autofill_header.js"></script>');
document.write('<script src="/static/app_part_wire_init.js"></script>');
