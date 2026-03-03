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

			var commit = PH.call("jobSummaryCommit", j.commit_message || "");
			var patchName = PH.call("jobSummaryPatchName", j.patch_path || "");

			var metaParts = [];
			metaParts.push(`mode=${String(j.mode || "")}`);
			if (patchName) metaParts.push(`patch=${patchName}`);

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
			if (commit) {
				line += '<div class="job-title">' + escapeHtml(commit) + "</div>";
			}
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
	if (activeJobId) return;
	var now = Date.now();
	if (idleNextDueMs && now < idleNextDueMs) return;

	var runsIssue = String(el("runsIssue").value || "").trim();
	var runsResult = String(el("runsResult").value || "");
	var canCondRuns = !runsIssue && !runsResult;

	var pRuns;
	if (canCondRuns) {
		const q = ["limit=80"];
		if (idleSigs.runs) q.push("since_sig=" + encodeURIComponent(idleSigs.runs));
		pRuns = apiGet(`/api/runs?${q.join("&")}`).then((r) => {
			if (!r || r.ok === false) return { changed: false, sig: idleSigs.runs };
			var sig = String(r.sig || "");
			if (sig) idleSigs.runs = sig;
			if (r.unchanged) return { changed: false, sig: sig };
			__ph_w.renderRunsFromResponse(r);
			return { changed: true, sig: sig };
		});
	} else {
		pRuns = Promise.resolve(null);
	}

	var qsHdr = "";
	if (idleSigs.hdr) qsHdr = "?since_sig=" + encodeURIComponent(idleSigs.hdr);
	var pHdr = apiGet("/api/debug/diagnostics" + qsHdr).then((d) => {
		if (!d || d.ok === false) return { changed: false, sig: idleSigs.hdr };
		var sig = String(d.sig || "");
		if (sig) idleSigs.hdr = sig;
		if (d.unchanged) return { changed: false, sig: sig };
		var base = "";
		if (cfg && cfg.server && cfg.server.host && cfg.server.port) {
			base = "server: " + cfg.server.host + ":" + cfg.server.port;
		}
		renderHeaderFromDiagnostics(d, base);
		return { changed: true, sig: sig };
	});

	Promise.all([refreshJobsIdle(), pRuns, pHdr]).then((vals) => {
		var changed = false;
		for (let i = 0; i < vals.length; i++) {
			const v = vals[i];
			if (v && v.changed) changed = true;
		}
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
