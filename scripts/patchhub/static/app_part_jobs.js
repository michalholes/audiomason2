/** @type {any} */
var __ph_w = /** @type {any} */ (window);
var PH = /** @type {any} */ (window).PH;
function renderJobsFromResponse(r) {
	var jobs = r.jobs || [];

	// If the most recently enqueued job reached a terminal state, reset mode to patch.
	try {
		const lastId = String(window.__ph_last_enqueued_job_id || "");
		if (lastId) {
			const j =
				(jobs || []).find((x) => String(x.job_id || "") === lastId) || null;
			const st = j
				? String(j.status || "")
						.trim()
						.toLowerCase()
				: "";
			if (st && st !== "running" && st !== "queued") {
				const m = el("mode");
				if (m) m.value = "patch";
				// Clear transient inputs from the completed non-patch job.
				try {
					const iid = el("issueId");
					if (iid) iid.value = "";
					const cm = el("commitMsg");
					if (cm) cm.value = "";
					const pp = el("patchPath");
					if (pp) pp.value = "";
					const rc = el("rawCommand");
					if (rc) rc.value = "";
				} catch (_) {}
				try {
					dirty.issueId = false;
					dirty.commitMsg = false;
					dirty.patchPath = false;
				} catch (_) {}
				// Ensure the rest of the form state is updated.
				try {
					if (typeof __ph_w.validateAndPreview === "function") {
						__ph_w.validateAndPreview();
					} else if (m) {
						m.dispatchEvent(new Event("change"));
					}
				} catch (_) {}
				window.__ph_last_enqueued_job_id = "";
				window.__ph_last_enqueued_mode = "";
			}
		}
	} catch (_) {}

	var active = jobs.find((j) => j.status === "running") || null;
	var activeId = active ? String(active.job_id || "") : "";

	var idleAutoSelect = !!(cfg && cfg.ui && cfg.ui.idle_auto_select_last_job);

	if (!selectedJobId) {
		const saved = PH.call("loadLiveJobId");
		if (saved) selectedJobId = saved;
	}

	if (!selectedJobId && activeId) {
		selectedJobId = activeId;
		AMP_UI.saveLiveJobId(selectedJobId);
		suppressIdleOutput = false;
	}

	if (!selectedJobId && jobs.length && idleAutoSelect) {
		jobs.sort((a, b) =>
			String(a.created_utc || "").localeCompare(String(b.created_utc || "")),
		);
		selectedJobId = String(jobs[jobs.length - 1].job_id || "");
		if (selectedJobId) AMP_UI.saveLiveJobId(selectedJobId);
		suppressIdleOutput = false;
	}
	PH.call("renderActiveJob", jobs);
	ensureAutoRefresh(jobs);

	var html = jobs
		.map((j) => {
			var jobId = String(j.job_id || "");
			var isSel = selectedJobId && String(selectedJobId) === jobId;
			var cls = `item job-item${isSel ? " selected" : ""}`;

			var issueId = String(j.issue_id || "").trim();
			var issueText = issueId ? `#${issueId}` : "(no issue)";

			var stRaw = String(j.status || "")
				.trim()
				.toLowerCase();
			var statusText = stRaw ? stRaw.toUpperCase() : "UNKNOWN";
			var statusCls = `job-status st-${stRaw || "unknown"}`;

			var metaParts = [];
			metaParts.push(`mode=${String(j.mode || "")}`);

			var dur = PH.call(
				"jobSummaryDurationSeconds",
				j.started_utc,
				j.ended_utc,
			);
			if (dur) metaParts.push(`dur=${dur}s`);

			var meta = metaParts.join(" | ");

			var line = '<div class="' + cls + '">';
			line +=
				'<div class="name job-name" data-jobid="' + escapeHtml(jobId) + '">';
			line += '<div class="job-lines">';
			line += '<div class="job-top">';
			line += '<span class="job-issue">' + escapeHtml(issueText) + "</span>";
			line +=
				'<span class="' +
				escapeHtml(statusCls) +
				'">' +
				escapeHtml(statusText) +
				"</span>";
			line += "</div>";
			line += '<div class="job-meta">' + escapeHtml(meta) + "</div>";
			line += "</div>";
			line += "</div>";
			line += "</div>";
			return line;
		})
		.join("");
	el("jobsList").innerHTML = html || '<div class="muted">(none)</div>';
}

function refreshJobsIdle() {
	var qs = "";
	if (idleSigs.jobs) qs = "?since_sig=" + encodeURIComponent(idleSigs.jobs);
	return apiGet("/api/jobs" + qs).then((r) => {
		if (!r || r.ok === false) {
			return { changed: false, sig: idleSigs.jobs };
		}
		var sig = String(r.sig || "");
		if (sig) idleSigs.jobs = sig;
		if (r.unchanged) return { changed: false, sig: sig };
		renderJobsFromResponse(r);
		return { changed: true, sig: sig };
	});
}

function idleRefreshTick() {
	if (document.hidden) return;
	if (!idleNextDueMs) idleNextDueMs = 0;
	if (Date.now() < idleNextDueMs) return;

	var qs = "";
	if (idleSigs.snapshot)
		qs = "?since_sig=" + encodeURIComponent(idleSigs.snapshot);

	apiGetETag("ui_snapshot", "/api/ui_snapshot" + qs)
		.then((r) => {
			if (!r || r.ok === false) return { changed: false };
			if (r.unchanged) return { changed: false };

			var snapSig = String(r.sig || "");
			if (snapSig) idleSigs.snapshot = snapSig;

			var js = String(r.jobs_sig || "");
			var rs = String(r.runs_sig || "");
			var hs = String(r.diag_sig || "");
			if (js) idleSigs.jobs = js;
			if (rs) idleSigs.runs = rs;
			if (hs) idleSigs.hdr = hs;

			renderJobsFromResponse({ ok: true, jobs: r.jobs || [] });
			__ph_w.renderRunsFromResponse({ ok: true, runs: r.runs || [] });

			var base = "";
			if (cfg && cfg.server && cfg.server.host && cfg.server.port) {
				base = "server: " + cfg.server.host + ":" + cfg.server.port;
			}
			renderHeaderFromDiagnostics(r.diagnostics || {}, base);

			return { changed: true };
		})
		.then((res) => {
			var changed = !!(res && res.changed);
			if (changed) {
				idleBackoffIdx = 0;
			} else if (idleBackoffIdx < IDLE_BACKOFF_MS.length - 1) {
				idleBackoffIdx += 1;
			}
			idleNextDueMs = Date.now() + IDLE_BACKOFF_MS[idleBackoffIdx];
		});
}

function refreshJobs() {
	apiGet("/api/jobs").then((r) => {
		if (!r || r.ok === false) {
			setPre("jobsList", r);
			PH.call("renderActiveJob", []);
			return;
		}
		renderJobsFromResponse(r);
	});
}

function ensureAutoRefresh(jobs) {
	var id = PH.call("getLiveJobId");
	var st = "";
	if (id && jobs && jobs.length) {
		const j = jobs.find((x) => String(x.job_id || "") === String(id)) || null;
		st = j ? String(j.status || "") : "";
	}
	if (st === "running" || st === "queued") PH.call("openLiveStream", id);
	else PH.call("closeLiveStream");

	if (activeJobId) {
		if (!autoRefreshTimer) {
			autoRefreshTimer = setInterval(() => {
				try {
					refreshJobs();
					__ph_w.refreshRuns();
				} catch (e) {
					setUiError(e);
				}
			}, 1500);
		}
		return;
	}
	if (autoRefreshTimer) {
		clearInterval(autoRefreshTimer);
		autoRefreshTimer = null;
	}
}

function computeCanonicalPreview(mode, issueId, commitMsg, patchPath) {
	var prefix =
		cfg && cfg.runner && cfg.runner.command
			? cfg.runner.command
			: ["python3", "scripts/am_patch.py"];
	var argv = prefix.slice();

	if (mode === "finalize_live") {
		argv.push("-f");
		argv.push(String(commitMsg || ""));
		return argv;
	}
	if (mode === "finalize_workspace") {
		argv.push("-w");
		argv.push(String(issueId || ""));
		return argv;
	}
	if (mode === "rerun_latest") {
		argv.push("-l");
		return argv;
	}

	argv.push(String(issueId || ""));
	argv.push(String(commitMsg || ""));
	argv.push(String(patchPath || ""));
	return argv;
}
