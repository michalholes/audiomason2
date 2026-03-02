(() => {
	// Load split UI helpers (monolith mitigation).
	// These scripts attach to window.AMP_PATCHHUB_UI.
	document.write('<script src="/static/patchhub_progress_ui.js"></script>');
	document.write('<script src="/static/patchhub_live_ui.js"></script>');

	window.AMP_PATCHHUB_UI = window.AMP_PATCHHUB_UI || {};
	const AMP_UI = window.AMP_PATCHHUB_UI;

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

	function el(id) {
		return document.getElementById(id);
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

	function renderRunsFromResponse(r) {
		runsCache = r.runs || [];

		var html = runsCache
			.map((x, idx) => {
				var log = x.log_rel_path || "";
				var link = log
					? '<a class="linklike" href="/api/fs/download?path=' +
						encodeURIComponent(log) +
						'">log</a>'
					: "";
				var sel =
					selectedRun &&
					selectedRun.issue_id === x.issue_id &&
					selectedRun.mtime_utc === x.mtime_utc
						? " *"
						: "";
				return (
					'<div class="item runitem" data-idx="' +
					String(idx) +
					'">' +
					'<span class="name">#' +
					String(x.issue_id) +
					" " +
					escapeHtml(String(x.result || "")) +
					sel +
					"</span>" +
					'<span class="actions">' +
					link +
					' <span class="muted">' +
					formatLocalTime(x.mtime_utc || "") +
					"</span></span>" +
					"</div>"
				);
			})
			.join("");

		el("runsList").innerHTML = html || '<div class="muted">(none)</div>';

		Array.from(el("runsList").querySelectorAll(".runitem .name")).forEach(
			(node) => {
				node.addEventListener("click", () => {
					var item = node.parentElement;
					var idx = parseInt(item.getAttribute("data-idx") || "-1", 10);
					if (idx >= 0 && idx < runsCache.length) {
						selectedRun = runsCache[idx];
						renderIssueDetail();
						refreshRuns();
					}
				});
			},
		);
	}

	function refreshRuns() {
		var q = [];
		var issue = String(el("runsIssue").value || "").trim();
		var res = String(el("runsResult").value || "");
		if (issue) q.push(`issue_id=${encodeURIComponent(issue)}`);
		if (res) q.push(`result=${encodeURIComponent(res)}`);
		q.push("limit=80");

		apiGet(`/api/runs?${q.join("&")}`).then((r) => {
			if (!r || r.ok === false) {
				setPre("runsList", r);
				return;
			}
			renderRunsFromResponse(r);
		});
	}

	function refreshLastRunLog() {
		apiGet("/api/runs?limit=1").then((r) => {
			if (!r || r.ok === false) {
				setPre("lastRunLog", r);
				return;
			}
			var runs = r.runs || [];
			if (!runs.length) {
				lastRunLogPath = "";
				setPre("lastRunLog", "");
				return;
			}
			var logRel = String(runs[0].log_rel_path || "");
			if (!logRel) {
				lastRunLogPath = "";
				setPre("lastRunLog", "(no log path)");
				return;
			}

			lastRunLogPath = logRel;
			var box = el("lastRunLog");
			var wantFollow = isNearBottom(box, 24);
			var url =
				"/api/fs/read_text?path=" +
				encodeURIComponent(logRel) +
				"&tail_lines=2000";
			apiGet(url).then((rt) => {
				if (!rt || rt.ok === false) {
					setPre("lastRunLog", rt);
					return;
				}
				var t = String(rt.text || "");
				if (rt.truncated) t += "\n\n[TRUNCATED]";
				setPre("lastRunLog", t);
				if (wantFollow && box) box.scrollTop = box.scrollHeight;
			});
		});
	}

	function refreshTail(lines) {
		tailLines = lines || tailLines || 200;

		var idleGuardOn = !!(cfg && cfg.ui && cfg.ui.clear_output_on_autofill);
		var jid = uiCall("getLiveJobId");
		if (!jid && suppressIdleOutput && idleGuardOn) {
			setPre("tail", "");
			uiCall("updateProgressPanelFromEvents");
			return;
		}

		var linesQ = encodeURIComponent(String(tailLines));
		var url = `/api/runner/tail?lines=${linesQ}`;
		if (jid) {
			url =
				"/api/jobs/" +
				encodeURIComponent(String(jid)) +
				"/log_tail?lines=" +
				linesQ;
		}
		apiGet(url).then((r) => {
			if (!r || r.ok === false) {
				setPre("tail", r);
				return;
			}
			var t = String(r.tail || "");
			setPre("tail", t);
		});
	}

	function parseProgressFromText(text) {
		var lines = String(text || "").split(/\r?\n/);
		var order = [];
		var state = {};
		var currentRunning = "";

		function normStepName(s) {
			return String(s || "")
				.replace(/\s+/g, " ")
				.trim();
		}

		function ensureStep(name) {
			if (!name) return;
			if (!Object.hasOwn(state, name)) {
				state[name] = "pending";
			}
			if (order.indexOf(name) < 0) order.push(name);
		}

		function setState(name, st) {
			name = normStepName(name);
			if (!name) return;
			ensureStep(name);
			state[name] = st;
		}

		for (let i = 0; i < lines.length; i++) {
			const raw = String(lines[i] || "");
			const s = raw.trim();
			if (!s) continue;

			if (s.indexOf("DO:") === 0) {
				const stepDo = normStepName(s.slice(3));
				setState(stepDo, "running");
				currentRunning = stepDo;
				continue;
			}

			if (s.indexOf("OK:") === 0) {
				const stepOk = normStepName(s.slice(3));
				setState(stepOk, "ok");
				if (currentRunning === stepOk) currentRunning = "";
				continue;
			}

			if (s.indexOf("FAIL:") === 0) {
				const stepFail = normStepName(s.slice(5));
				setState(stepFail, "fail");
				if (currentRunning === stepFail) currentRunning = "";
				continue;
			}

			if (
				s.indexOf("ERROR:") === 0 ||
				s === "FAIL" ||
				s.indexOf("FAIL ") === 0
			) {
				if (currentRunning) setState(currentRunning, "fail");
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

		return { order: order, state: state };
	}

	function pickProgressSummaryLine(text) {
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

	function renderProgressSteps(progress) {
		var box = el("progressSteps");
		if (!box) return;

		var order = progress && progress.order ? progress.order : [];
		var state = progress && progress.state ? progress.state : {};

		if (!order.length) {
			box.innerHTML = "";
			return;
		}

		var html = "";
		for (let i = 0; i < order.length; i++) {
			const name = order[i];
			const st = state[name] || "pending";
			html += '<div class="step">';
			html += `<span class="dot ${escapeHtml(st)}"></span>`;
			html += `<span class="step-name">${escapeHtml(name)}</span>`;
			if (st === "running") {
				html += '<span class="pill running">RUNNING</span>';
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

	function updateShortProgressFromText(text) {
		var progress = parseProgressFromText(text);
		renderProgressSteps(progress);
		renderProgressSummary(pickProgressSummaryLine(text));
	}

	function normStepName(s) {
		return String(s || "")
			.replace(/\s+/g, " ")
			.trim();
	}

	function renderJobsFromResponse(r) {
		var jobs = r.jobs || [];

		var active = jobs.find((j) => j.status === "running") || null;
		var activeId = active ? String(active.job_id || "") : "";

		var idleAutoSelect = !!(cfg && cfg.ui && cfg.ui.idle_auto_select_last_job);

		if (!selectedJobId) {
			const saved = uiCall("loadLiveJobId");
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
		uiCall("renderActiveJob", jobs);
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

				var commit = uiCall("jobSummaryCommit", j.commit_message || "");
				var patchName = uiCall("jobSummaryPatchName", j.patch_path || "");

				var metaParts = [];
				metaParts.push(`mode=${String(j.mode || "")}`);
				if (patchName) metaParts.push(`patch=${patchName}`);

				var dur = uiCall(
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
			if (idleSigs.runs)
				q.push("since_sig=" + encodeURIComponent(idleSigs.runs));
			pRuns = apiGet(`/api/runs?${q.join("&")}`).then((r) => {
				if (!r || r.ok === false) return { changed: false, sig: idleSigs.runs };
				var sig = String(r.sig || "");
				if (sig) idleSigs.runs = sig;
				if (r.unchanged) return { changed: false, sig: sig };
				renderRunsFromResponse(r);
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
				uiCall("renderActiveJob", []);
				return;
			}
			renderJobsFromResponse(r);
		});
	}

	function ensureAutoRefresh(jobs) {
		var id = uiCall("getLiveJobId");
		var st = "";
		if (id && jobs && jobs.length) {
			const j = jobs.find((x) => String(x.job_id || "") === String(id)) || null;
			st = j ? String(j.status || "") : "";
		}
		if (st === "running" || st === "queued") uiCall("openLiveStream", id);
		else uiCall("closeLiveStream");

		if (activeJobId) {
			if (!autoRefreshTimer) {
				autoRefreshTimer = setInterval(() => {
					refreshJobs();
					refreshRuns();
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

	function setStartFormState(state) {
		var issueEnabled = !!(state && state.issue_id);
		var msgEnabled = !!(state && state.commit_message);
		var patchEnabled = !!(state && state.patch_path);

		el("issueId").disabled = !issueEnabled;
		el("commitMsg").disabled = !msgEnabled;
		el("patchPath").disabled = !patchEnabled;
		var browse = el("browsePatch");
		if (browse) browse.disabled = !patchEnabled;
	}

	function validateAndPreview() {
		var mode = String(el("mode").value || "patch");
		var issueId = String(el("issueId").value || "").trim();
		var commitMsg = String(el("commitMsg").value || "").trim();
		var patchPath = normalizePatchPath(String(el("patchPath").value || ""));
		el("patchPath").value = patchPath;

		var raw = getRawCommand();

		var modeRules = null;
		if (mode === "patch" || mode === "repair") {
			modeRules = { issue_id: true, commit_message: true, patch_path: true };
		} else if (mode === "finalize_live") {
			modeRules = { issue_id: false, commit_message: true, patch_path: false };
		} else if (mode === "finalize_workspace") {
			modeRules = { issue_id: true, commit_message: false, patch_path: false };
		} else if (mode === "rerun_latest") {
			modeRules = { issue_id: false, commit_message: false, patch_path: false };
		} else {
			modeRules = { issue_id: true, commit_message: true, patch_path: true };
		}
		setStartFormState(modeRules);

		var ok = true;

		var canonical = null;
		var preview = null;

		if (raw) {
			ok = !parseInFlight && !!lastParsed && lastParsedRaw === raw;
			if (ok) {
				const p = lastParsed.parsed || {};
				const c = lastParsed.canonical || {};
				canonical = c.argv ? c.argv : [];
				const pMode = p.mode ? p.mode : mode;
				const pIssue = p.issue_id ? p.issue_id : issueId;
				const pMsg = p.commit_message ? p.commit_message : commitMsg;
				const pPatch = p.patch_path ? p.patch_path : patchPath;
				preview = {
					mode: pMode,
					issue_id: pIssue,
					commit_message: pMsg,
					patch_path: pPatch,
					canonical_argv: canonical,
					raw_command: raw,
				};
			} else {
				canonical = [];
				preview = {
					mode: mode,
					issue_id: issueId,
					commit_message: commitMsg,
					patch_path: patchPath,
					canonical_argv: canonical,
					raw_command: raw,
					parse_status: parseInFlight ? "parsing" : "needs_parse",
				};
			}
		} else {
			if (mode === "patch" || mode === "repair") {
				ok = !!commitMsg && !!patchPath;
			} else if (mode === "finalize_live") {
				ok = !!commitMsg;
			} else if (mode === "finalize_workspace") {
				ok = !!issueId && /^[0-9]+$/.test(issueId);
			} else if (mode === "rerun_latest") {
				ok = true;
			}

			canonical = computeCanonicalPreview(mode, issueId, commitMsg, patchPath);
			preview = {
				mode: mode,
				issue_id: issueId,
				commit_message: commitMsg,
				patch_path: patchPath,
				canonical_argv: canonical,
			};
		}
		setPre("previewRight", preview);
		el("enqueueBtn").disabled = !ok;

		var hint2 = el("enqueueHint");
		if (hint2) {
			if (raw) {
				hint2.textContent = "";
			} else {
				if (ok) {
					hint2.textContent = "";
				} else if (mode === "finalize_live") {
					hint2.textContent = "missing message";
				} else if (mode === "finalize_workspace") {
					hint2.textContent = "missing issue id";
				} else if (mode === "patch" || mode === "repair") {
					hint2.textContent = "missing commit message or patch path";
				} else {
					hint2.textContent = "missing fields";
				}
			}
		}
	}

	function enqueue() {
		var mode = String(el("mode").value || "patch");
		var body = {
			mode: mode,
			raw_command: el("rawCommand")
				? String(el("rawCommand").value || "").trim()
				: "",
		};

		setUiStatus("enqueue: started mode=" + mode);

		if (mode === "patch" || mode === "repair") {
			body.issue_id = String(el("issueId").value || "").trim();
			body.commit_message = String(el("commitMsg").value || "").trim();
			body.patch_path = normalizePatchPath(
				String(el("patchPath").value || "").trim(),
			);
		} else if (mode === "finalize_live") {
			body.commit_message = String(el("commitMsg").value || "").trim();
		} else if (mode === "finalize_workspace") {
			body.issue_id = String(el("issueId").value || "").trim();
		}

		apiPost("/api/jobs/enqueue", body).then((r) => {
			pushApiStatus(r);
			setPre("previewRight", r);
			if (r && r.ok !== false && r.job_id) {
				setUiStatus("enqueue: ok job_id=" + String(r.job_id));
				selectedJobId = String(r.job_id);
				AMP_UI.saveLiveJobId(selectedJobId);
				suppressIdleOutput = false;
				uiCall("openLiveStream", selectedJobId);
				refreshTail(tailLines);
			} else {
				setUiError(String((r && r.error) || "enqueue failed"));
			}
			refreshJobs();
		});
	}

	function uploadFile(file) {
		var fd = new FormData();
		fd.append("file", file);
		setUiStatus("upload: started " + String((file && file.name) || ""));
		fetch("/api/upload/patch", {
			method: "POST",
			body: fd,
			headers: { Accept: "application/json" },
		})
			.then((r) =>
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
			)
			.then((j) => {
				pushApiStatus(j);
				setText(
					"uploadHint",
					j && j.ok
						? "Uploaded: " + String(j.stored_rel_path || "")
						: "Upload failed: " + String((j && j.error) || ""),
				);
				if (j && j.ok) {
					setUiStatus("upload: ok");
				} else {
					setUiError(String((j && j.error) || "upload failed"));
				}
				if (j && j.stored_rel_path) {
					const stored = String(j.stored_rel_path);
					const n = el("patchPath");
					if (n && shouldOverwrite("patchPath", n)) {
						n.value = stored;
					}

					const relUnderRoot = stripPatchesPrefix(stored);
					const parent = parentRel(relUnderRoot);
					if (String(el("fsPath").value || "") === "") {
						el("fsPath").value = parent;
					}
				}
				applyAutofillFromPayload(j);
				refreshFs();
			})
			.catch((e) => {
				setPre("uploadResult", String(e));
				setUiError(String(e));
			});
	}

	function enableGlobalDropOverlay() {
		var counter = 0;

		function show() {
			document.body.classList.add("dragging");
		}
		function hide() {
			document.body.classList.remove("dragging");
		}

		document.addEventListener("dragenter", (e) => {
			e.preventDefault();
			counter += 1;
			show();
		});

		document.addEventListener("dragover", (e) => {
			e.preventDefault();
			show();
		});

		document.addEventListener("dragleave", (e) => {
			e.preventDefault();
			counter -= 1;
			if (counter <= 0) {
				counter = 0;
				hide();
			}
		});

		document.addEventListener("drop", (e) => {
			e.preventDefault();
			counter = 0;
			hide();
			var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
			if (f) uploadFile(f);
		});
	}

	function setupUpload() {
		var zone = el("uploadZone");
		var browse = el("uploadBrowse");
		var input = el("uploadInput");

		function openPicker() {
			if (!input) return;
			input.value = "";
			input.click();
		}

		if (browse) {
			browse.addEventListener("click", () => {
				openPicker();
			});
		}
		if (zone) {
			zone.addEventListener("click", () => {
				openPicker();
			});

			function setDrag(on) {
				if (on) zone.classList.add("dragover");
				else zone.classList.remove("dragover");
			}

			zone.addEventListener("dragenter", (e) => {
				e.preventDefault();
				setDrag(true);
			});
			zone.addEventListener("dragleave", (e) => {
				e.preventDefault();
				setDrag(false);
			});
			zone.addEventListener("dragover", (e) => {
				e.preventDefault();
				setDrag(true);
			});
			zone.addEventListener("drop", (e) => {
				e.preventDefault();
				setDrag(false);
				var f =
					e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
				if (f) uploadFile(f);
			});
		}

		if (input) {
			input.addEventListener("change", () => {
				if (input.files && input.files[0]) uploadFile(input.files[0]);
			});
		}

		window.addEventListener("dragover", (e) => {
			e.preventDefault();
		});
		window.addEventListener("drop", (e) => {
			e.preventDefault();
		});
	}

	function loadConfig() {
		return apiGet("/api/config")
			.then((r) => {
				cfg = r || null;
				if (cfg && cfg.issue && cfg.issue.default_regex) {
					try {
						issueRegex = new RegExp(cfg.issue.default_regex);
					} catch (e) {
						issueRegex = null;
					}
				}
				if (cfg && cfg.meta && cfg.meta.version) {
					setText("ampWebVersion", "v" + String(cfg.meta.version));
				}
				refreshHeader();
				if (cfg && cfg.ui) {
					if (cfg.ui.base_font_px) {
						document.documentElement.style.fontSize =
							String(cfg.ui.base_font_px) + "px";
					}
					if (cfg.ui.drop_overlay_enabled) {
						enableGlobalDropOverlay();
					}
				}
				return cfg;
			})
			.catch(() => {
				cfg = null;
				return null;
			});
	}

	function shouldOverwrite(fieldKey, node) {
		if (!cfg || !cfg.autofill) return String(node.value || "").trim() === "";
		var pol = String(cfg.autofill.overwrite_policy || "");
		if (pol === "only_if_empty") return String(node.value || "").trim() === "";
		if (pol === "if_not_dirty") return !dirty[fieldKey];
		return false;
	}

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

		uiCall("openLiveStream", null);
		setPre("tail", "");
		updateShortProgressFromText("");

		suppressIdleOutput = true;

		if (cfg && cfg.ui && cfg.ui.show_autofill_clear_status) {
			setUiStatus("autofill: loaded new patch, output cleared");
		}
	}

	function pollLatestPatchOnce() {
		if (!cfg || !cfg.autofill || !cfg.autofill.enabled) return;
		apiGet("/api/patches/latest").then((r) => {
			if (!r || r.ok === false) {
				setUiError(String((r && r.error) || "autofill scan failed"));
				return;
			}

			pushApiStatus(r);
			if (!r.found) return;
			var token = String(r.token || "");
			if (!token || token === latestToken) return;
			latestToken = token;
			applyAutofillFromPayload(r);

			if (cfg && cfg.ui && cfg.ui.clear_output_on_autofill) {
				if (token !== lastAutofillClearedToken) {
					resetOutputForNewPatch();
					lastAutofillClearedToken = token;
				}
			}
		});
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

	function wireButtons() {
		el("fsRefresh").addEventListener("click", refreshFs);
		el("fsUp").addEventListener("click", () => {
			var p = el("fsPath").value || "";
			el("fsPath").value = parentRel(p);
			fsSelected = "";
			setFsHint("");
			refreshFs();
		});

		if (el("fsSelectAll")) {
			el("fsSelectAll").addEventListener("click", () => {
				fsLastRels.forEach((rel) => {
					fsChecked[rel] = true;
				});
				fsUpdateSelCount();
				refreshFs();
			});
		}
		if (el("fsClear")) {
			el("fsClear").addEventListener("click", () => {
				fsClearSelection();
				refreshFs();
			});
		}
		if (el("fsDownloadSelected")) {
			el("fsDownloadSelected").addEventListener("click", () => {
				fsDownloadSelected();
			});
		}

		if (el("fsMkdir")) {
			el("fsMkdir").addEventListener("click", () => {
				var base = String(el("fsPath").value || "");
				var name = prompt("New directory name");
				if (!name) return;
				var rel = joinRel(base, name);
				apiPost("/api/fs/mkdir", { path: rel }).then((r) => {
					if (!r || r.ok === false) {
						setFsHint("mkdir failed");
						return;
					}
					refreshFs();
				});
			});
		}

		if (el("fsRename")) {
			el("fsRename").addEventListener("click", () => {
				if (!fsSelected) {
					setFsHint("focus an item first");
					return;
				}
				var base = parentRel(fsSelected);
				var curName = fsSelected.split("/").pop();
				var dstName = prompt("New name", curName || "");
				if (!dstName) return;
				var dst = joinRel(base, dstName);
				apiPost("/api/fs/rename", { src: fsSelected, dst: dst }).then((r) => {
					if (!r || r.ok === false) {
						setFsHint("rename failed");
						return;
					}
					fsSelected = dst;
					refreshFs();
				});
			});
		}

		if (el("fsDelete")) {
			el("fsDelete").addEventListener("click", () => {
				var paths = [];
				for (var k in fsChecked) {
					if (Object.hasOwn(fsChecked, k)) paths.push(k);
				}
				if (!paths.length && fsSelected) paths = [fsSelected];
				if (!paths.length) {
					setFsHint("select at least one item");
					return;
				}
				if (!confirm("Delete selected item(s)?")) return;

				var seq = Promise.resolve();
				paths.sort().forEach((p) => {
					seq = seq.then(() =>
						apiPost("/api/fs/delete", { path: p }).then((r) => {
							if (!r || r.ok !== true) {
								const err = r && r.error ? String(r.error) : "unknown error";
								setFsHint("delete failed: " + err);
								throw new Error(err);
							}
							return r;
						}),
					);
				});
				seq
					.then(() => {
						fsClearSelection();
						fsSelected = "";
						refreshFs();
					})
					.catch((e) => {
						if (e && e.message) {
							setFsHint("delete failed: " + String(e.message));
						} else {
							setFsHint("delete failed");
						}
					});
			});
		}

		if (el("fsUnzip")) {
			el("fsUnzip").addEventListener("click", () => {
				if (!fsSelected || !/\.zip$/i.test(fsSelected)) {
					setFsHint("focus a .zip file first");
					return;
				}
				var base = parentRel(fsSelected);
				var dst = prompt("Destination directory", base || "");
				if (dst === null) return;
				apiPost("/api/fs/unzip", {
					zip_path: fsSelected,
					dest_dir: String(dst || ""),
				}).then((r) => {
					if (!r || r.ok === false) {
						setFsHint("unzip failed");
						return;
					}
					refreshFs();
				});
			});
		}
		el("runsRefresh").addEventListener("click", refreshRuns);

		if (el("runsCollapse")) {
			el("runsCollapse").addEventListener("click", () => {
				uiCall("setRunsVisible", !runsVisible);
				AMP_UI.saveRunsVisible(runsVisible);
			});
		}

		if (el("previewToggle")) {
			el("previewToggle").addEventListener("click", () => {
				setPreviewVisible(!previewVisible);
			});
		}
		if (el("previewCollapse")) {
			el("previewCollapse").addEventListener("click", () => {
				setPreviewVisible(!previewVisible);
			});
		}

		el("jobsRefresh").addEventListener("click", refreshJobs);

		if (el("jobsCollapse")) {
			el("jobsCollapse").addEventListener("click", () => {
				uiCall("setJobsVisible", !jobsVisible);
				AMP_UI.saveJobsVisible(jobsVisible);
			});
		}

		if (el("liveLevel")) {
			el("liveLevel").addEventListener("change", () => {
				liveLevel = String(el("liveLevel").value || "normal");
				try {
					localStorage.setItem("amp.liveLogLevel", liveLevel);
				} catch (e) {}
				uiCall("renderLiveLog");
				uiCall("updateProgressFromEvents");
			});
		}

		if (el("jobsList")) {
			el("jobsList").addEventListener("click", (e) => {
				var t = e && e.target ? e.target : null;
				while (t && t !== el("jobsList")) {
					const jobId = t.getAttribute && t.getAttribute("data-jobid");
					if (jobId) {
						selectedJobId = String(jobId);
						AMP_UI.saveLiveJobId(selectedJobId);
						suppressIdleOutput = false;
						refreshJobs();
						uiCall("openLiveStream", uiCall("getLiveJobId"));
						refreshTail(tailLines);
						return;
					}
					t = t.parentElement;
				}
			});
		}

		el("enqueueBtn").addEventListener("click", enqueue);

		if (el("parseBtn")) {
			el("parseBtn").addEventListener("click", () => {
				triggerParse(getRawCommand());
			});
		}

		if (el("rawCommand")) {
			el("rawCommand").addEventListener("input", () => {
				var raw = getRawCommand();
				if (raw !== lastParsedRaw) {
					lastParsed = null;
					lastParsedRaw = "";
				}
				if (!raw) {
					clearParsedState();
					setParseHint("");
					validateAndPreview();
					return;
				}
				scheduleParseDebounced(raw);
			});

			el("rawCommand").addEventListener("paste", () => {
				setTimeout(() => {
					triggerParse(getRawCommand());
				}, 0);
			});
		}

		el("mode").addEventListener("change", validateAndPreview);
		el("issueId").addEventListener("input", () => {
			dirty.issueId = true;
			validateAndPreview();
		});
		el("commitMsg").addEventListener("input", () => {
			dirty.commitMsg = true;
			validateAndPreview();
		});
		el("patchPath").addEventListener("input", () => {
			dirty.patchPath = true;
			validateAndPreview();
		});

		var browse = el("browsePatch");
		if (browse) {
			browse.addEventListener("click", () => {
				if (!fsSelected) {
					setFsHint("select a patch file first");
					return;
				}
				el("patchPath").value = normalizePatchPath(fsSelected);
				dirty.patchPath = true;
				validateAndPreview();
			});
		}

		if (el("refreshAll")) {
			el("refreshAll").addEventListener("click", () => {
				refreshFs();
				refreshRuns();
				uiCall("refreshStats");
				refreshJobs();
				refreshHeader();
				renderIssueDetail();
				validateAndPreview();
			});
		}
	}

	function init() {
		setupUpload();
		wireButtons();
		setPreviewVisible(false);
		uiCall("loadUiVisibility");
		uiCall("setRunsVisible", runsVisible);
		uiCall("setJobsVisible", jobsVisible);

		uiCall("loadLiveLevel");
		var savedJobId = uiCall("loadLiveJobId");
		if (savedJobId) selectedJobId = savedJobId;
		if (el("liveLevel")) {
			el("liveLevel").value = liveLevel;
		}

		loadConfig().then(() => {
			refreshFs();
			refreshRuns();
			uiCall("refreshStats");
			refreshJobs();
			refreshTail(tailLines);
			refreshHeader();
			renderIssueDetail();
			validateAndPreview();
			startAutofillPolling();

			if (patchStatTimer) {
				clearInterval(patchStatTimer);
				patchStatTimer = null;
			}
			patchStatTimer = setInterval(tickMissingPatchClear, 1000);

			setInterval(() => {
				if (activeJobId) {
					refreshJobs();
				} else {
					idleRefreshTick();
				}
				refreshTail(tailLines);
			}, 2000);

			setInterval(() => {
				if (activeJobId) {
					refreshHeader();
				}
			}, 5000);

			if (window.AmpSettings && typeof window.AmpSettings.init === "function") {
				try {
					window.AmpSettings.init();
				} catch (e) {
					// Best-effort: do not break main UI if AMP settings init fails.
				}
			}
		});
	}

	window.addEventListener("load", init);
})();
