(() => {
	var w = /** @type {any} */ (window);
	var ui = w.AMP_PATCHHUB_UI;
	if (!ui) {
		ui = {};
		w.AMP_PATCHHUB_UI = ui;
	}

	function el(id) {
		return document.getElementById(id);
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

	function escapeHtml(s) {
		return String(s || "")
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#39;");
	}

	function normStepName(s) {
		return String(s || "")
			.replace(/\s+/g, " ")
			.trim();
	}

	function stageNameFromGateName(name) {
		name = String(name || "")
			.trim()
			.toUpperCase()
			.replace(/_/g, "-");
		if (!name) return "";
		return `GATE_${name}`;
	}

	function parseSkipInfo(ev, fallbackStage) {
		var msg = String((ev && ev.msg) || "").trim();
		var m = msg.match(/^gate_([a-z0-9_-]+)=SKIP \((.+)\)$/i);
		if (!m) return null;
		var stage = normStepName(fallbackStage || stageNameFromGateName(m[1]));
		if (!stage) return null;
		return {
			stage: stage,
			reason: String(m[2] || "").trim(),
		};
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

	var progressTimer = null;
	var lastProgressModel = null;
	var progressClock = {
		eventKey: "",
		monoMs: 0,
		clientMs: 0,
	};

	function isTimedGateStage(name) {
		name = normStepName(name);
		return name === "GATE_PYTEST" || name === "GATE_MYPY";
	}

	function parseMonoMs(value) {
		var num = Number(value);
		return Number.isFinite(num) ? num : null;
	}

	function syncProgressClock(events) {
		var lastKey = "";
		var lastMonoMs = null;
		for (let i = 0; i < (events || []).length; i++) {
			const ev = events[i];
			if (!ev || typeof ev !== "object") continue;
			const monoMs = parseMonoMs(ev.ts_mono_ms);
			if (monoMs === null) continue;
			lastMonoMs = monoMs;
			lastKey = `${String(ev.seq || "")}:${String(ev.type || "")}:${String(i)}`;
		}
		if (!lastKey || lastMonoMs === null) {
			progressClock = { eventKey: "", monoMs: 0, clientMs: 0 };
			return progressClock;
		}
		if (progressClock.eventKey !== lastKey) {
			progressClock = {
				eventKey: lastKey,
				monoMs: lastMonoMs,
				clientMs: Date.now(),
			};
		}
		return progressClock;
	}

	function formatDurationSeconds(startMonoMs, endMonoMs) {
		if (!Number.isFinite(startMonoMs) || !Number.isFinite(endMonoMs)) return "";
		var sec = (endMonoMs - startMonoMs) / 1000;
		if (sec < 0) return "";
		return String(Math.round(sec * 10) / 10);
	}

	function getStepDurationLabel(progress, name, st) {
		if (!progress || st === "skip") return "";
		var timing = progress.timing && progress.timing[name];
		var endMonoMs = null;
		var clock = null;
		var deltaMs = 0;
		if (!timing || !Number.isFinite(timing.startMonoMs)) return "";
		if (st !== "running" && st !== "ok" && st !== "fail") return "";
		endMonoMs = Number.isFinite(timing.stopMonoMs) ? timing.stopMonoMs : null;
		if (endMonoMs === null && st === "running") {
			clock = progress.clock || { monoMs: 0, clientMs: 0 };
			if (Number.isFinite(clock.monoMs) && Number.isFinite(clock.clientMs)) {
				deltaMs = Date.now() - clock.clientMs;
				if (deltaMs < 0) deltaMs = 0;
				endMonoMs = clock.monoMs + deltaMs;
			}
		}
		if (endMonoMs === null) return "";
		return formatDurationSeconds(timing.startMonoMs, endMonoMs);
	}

	function hasRunningTimedGate(progress) {
		var order = progress && progress.order ? progress.order : [];
		var state = progress && progress.state ? progress.state : {};
		for (let i = 0; i < order.length; i++) {
			const name = order[i];
			if (
				state[name] === "running" &&
				getStepDurationLabel(progress, name, "running")
			) {
				return true;
			}
		}
		return false;
	}

	function syncProgressTimer(progress) {
		lastProgressModel = progress || null;
		if (hasRunningTimedGate(progress)) {
			if (!progressTimer) {
				progressTimer = setInterval(() => {
					if (!lastProgressModel || !hasRunningTimedGate(lastProgressModel)) {
						syncProgressTimer(null);
						return;
					}
					renderProgressSteps(lastProgressModel);
				}, 1000);
			}
			return;
		}
		if (progressTimer) {
			clearInterval(progressTimer);
			progressTimer = null;
		}
	}

	function renderProgressSteps(progress) {
		var box = el("progressSteps");
		if (!box) return;

		var order = progress && progress.order ? progress.order : [];
		var state = progress && progress.state ? progress.state : {};
		var details = progress && progress.details ? progress.details : {};

		if (!order.length) {
			box.innerHTML = "";
			return;
		}

		var html = "";
		for (let i = 0; i < order.length; i++) {
			const name = order[i];
			const st = state[name] || "pending";
			const dotState = st === "skip" ? "pending" : st;
			const duration = getStepDurationLabel(progress, name, st);
			html += '<div class="step">';
			html += `<span class="dot ${escapeHtml(dotState)}"></span>`;
			html += `<span class="step-name">${escapeHtml(name)}</span>`;
			if (st === "running") {
				if (duration && isTimedGateStage(name)) {
					html += `<span class="pill running">RUNNING (${escapeHtml(duration)}s)</span>`;
				} else {
					html += '<span class="pill running">RUNNING</span>';
				}
			} else if (st === "skip") {
				const reason = String(details[name] || "").trim();
				const label = reason ? `SKIPPED (${reason})` : "SKIPPED";
				html += `<span class="pill">${escapeHtml(label)}</span>`;
			} else if (duration && isTimedGateStage(name)) {
				html += `<span class="pill">${escapeHtml(duration)}s</span>`;
			}
			html += "</div>";
		}

		box.innerHTML = html;
	}

	function renderProgressSummary(summaryLine) {
		var node = el("progressSummary");
		if (!node) return;
		node.textContent = summaryLine || "(idle)";
	}

	function refreshJobs() {
		apiGet("/api/jobs").then((r) => {
			if (!r || r.ok === false) {
				// Best-effort: do not crash UI on errors.
				return;
			}
			// renderActiveJob expects the full jobs list (it picks active from ui state).
			try {
				renderActiveJob(r.jobs || []);
			} catch (e) {}
		});
	}
	function apiGet(path) {
		return fetch(path, { headers: { Accept: "application/json" } }).then((r) =>
			r.text().then((t) => {
				try {
					return JSON.parse(t);
				} catch (e) {
					return { ok: false, error: "bad json", raw: t, status: r.status };
				}
			}),
		);
	}

	function getTrackedActiveJob(jobs) {
		if (!PH || typeof PH.call !== "function") return null;
		return PH.call("getTrackedActiveJob", jobs || []) || null;
	}

	function getTrackedActiveJobId(jobs) {
		if (!PH || typeof PH.call !== "function") return "";
		return String(PH.call("getTrackedActiveJobId", jobs || []) || "");
	}

	function summaryFromTerminalStatus(status) {
		status = String(status || "")
			.trim()
			.toLowerCase();
		if (status === "success") {
			return { text: "RESULT: SUCCESS", status: "success" };
		}
		if (status === "canceled") {
			return { text: "RESULT: CANCELED", status: "fail" };
		}
		if (status) {
			return { text: `RESULT: ${status.toUpperCase()}`, status: "fail" };
		}
		return { text: "RESULT: UNKNOWN", status: "fail" };
	}

	function pickProgressSummaryLineFromText(text) {
		var lines = String(text || "").split(/\r?\n/);
		for (let i = lines.length - 1; i >= 0; i--) {
			const s = String(lines[i] || "").trim();
			if (!s) continue;
			if (s.indexOf("RESULT:") === 0) return s;
			if (s.indexOf("STATUS:") === 0) return s;
			if (s.indexOf("FAIL:") === 0) return s;
			if (s.indexOf("OK:") === 0) return s;
			if (s.indexOf("DO:") === 0) return s;
		}
		return "(idle)";
	}

	function summaryFromTailText(text) {
		var line = pickProgressSummaryLineFromText(text);
		var upper = String(line || "")
			.trim()
			.toUpperCase();
		if (upper === "RESULT: SUCCESS") {
			return { text: line, status: "success" };
		}
		if (upper.indexOf("RESULT:") === 0 || upper.indexOf("FAIL:") === 0) {
			return { text: line, status: "fail" };
		}
		if (
			upper.indexOf("STATUS:") === 0 ||
			upper.indexOf("OK:") === 0 ||
			upper.indexOf("DO:") === 0
		) {
			return { text: line, status: "running" };
		}
		return { text: line, status: "idle" };
	}

	function deriveProgressFromEvents(events) {
		var order = [];
		var state = {};
		var details = {};
		var timing = {};
		var currentRunning = "";
		var resultStatus = "";
		var clock = syncProgressClock(events);

		function ensureStep(name) {
			if (!name) return;
			if (!Object.hasOwn(state, name)) {
				state[name] = "pending";
			}
			if (order.indexOf(name) < 0) order.push(name);
		}

		function ensureTiming(name, startMonoMs) {
			if (!isTimedGateStage(name) || !Number.isFinite(startMonoMs)) return;
			if (!Object.hasOwn(timing, name)) {
				timing[name] = { startMonoMs: startMonoMs, stopMonoMs: null };
			}
		}

		function setState(name, st) {
			name = normStepName(name);
			if (!name) return;
			ensureStep(name);
			state[name] = st;
		}

		function setSkip(name, reason) {
			name = normStepName(name);
			if (!name) return;
			ensureStep(name);
			state[name] = "skip";
			details[name] = String(reason || "").trim();
			delete timing[name];
		}

		for (let i = 0; i < (events || []).length; i++) {
			const ev = events[i];
			if (!ev || typeof ev !== "object") continue;
			const t = String(ev.type || "");
			const monoMs = parseMonoMs(ev.ts_mono_ms);

			if (t === "result") {
				resultStatus = ev.ok ? "success" : "fail";
				continue;
			}

			if (t !== "log") continue;

			const skipInfo = parseSkipInfo(ev, currentRunning);
			if (skipInfo) {
				setSkip(skipInfo.stage, skipInfo.reason);
				if (currentRunning === skipInfo.stage) currentRunning = "";
				continue;
			}

			const kind = String(ev.kind || "");
			if (kind !== "DO" && kind !== "OK" && kind !== "FAIL") continue;

			const stage = normStepName(ev.stage || "");
			if (!stage) continue;

			if (kind === "DO") {
				setState(stage, "running");
				ensureTiming(stage, monoMs);
				currentRunning = stage;
				continue;
			}

			if (kind === "OK") {
				if (state[stage] !== "skip") {
					setState(stage, "ok");
					if (
						Object.hasOwn(timing, stage) &&
						!Number.isFinite(timing[stage].stopMonoMs) &&
						Number.isFinite(monoMs)
					) {
						timing[stage].stopMonoMs = monoMs;
					}
				}
				if (currentRunning === stage) currentRunning = "";
				continue;
			}

			if (kind === "FAIL") {
				setState(stage, "fail");
				delete details[stage];
				if (
					Object.hasOwn(timing, stage) &&
					!Number.isFinite(timing[stage].stopMonoMs) &&
					Number.isFinite(monoMs)
				) {
					timing[stage].stopMonoMs = monoMs;
				}
				if (currentRunning === stage) currentRunning = "";
			}
		}

		if (currentRunning) {
			for (let j = 0; j < order.length; j++) {
				const nm = order[j];
				if (state[nm] === "running" && nm !== currentRunning) {
					state[nm] = "pending";
				}
			}
		}

		for (let k = 0; k < order.length; k++) {
			const nm2 = order[k];
			if (!Object.hasOwn(state, nm2)) state[nm2] = "pending";
		}

		return {
			order: order,
			state: state,
			details: details,
			timing: timing,
			clock: clock,
			resultStatus: resultStatus,
		};
	}

	function deriveProgressSummaryFromEvents(events, progress, active) {
		var lastTerminal = null;
		var lastResult = null;
		var lastLog = null;
		for (let i = (events || []).length - 1; i >= 0; i--) {
			const ev = events[i];
			if (!ev || typeof ev !== "object") continue;
			const t = String(ev.type || "");
			if (t === "control" && String(ev.event || "") === "stream_end") {
				lastTerminal = ev;
				break;
			}
			if (t === "result") {
				lastResult = ev;
				break;
			}
			if (t === "log") {
				const skipInfo = parseSkipInfo(ev, ev.stage || "");
				if (skipInfo) {
					return {
						text: `SKIP: ${skipInfo.stage} (${skipInfo.reason})`,
						status: "running",
					};
				}
				const kind = String(ev.kind || "");
				if (kind === "DO" || kind === "OK" || kind === "FAIL") {
					lastLog = ev;
					break;
				}
			}
		}

		if (lastTerminal) {
			return summaryFromTerminalStatus(lastTerminal.status);
		}

		if (lastResult) {
			return {
				text: lastResult.ok ? "RESULT: SUCCESS" : "RESULT: FAIL",
				status: lastResult.ok ? "success" : "fail",
			};
		}

		if (lastLog) {
			const stage = normStepName(lastLog.stage || "");
			const kind = String(lastLog.kind || "");
			if (
				kind === "OK" &&
				progress &&
				progress.state &&
				progress.state[stage] === "skip"
			) {
				const reason = String(
					(progress.details && progress.details[stage]) || "",
				).trim();
				return {
					text: reason ? `SKIP: ${stage} (${reason})` : `SKIP: ${stage}`,
					status: "running",
				};
			}
			if (kind === "FAIL") {
				return { text: `FAIL: ${stage}`, status: "fail" };
			}
			if (kind === "OK") {
				return { text: `OK: ${stage}`, status: "running" };
			}
			if (kind === "DO") {
				return { text: `DO: ${stage}`, status: "running" };
			}
		}

		var activeStatus = "";
		if (active) {
			activeStatus = String(active.status || "")
				.trim()
				.toLowerCase();
			if (activeStatus === "queued") {
				return { text: "STATUS: QUEUED", status: "running" };
			}
			return { text: "STATUS: RUNNING", status: "running" };
		}

		if (progress && progress.order && progress.order.length) {
			return { text: "STATUS: RUNNING", status: "running" };
		}
		return { text: "(idle)", status: "idle" };
	}

	function setProgressSummaryState(summary) {
		var node = el("progressSummary");
		if (!node) return;
		var st = summary && summary.status ? String(summary.status) : "idle";
		if (st !== "success" && st !== "fail" && st !== "running") st = "idle";
		node.classList.remove("success", "fail", "running", "idle", "muted");
		node.classList.add(st);
		if (st === "idle") node.classList.add("muted");
	}

	var appliedJobKey = "";

	function renderAppliedFilesBlock(html, hidden) {
		var node = el("progressApplied");
		if (!node) return;
		node.classList.toggle("hidden", !!hidden);
		node.innerHTML = hidden ? "" : html;
	}

	function renderAppliedFilesUnavailable(statusText) {
		renderAppliedFilesBlock(
			'<div class="progress-applied-title">Applied files unavailable</div>' +
				`<div class="muted">${escapeHtml(statusText)}</div>`,
			false,
		);
	}

	function renderAppliedFiles(job) {
		var files = Array.isArray(job.applied_files) ? job.applied_files : [];
		if (!files.length) {
			renderAppliedFilesUnavailable("successful run with no applied file list");
			return;
		}
		var visible = files.slice(0, 8);
		var html = `<div class="progress-applied-title">Applied files (${files.length})</div>`;
		html += '<div class="progress-applied-list">';
		visible.forEach((path) => {
			html += `<div class="progress-applied-item">${escapeHtml(path)}</div>`;
		});
		if (files.length > visible.length) {
			html += `<div class="progress-applied-more">+${files.length - visible.length} more</div>`;
		}
		html += "</div>";
		renderAppliedFilesBlock(html, false);
	}

	function getCurrentLiveJobId() {
		var jobId = "";
		try {
			jobId = String(
				(PH && typeof PH.call === "function" && PH.call("getLiveJobId")) || "",
			);
		} catch (e) {
			jobId = "";
		}
		if (jobId) return jobId;
		try {
			jobId = String(
				(ui && typeof ui.getLiveJobId === "function" && ui.getLiveJobId()) ||
					"",
			);
		} catch (e) {
			jobId = "";
		}
		if (jobId) return jobId;
		try {
			jobId = String(localStorage.getItem("amp.liveJobId") || "");
		} catch (e) {
			jobId = "";
		}
		return jobId;
	}

	function refreshAppliedFilesForCurrentJob(summary, opts) {
		var status = summary && summary.status ? String(summary.status) : "idle";
		var force = !!(opts && opts.forceAppliedFilesRetry);
		var jobId = getCurrentLiveJobId();
		if (!jobId || status === "idle" || status === "running") {
			appliedJobKey = "";
			renderAppliedFilesBlock("", true);
			return Promise.resolve();
		}
		var key = `${jobId}:${status}`;
		if (!force && appliedJobKey === key) return Promise.resolve();
		appliedJobKey = key;
		if (status !== "success") {
			renderAppliedFilesUnavailable(`result=${status}`);
			return Promise.resolve();
		}
		return apiGet(`/api/jobs/${encodeURIComponent(jobId)}`).then((r) => {
			if (!r || r.ok === false || !r.job) {
				renderAppliedFilesUnavailable("job detail unavailable");
				return;
			}
			renderAppliedFiles(r.job || {});
		});
	}

	function updateProgressPanelFromEvents(opts) {
		var jobs = opts && Array.isArray(opts.jobs) ? opts.jobs : [];
		var events = ui.liveEvents || [];
		var active = getTrackedActiveJob(jobs);
		var progress = deriveProgressFromEvents(events);
		renderProgressSteps(progress);
		renderActiveJob(jobs);
		var summary = deriveProgressSummaryFromEvents(events, progress, active);
		renderProgressSummary(summary.text);
		setProgressSummaryState(summary);
		return refreshAppliedFilesForCurrentJob(summary, opts);
	}

	function refreshStats() {
		apiGet("/api/debug/diagnostics").then((r) => {
			if (!r || r.ok === false) {
				setPre("stats", r);
				return;
			}
			var s = r.stats || {};
			var all = s.all_time || {};
			var lines = [];
			lines.push({ k: "all_time.total", v: String(all.total || 0) });
			lines.push({ k: "all_time.success", v: String(all.success || 0) });
			lines.push({ k: "all_time.fail", v: String(all.fail || 0) });
			lines.push({ k: "all_time.unknown", v: String(all.unknown || 0) });
			lines.push({ k: "all_time.canceled", v: String(all.canceled || 0) });

			(s.windows || []).forEach((w) => {
				var d = w.days;
				lines.push({ k: `${String(d)}d.total`, v: String(w.total || 0) });
				lines.push({ k: `${String(d)}d.success`, v: String(w.success || 0) });
				lines.push({ k: `${String(d)}d.fail`, v: String(w.fail || 0) });
				lines.push({ k: `${String(d)}d.unknown`, v: String(w.unknown || 0) });
				lines.push({ k: `${String(d)}d.canceled`, v: String(w.canceled || 0) });
			});

			el("stats").innerHTML = lines
				.map(
					(x) =>
						`<div class="rowline"><span class="k">${escapeHtml(x.k)}</span>` +
						`<span class="v">${escapeHtml(x.v)}</span></div>`,
				)
				.join("");
		});
	}

	function renderActiveJob(jobs) {
		var active = getTrackedActiveJob(jobs);
		var activeStatus = "";
		activeJobId = getTrackedActiveJobId(jobs) || null;
		w.activeJobId = activeJobId;
		var queued = (jobs || []).filter((j) => j.status === "queued");
		var jidEnc = "";

		var box = el("activeJob");
		if (!box) return;

		if (!active && queued.length === 0) {
			box.innerHTML = '<div class="muted">(none)</div>';
			return;
		}

		var html = "";
		if (active) {
			activeStatus = String(active.status || "running").toLowerCase();
			jidEnc = encodeURIComponent(active.job_id || "");
			let elapsed = "";
			if (PH && typeof PH.call === "function") {
				elapsed = String(
					PH.call(
						"jobSummaryDurationSeconds",
						active.started_utc,
						active.ended_utc,
					) || "",
				);
			}
			html +=
				`<div><b>${escapeHtml(activeStatus)}</b> ` +
				`${escapeHtml(active.job_id || "")}</div>`;
			html +=
				`<div class="muted">mode=${escapeHtml(active.mode || "")} ` +
				`issue=${escapeHtml(active.issue_id || "")}` +
				(elapsed ? ` elapsed=${escapeHtml(elapsed)}s` : "") +
				"</div>";
			html +=
				'<div class="row"><button class="btn btn-small" id="cancelActive">Cancel</button>';
			if (activeStatus === "running") {
				html +=
					'<button class="btn btn-small" id="hardStopActive">Hard stop AMP</button>';
			}
			html +=
				'<a class="linklike" href="/api/jobs/' +
				jidEnc +
				'/log_tail?lines=200">log</a></div>';
		}

		if (queued.length) {
			html += `<div style="margin-top:6px"><b>queued</b>: ${String(queued.length)}</div>`;
		}

		box.innerHTML = html;

		var cancelBtn = el("cancelActive");
		if (cancelBtn && active && active.job_id) {
			cancelBtn.addEventListener("click", () => {
				apiPost(
					`/api/jobs/${encodeURIComponent(active.job_id)}/cancel`,
					{},
				).then((resp) => {
					if (!resp || resp.ok === false) {
						setUiError(String((resp && resp.error) || "Cannot cancel"));
					}
					refreshJobs();
				});
			});
		}

		var hardStopBtn = el("hardStopActive");
		if (hardStopBtn && active && active.job_id) {
			hardStopBtn.addEventListener("click", () => {
				apiPost(
					`/api/jobs/${encodeURIComponent(active.job_id)}/hard_stop`,
					{},
				).then((resp) => {
					if (!resp || resp.ok === false) {
						setUiError(String((resp && resp.error) || "Cannot hard stop"));
					}
					refreshJobs();
				});
			});
		}
	}

	// Exports
	var PH = w.PH;
	if (PH && typeof PH.register === "function") {
		PH.register("progress", {
			deriveProgressFromEvents,
			deriveProgressSummaryFromEvents,
			setProgressSummaryState,
			updateProgressPanelFromEvents,
			refreshStats,
			renderActiveJob,
		});
	}
	ui.deriveProgressFromEvents = deriveProgressFromEvents;
	ui.deriveProgressSummaryFromEvents = deriveProgressSummaryFromEvents;
	ui.setProgressSummaryState = setProgressSummaryState;
	ui.updateProgressPanelFromEvents = updateProgressPanelFromEvents;
	ui.refreshStats = refreshStats;
	ui.renderActiveJob = renderActiveJob;
})();
