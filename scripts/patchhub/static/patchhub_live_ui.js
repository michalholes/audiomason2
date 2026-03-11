(() => {
	var w = /** @type {any} */ (window);
	var ui = w.AMP_PATCHHUB_UI;
	if (!ui) {
		ui = {};
		w.AMP_PATCHHUB_UI = ui;
	}

	// Module-local state. Split UI modules must not rely on app.js locals.
	var liveStreamJobId = null;
	var liveES = null;
	var liveEvents = [];
	var MAX_LIVE_EVENTS = 2000;
	var liveRenderTimer = null;
	var liveLevel = "normal";
	var liveTerminalInfo = null;
	var workspacesVisible = false;
	var runsVisible = false;
	var jobsVisible = false;
	ui.liveEvents = liveEvents;

	function safeExport(name, fn) {
		ui[name] = (...args) => {
			try {
				return fn(...args);
			} catch (e) {
				console.error(`PatchHub UI module error in ${name}:`, e);
				return undefined;
			}
		};
	}

	function el(id) {
		return document.getElementById(id);
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
	function loadLiveJobId() {
		var v = null;
		try {
			v = localStorage.getItem("amp.liveJobId");
		} catch (e) {
			v = null;
		}
		if (!v) return null;
		return String(v);
	}

	function saveLiveJobId(jobId) {
		try {
			localStorage.setItem("amp.liveJobId", String(jobId || ""));
		} catch (e) {}
	}

	function loadLiveLevel() {
		var v = null;
		try {
			v = localStorage.getItem("amp.liveLogLevel");
		} catch (e) {
			v = null;
		}
		if (!v) return;
		setLiveLevel(v);
	}

	function getLiveLevel() {
		return liveLevel;
	}

	function setLiveLevel(v) {
		v = String(v || "").trim();
		if (["quiet", "normal", "warning", "verbose", "debug"].indexOf(v) < 0) {
			v = "normal";
		}
		liveLevel = v;
		try {
			localStorage.setItem("amp.liveLogLevel", liveLevel);
		} catch (e) {}
		return liveLevel;
	}

	function loadUiVisibility() {
		var v = null;
		try {
			v = localStorage.getItem("amp.ui.workspacesVisible");
		} catch (e) {
			v = null;
		}
		if (v === "1") workspacesVisible = true;
		else if (v === "0") workspacesVisible = false;

		v = null;
		try {
			v = localStorage.getItem("amp.ui.runsVisible");
		} catch (e) {
			v = null;
		}
		if (v === "1") runsVisible = true;
		else if (v === "0") runsVisible = false;

		v = null;
		try {
			v = localStorage.getItem("amp.ui.jobsVisible");
		} catch (e) {
			v = null;
		}
		if (v === "1") jobsVisible = true;
		else if (v === "0") jobsVisible = false;

		setWorkspacesVisible(workspacesVisible);
		setRunsVisible(runsVisible);
		setJobsVisible(jobsVisible);
		return {
			workspacesVisible: workspacesVisible,
			runsVisible: runsVisible,
			jobsVisible: jobsVisible,
		};
	}

	function saveWorkspacesVisible(v) {
		try {
			localStorage.setItem("amp.ui.workspacesVisible", v ? "1" : "0");
		} catch (e) {}
	}

	function saveRunsVisible(v) {
		try {
			localStorage.setItem("amp.ui.runsVisible", v ? "1" : "0");
		} catch (e) {}
	}

	function saveJobsVisible(v) {
		try {
			localStorage.setItem("amp.ui.jobsVisible", v ? "1" : "0");
		} catch (e) {}
	}

	function setWorkspacesVisible(v) {
		workspacesVisible = !!v;
		var wrap = el("workspacesWrap");
		var btn = el("workspacesCollapse");
		if (wrap) wrap.classList.toggle("hidden", !workspacesVisible);
		if (btn) btn.textContent = workspacesVisible ? "Hide" : "Show";
	}

	function setRunsVisible(v) {
		runsVisible = !!v;
		var wrap = el("runsWrap");
		var btn = el("runsCollapse");
		if (wrap) wrap.classList.toggle("hidden", !runsVisible);
		if (btn) btn.textContent = runsVisible ? "Hide" : "Show";
	}

	function setJobsVisible(v) {
		jobsVisible = !!v;
		var wrap = el("jobsWrap");
		var btn = el("jobsCollapse");
		if (wrap) wrap.classList.toggle("hidden", !jobsVisible);
		if (btn) btn.textContent = jobsVisible ? "Hide" : "Show";
	}

	function setLiveStreamStatus(text) {
		var box = el("liveStreamStatus");
		if (!box) return;
		box.textContent = String(text || "");
	}

	function getLiveJobId() {
		// Self-contained: do not reference app.js locals (separate module scope).
		var v = loadLiveJobId();
		if (v) return v;
		return null;
	}

	function isNonTerminalJobStatus(status) {
		status = String(status || "")
			.trim()
			.toLowerCase();
		return status === "queued" || status === "running";
	}

	function getTrackedLiveJobId() {
		var jobId = getLiveJobId();
		if (jobId) return String(jobId);
		if (liveStreamJobId) return String(liveStreamJobId);
		return "";
	}

	function hasTrackedLiveContext(trackedId) {
		if (!trackedId) return false;
		if (liveStreamJobId && String(liveStreamJobId) === trackedId) {
			return true;
		}
		if (liveES && getTrackedLiveJobId() === trackedId) {
			return true;
		}
		if ((liveEvents || []).length > 0 && getTrackedLiveJobId() === trackedId) {
			return true;
		}
		return String(w.__ph_last_enqueued_job_id || "") === trackedId;
	}

	function deriveTrackedFallbackStatus() {
		for (let i = liveEvents.length - 1; i >= 0; i--) {
			const ev = liveEvents[i];
			if (!ev || typeof ev !== "object") continue;
			if (String(ev.type || "") === "control") continue;
			if (
				String(ev.type || "") === "log" &&
				String(ev.msg || "")
					.trim()
					.toLowerCase() === "queued"
			) {
				return "queued";
			}
			return "running";
		}
		return "queued";
	}

	function deriveTrackedFallbackMeta() {
		var meta = { mode: "", issue_id: "" };
		for (let i = 0; i < liveEvents.length; i++) {
			const ev = liveEvents[i];
			if (!ev || typeof ev !== "object") continue;
			if (String(ev.type || "") !== "hello") continue;
			meta.mode = String(ev.runner_mode || "");
			meta.issue_id = String(ev.issue_id || "");
			break;
		}
		if (!meta.mode) {
			meta.mode = String(w.__ph_last_enqueued_mode || "");
		}
		return meta;
	}

	function getTrackedActiveJob(jobs) {
		var trackedId = getTrackedLiveJobId();
		var match = null;
		var fallbackMeta = null;
		if (!trackedId) return null;
		if (
			liveTerminalInfo &&
			String(liveTerminalInfo.jobId || "") === trackedId
		) {
			return null;
		}
		if (Array.isArray(jobs) && jobs.length) {
			match = jobs.find((job) => String(job.job_id || "") === trackedId);
			if (match) {
				return isNonTerminalJobStatus(match.status) ? match : null;
			}
		}
		if (!hasTrackedLiveContext(trackedId)) {
			return null;
		}
		fallbackMeta = deriveTrackedFallbackMeta();
		return {
			job_id: trackedId,
			status: deriveTrackedFallbackStatus(),
			mode: fallbackMeta.mode,
			issue_id: fallbackMeta.issue_id,
		};
	}

	function getTrackedActiveJobId(jobs) {
		var tracked = getTrackedActiveJob(jobs);
		return tracked ? String(tracked.job_id || "") : "";
	}

	function hasTrackedActiveJob(jobs) {
		return !!getTrackedActiveJobId(jobs);
	}

	function rememberTerminalEvent(jobId, status, reason) {
		liveTerminalInfo = {
			jobId: String(jobId || ""),
			status: String(status || ""),
			reason: String(reason || ""),
		};
		liveEvents.push({
			type: "control",
			event: "stream_end",
			job_id: String(jobId || ""),
			status: String(status || ""),
			reason: String(reason || ""),
		});
		if (liveEvents.length > MAX_LIVE_EVENTS) {
			liveEvents.splice(0, liveEvents.length - MAX_LIVE_EVENTS);
		}
		scheduleLiveRender();
	}

	function closeLiveStream() {
		if (liveES) {
			try {
				liveES.close();
			} catch (e) {}
		}
		liveES = null;
		liveStreamJobId = null;
	}

	function filterLiveEvent(ev) {
		if (!ev) return false;
		var t = String(ev.type || "");
		if (t === "result") return true;
		if (t === "hello") return liveLevel === "debug";
		if (t !== "log") return liveLevel === "debug";

		if (ev.bypass === true) return true;

		var ch = String(ev.ch || "");
		var sev = String(ev.sev || "");
		var summary = ev.summary === true;

		if (liveLevel === "quiet") return summary;
		if (liveLevel === "debug") return true;

		if (ch === "CORE") return true;

		if (liveLevel === "normal") return false;

		if (liveLevel === "warning") return ch === "DETAIL" && sev === "WARNING";
		if (liveLevel === "verbose") {
			if (ch !== "DETAIL") return false;
			return sev === "WARNING" || sev === "INFO";
		}
		return false;
	}

	function compactJson(value) {
		try {
			return JSON.stringify(value);
		} catch (e) {
			return "{}";
		}
	}

	function formatLiveEvent(ev) {
		var t = String(ev.type || "");
		if (t === "hello") {
			return (
				`HELLO protocol=${String(ev.protocol || "")} ` +
				`mode=${String(ev.runner_mode || "")} ` +
				`issue=${String(ev.issue_id || "")}`
			);
		}
		if (t === "result") {
			const ok = ev.ok ? "SUCCESS" : "FAIL";
			return `RESULT: ${ok} rc=${String(ev.return_code)}`;
		}
		if (t === "reply") {
			const replyData =
				ev.data && typeof ev.data === "object" ? compactJson(ev.data) : "{}";
			return (
				`REPLY cmd=${String(ev.cmd || "")} ` +
				`cmd_id=${String(ev.cmd_id || "")} ` +
				`ok=${String(ev.ok === true)} data=${replyData}`
			);
		}
		if (t === "control") {
			return `CONTROL event=${String(ev.event || "")} ${compactJson(ev)}`;
		}

		var showPrefixes = liveLevel === "debug";
		var line = "";

		if (showPrefixes) {
			const parts = [];
			const stage = String(ev.stage || "");
			const kind = String(ev.kind || "");
			const sev = String(ev.sev || "");
			const msg = String(ev.msg || "");
			if (stage) parts.push(stage);
			if (kind) parts.push(kind);
			if (sev) parts.push(sev);
			parts.push(msg);
			line = parts.join(" | ");
		} else {
			line = String(ev.msg || "");
		}

		if (!line) {
			line = `JSON ${compactJson(ev)}`;
		}

		if (ev.stdout || ev.stderr) {
			const out = [];
			out.push(line);
			if (ev.stdout) out.push(`STDOUT:\n${String(ev.stdout)}`);
			if (ev.stderr) out.push(`STDERR:\n${String(ev.stderr)}`);
			return out.join("\n");
		}
		return line;
	}

	function renderLiveLog() {
		var box = el("liveLog");
		if (!box) return;
		var lines = [];
		for (let i = 0; i < liveEvents.length; i++) {
			const ev = liveEvents[i];
			if (!filterLiveEvent(ev)) continue;
			lines.push(formatLiveEvent(ev));
		}
		box.textContent = lines.join("\n");
		var wrap = box.parentElement;
		if (wrap && wrap.classList && wrap.classList.contains("card-tight")) {
			// no-op
		}
	}

	function scheduleLiveRender() {
		if (liveRenderTimer) return;
		liveRenderTimer = setTimeout(() => {
			liveRenderTimer = null;
			renderLiveLog();
			if (ui.updateProgressPanelFromEvents) ui.updateProgressPanelFromEvents();
		}, 50);
	}

	function updateProgressFromEvents() {
		var box = el("activeStage");
		if (!box) return;
		for (let i = liveEvents.length - 1; i >= 0; i--) {
			const ev = liveEvents[i];
			if (!ev) continue;
			if (String(ev.type || "") === "result") {
				box.textContent = ev.ok ? "RESULT: SUCCESS" : "RESULT: FAIL";
				return;
			}
			if (String(ev.type || "") === "log") {
				const stage = String(ev.stage || "");
				const kind = String(ev.kind || "");
				if (stage || kind) {
					box.textContent = (stage ? stage : "") + (kind ? ` / ${kind}` : "");
					return;
				}
			}
		}
	}

	function openLiveStream(jobId) {
		if (!jobId) {
			closeLiveStream();
			liveEvents = [];
			ui.liveEvents = liveEvents;
			ui.liveEvents = liveEvents;
			renderLiveLog();
			if (ui.updateProgressPanelFromEvents) ui.updateProgressPanelFromEvents();
			setLiveStreamStatus("");
			return;
		}
		jobId = String(jobId);

		if (liveStreamJobId === jobId && liveES) return;

		closeLiveStream();
		liveStreamJobId = jobId;
		liveTerminalInfo = null;
		liveEvents = [];
		ui.liveEvents = liveEvents;
		renderLiveLog();
		if (ui.updateProgressPanelFromEvents) ui.updateProgressPanelFromEvents();
		setLiveStreamStatus("connecting...");

		var url = `/api/jobs/${encodeURIComponent(jobId)}/events`;
		var es = new EventSource(url);
		liveES = es;

		es.onmessage = (e) => {
			if (!e || !e.data) return;
			var obj = null;
			try {
				obj = JSON.parse(String(e.data));
			} catch (err) {
				obj = null;
			}
			if (!obj) return;
			liveEvents.push(obj);
			if (liveEvents.length > MAX_LIVE_EVENTS) {
				liveEvents.splice(0, liveEvents.length - MAX_LIVE_EVENTS);
			}
			scheduleLiveRender();
			setLiveStreamStatus("streaming");
		};

		es.addEventListener("end", (e) => {
			var reason = "";
			var status = "";
			if (e && e.data) {
				try {
					const p = JSON.parse(String(e.data || "{}"));
					if (p && typeof p === "object") {
						reason = String(p.reason || "");
						status = String(p.status || "");
					}
				} catch (err) {}
			}
			rememberTerminalEvent(jobId, status, reason);
			var msg = "ended";
			if (status) msg += ` (${status})`;
			if (reason) msg += ` [${reason}]`;
			setLiveStreamStatus(msg);
			try {
				es.close();
			} catch (e2) {}
			if (liveES === es) {
				liveES = null;
			}
			if (ui.updateProgressPanelFromEvents) {
				ui.updateProgressPanelFromEvents({ forceAppliedFilesRetry: true });
			}
		});

		es.onerror = () => {
			apiGet(`/api/jobs/${encodeURIComponent(jobId)}`).then((r) => {
				if (!r || r.ok === false) {
					closeLiveStream();
					setLiveStreamStatus("ended [job_not_found]");
					return;
				}
				var j = r.job || {};
				var st = String(j.status || "");
				if (st && !isNonTerminalJobStatus(st)) {
					rememberTerminalEvent(jobId, st, "job_completed");
					closeLiveStream();
					setLiveStreamStatus(`ended (${st}) [job_completed]`);
					if (ui.updateProgressPanelFromEvents) {
						ui.updateProgressPanelFromEvents({ forceAppliedFilesRetry: true });
					}
					return;
				}
				setLiveStreamStatus("reconnecting...");
			});
		};
	}

	function jobSummaryCommit(msg) {
		msg = String(msg || "");
		msg = msg.replace(/\s+/g, " ").trim();
		if (!msg) return "";
		if (msg.length <= 60) return msg;
		return `${msg.slice(0, 57)}...`;
	}

	function jobSummaryPatchName(p) {
		p = String(p || "").trim();
		if (!p) return "";
		p = p.replace(/\\/g, "/");
		var idx = p.lastIndexOf("/");
		if (idx >= 0) return p.slice(idx + 1);
		return p;
	}

	function jobSummaryDurationSeconds(startUtc, endUtc) {
		if (!startUtc || !endUtc) return "";
		var a = new Date(String(startUtc));
		var b = new Date(String(endUtc));
		if (isNaN(a.getTime()) || isNaN(b.getTime())) return "";
		var sec = (b.getTime() - a.getTime()) / 1000;
		if (sec < 0) return "";
		var s = Math.round(sec * 10) / 10;
		return String(s);
	}

	// Exports
	var PH = w.PH;
	if (PH && typeof PH.register === "function") {
		PH.register("live", {
			loadLiveJobId,
			saveLiveJobId,
			loadLiveLevel,
			getLiveLevel,
			setLiveLevel,
			loadUiVisibility,
			saveWorkspacesVisible,
			saveRunsVisible,
			saveJobsVisible,
			setWorkspacesVisible,
			setRunsVisible,
			setJobsVisible,
			setLiveStreamStatus,
			getLiveJobId,
			isNonTerminalJobStatus,
			getTrackedActiveJob,
			getTrackedActiveJobId,
			hasTrackedActiveJob,
			closeLiveStream,
			renderLiveLog,
			filterLiveEvent,
			formatLiveEvent,
			updateProgressFromEvents,
			openLiveStream,
			jobSummaryCommit,
			jobSummaryPatchName,
			jobSummaryDurationSeconds,
		});
	}
	safeExport("loadLiveJobId", loadLiveJobId);
	safeExport("saveLiveJobId", saveLiveJobId);
	safeExport("loadLiveLevel", loadLiveLevel);
	safeExport("getLiveLevel", getLiveLevel);
	safeExport("setLiveLevel", setLiveLevel);
	safeExport("loadUiVisibility", loadUiVisibility);
	safeExport("saveWorkspacesVisible", saveWorkspacesVisible);
	safeExport("saveRunsVisible", saveRunsVisible);
	safeExport("saveJobsVisible", saveJobsVisible);
	safeExport("setWorkspacesVisible", setWorkspacesVisible);
	safeExport("setRunsVisible", setRunsVisible);
	safeExport("setJobsVisible", setJobsVisible);
	safeExport("setLiveStreamStatus", setLiveStreamStatus);
	safeExport("getLiveJobId", getLiveJobId);
	safeExport("isNonTerminalJobStatus", isNonTerminalJobStatus);
	safeExport("getTrackedActiveJob", getTrackedActiveJob);
	safeExport("getTrackedActiveJobId", getTrackedActiveJobId);
	safeExport("hasTrackedActiveJob", hasTrackedActiveJob);
	safeExport("closeLiveStream", closeLiveStream);
	ui.filterLiveEvent = filterLiveEvent;
	ui.formatLiveEvent = formatLiveEvent;
	safeExport("renderLiveLog", renderLiveLog);
	ui.updateProgressFromEvents = updateProgressFromEvents;
	ui.openLiveStream = openLiveStream;
	ui.jobSummaryCommit = jobSummaryCommit;
	ui.jobSummaryPatchName = jobSummaryPatchName;
	ui.jobSummaryDurationSeconds = jobSummaryDurationSeconds;
})();
