/** @type {any} */
var __ph_w = /** @type {any} */ (window);
var PH = /** @type {any} */ (window).PH;
function applyAutofillFromPayload(p) {
	if (!cfg || !cfg.autofill || !p) return;

	if (cfg.autofill.fill_patch_path && p.stored_rel_path) {
		const n1 = el("patchPath");
		if (n1 && shouldOverwrite("patchPath", n1)) {
			n1.value = String(p.stored_rel_path);
		}
	}

	if (cfg.autofill.fill_issue_id && p.derived_issue != null) {
		const n2 = el("issueId");
		if (n2 && shouldOverwrite("issueId", n2)) {
			n2.value = String(p.derived_issue || "");
		}
	}

	if (cfg.autofill.fill_commit_message && p.derived_commit_message != null) {
		const n3 = el("commitMsg");
		if (n3 && shouldOverwrite("commitMsg", n3)) {
			n3.value = String(p.derived_commit_message || "");
		}
	}

	validateAndPreview();
}

function resetOutputForNewPatch() {
	selectedJobId = null;
	AMP_UI.saveLiveJobId("");

	PH.call("openLiveStream", null);
	setPre("tail", "");
	__ph_w.updateShortProgressFromText("");

	suppressIdleOutput = true;

	if (cfg && cfg.ui && cfg.ui.show_autofill_clear_status) {
		setUiStatus("autofill: loaded new patch, output cleared");
	}
}

function pollLatestPatchOnce() {
	if (!cfg || !cfg.autofill || !cfg.autofill.enabled) return;
	var qs = latestToken
		? "?since_token=" + encodeURIComponent(String(latestToken))
		: "";
	apiGetETag("patches_latest", "/api/patches/latest" + qs).then((r) => {
		if (!r || r.ok === false) {
			setUiError(String((r && r.error) || "autofill scan failed"));
			return;
		}

		if (r && r.unchanged) return;
		pushApiStatus(r);
		if (!r.found) return;
		var token = String(r.token || "");
		if (!token || token === latestToken) return;
		latestToken = token;
		// New patch token: reset UI state deterministically.
		try {
			if (typeof dirty === "object" && dirty) {
				dirty.issueId = false;
				dirty.commitMsg = false;
				dirty.patchPath = false;
			}
		} catch (_) {}
		try {
			const m = el("mode");
			if (m) m.value = "patch";
			const rc = el("rawCommand");
			if (rc) rc.value = "";
		} catch (_) {}
		applyAutofillFromPayload(r);

		if (cfg && cfg.ui && cfg.ui.clear_output_on_autofill) {
			if (token !== lastAutofillClearedToken) {
				resetOutputForNewPatch();
				lastAutofillClearedToken = token;
			}
		}
	});
}

function stopAutofillPolling() {
	if (autofillTimer) {
		clearInterval(autofillTimer);
		autofillTimer = null;
	}
}

function startAutofillPolling() {
	if (autofillTimer) {
		clearInterval(autofillTimer);
		autofillTimer = null;
	}
	if (!cfg || !cfg.autofill || !cfg.autofill.enabled) return;
	var sec = parseInt(String(cfg.autofill.poll_interval_seconds || "10"), 10);
	if (isNaN(sec) || sec < 1) sec = 10;
	autofillTimer = setInterval(pollLatestPatchOnce, sec * 1000);
	pollLatestPatchOnce();
}

function renderHeaderFromDiagnostics(d, base) {
	if (!d || d.ok === false) return;
	var lock = d.lock || {};
	var disk = d.disk || {};
	var held = lock.held ? "LOCK:held" : "LOCK:free";
	var pct = "";
	if (disk.total && disk.used) {
		pct = "disk:" + String(Math.round((disk.used / disk.total) * 100)) + "%";
	}

	var meta = base;
	if (cfg && cfg.paths && cfg.paths.patches_root) {
		meta += " | patches: " + cfg.paths.patches_root;
	}
	meta += " | " + held;
	if (pct) meta += " | " + pct;

	if (el("hdrMeta")) el("hdrMeta").textContent = meta;
}

function refreshHeader() {
	var base = "";
	if (cfg && cfg.server && cfg.server.host && cfg.server.port) {
		base = "server: " + cfg.server.host + ":" + cfg.server.port;
	}

	apiGet("/api/debug/diagnostics").then((d) => {
		renderHeaderFromDiagnostics(d, base);
	});
}

function setTabActive(which) {
	var tabs = ["Overview", "Logs", "Patch", "Diff", "Files"];
	tabs.forEach((t) => {
		var btn = el("tab" + t);
		if (btn) {
			if (t === which) btn.classList.add("active");
			else btn.classList.remove("active");
		}
	});
}

function renderIssueDetail() {
	var cardTitle = el("issueDetailTitle");
	var tabs = el("issueTabs");
	var content = el("issueTabContent");
	var links = el("issueTabLinks");
	var body = el("issueTabBody");

	if (!selectedRun) {
		if (cardTitle) cardTitle.textContent = "Select a run on the left.";
		if (tabs) tabs.style.display = "none";
		if (content) content.style.display = "none";
		return;
	}

	if (cardTitle) {
		cardTitle.textContent =
			"Issue #" +
			String(selectedRun.issue_id) +
			" (" +
			String(selectedRun.result || "") +
			")";
	}
	if (tabs) tabs.style.display = "flex";
	if (content) content.style.display = "block";

	function renderLinks() {
		var parts = [];

		function add(label, rel) {
			if (!rel) return;
			parts.push(
				'<a class="linklike" href="/api/fs/download?path=' +
					encodeURIComponent(rel) +
					'">' +
					escapeHtml(label) +
					"</a>",
			);
		}

		add("log", selectedRun.log_rel_path);
		add("archived patch", selectedRun.archived_patch_rel_path);
		add("diff bundle", selectedRun.diff_bundle_rel_path);
		add("latest success zip", selectedRun.success_zip_rel_path);

		links.innerHTML = parts.join(" ");
	}

	function renderOverview() {
		setTabActive("Overview");
		renderLinks();
		setPre("issueTabBody", selectedRun);
	}

	function renderLogs() {
		setTabActive("Logs");
		renderLinks();
		if (!selectedRun.log_rel_path) {
			setPre("issueTabBody", "(no log path)");
			return;
		}
		var p = String(selectedRun.log_rel_path);
		var url =
			"/api/fs/read_text?path=" + encodeURIComponent(p) + "&tail_lines=2000";
		apiGet(url).then((r) => {
			if (!r || r.ok === false) {
				setPre("issueTabBody", r);
				return;
			}
			var t = String(r.text || "");
			if (r.truncated) {
				t += "\n\n[TRUNCATED]";
			}
			setPre("issueTabBody", t);
		});
	}

	function renderPatch() {
		setTabActive("Patch");
		renderLinks();
		if (selectedRun.archived_patch_rel_path) {
			setPre(
				"issueTabBody",
				"Download: /api/fs/download?path=" +
					selectedRun.archived_patch_rel_path,
			);
		} else {
			setPre("issueTabBody", "(no archived patch)");
		}
	}

	function renderDiff() {
		setTabActive("Diff");
		renderLinks();
		if (selectedRun.diff_bundle_rel_path) {
			setPre(
				"issueTabBody",
				"Download: /api/fs/download?path=" + selectedRun.diff_bundle_rel_path,
			);
		} else {
			setPre("issueTabBody", "(no diff bundle)");
		}
	}

	function renderFiles() {
		setTabActive("Files");
		renderLinks();
		// Convenience: jump file manager to the issue directory if possible.
		var p = "";
		if (selectedRun.log_rel_path) {
			p = parentRel(stripPatchesPrefix(selectedRun.log_rel_path));
		}
		if (p) {
			el("fsPath").value = p;
			fsSelected = "";
			setFsHint("");
			refreshFs();
		}
		setPre(
			"issueTabBody",
			"File manager path set to: " + String(el("fsPath").value || ""),
		);
	}

	el("tabOverview").onclick = renderOverview;
	el("tabLogs").onclick = renderLogs;
	el("tabPatch").onclick = renderPatch;
	el("tabDiff").onclick = renderDiff;
	el("tabFiles").onclick = renderFiles;

	// Default to overview when switching run.
	renderOverview();
}
