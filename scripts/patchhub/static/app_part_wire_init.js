/** @type {any} */
var PH = /** @type {any} */ (window).PH;
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
			runsVisible = !runsVisible;
			PH.call("setRunsVisible", runsVisible);
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
			jobsVisible = !jobsVisible;
			PH.call("setJobsVisible", jobsVisible);
			AMP_UI.saveJobsVisible(jobsVisible);
		});
	}

	if (el("liveLevel")) {
		el("liveLevel").addEventListener("change", () => {
			var v = String(el("liveLevel").value || "normal");
			PH.call("setLiveLevel", v);
			PH.call("renderLiveLog");
			PH.call("updateProgressFromEvents");
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
					PH.call("openLiveStream", PH.call("getLiveJobId"));
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
			PH.call("refreshStats");
			refreshJobs();
			refreshHeader();
			renderIssueDetail();
			validateAndPreview();
		});
	}
}

function init() {
	function start() {
		setupUpload();
		wireButtons();
		setPreviewVisible(false);
		PH.call("loadUiVisibility");
		PH.call("setRunsVisible", runsVisible);
		PH.call("setJobsVisible", jobsVisible);

		PH.call("loadLiveLevel");
		var savedJobId = PH.call("loadLiveJobId");
		if (savedJobId) selectedJobId = savedJobId;
		if (el("liveLevel")) {
			const v = PH.call("getLiveLevel");
			if (v) el("liveLevel").value = String(v);
		}

		loadConfig().then(() => {
			refreshFs();
			refreshRuns();
			PH.call("refreshStats");
			refreshJobs();
			refreshTail(tailLines);
			refreshHeader();
			renderIssueDetail();
			validateAndPreview();

			if (patchStatTimer) {
				clearInterval(patchStatTimer);
				patchStatTimer = null;
			}
			patchStatTimer = setInterval(tickMissingPatchClear, 1000);

			var refreshTimer = null;
			var headerTimer = null;

			function stopTimers() {
				if (refreshTimer) {
					clearInterval(refreshTimer);
					refreshTimer = null;
				}
				if (headerTimer) {
					clearInterval(headerTimer);
					headerTimer = null;
				}
				if (patchStatTimer) {
					clearInterval(patchStatTimer);
					patchStatTimer = null;
				}
				stopAutofillPolling();
				PH.call("closeLiveStream");
			}

			function startTimers() {
				stopTimers();

				patchStatTimer = setInterval(tickMissingPatchClear, 1000);

				refreshTimer = setInterval(() => {
					try {
						if (activeJobId) refreshJobs({ mode: "periodic" });
						else idleRefreshTick();
						refreshTail(tailLines);
					} catch (e) {
						setUiError(e);
					}
				}, 2000);

				headerTimer = setInterval(() => {
					try {
						if (activeJobId) refreshHeader({ mode: "periodic" });
					} catch (e) {
						setUiError(e);
					}
				}, 5000);

				startAutofillPolling();
			}

			function resyncVisible() {
				refreshFs();
				refreshRuns();
				PH.call("refreshStats");
				refreshJobs();
				refreshTail(tailLines);
				refreshHeader();
				renderIssueDetail();
				validateAndPreview();
			}

			document.addEventListener("visibilitychange", () => {
				try {
					if (document.hidden) {
						stopTimers();
					} else {
						resyncVisible();
						startTimers();
					}
				} catch (e) {
					setUiError(e);
				}
			});

			startTimers();

			if (
				/** @type {any} */ (window).AmpSettings &&
				typeof (/** @type {any} */ (window).AmpSettings.init) === "function"
			) {
				try {
					/** @type {any} */ (window).AmpSettings.init();
				} catch (e) {
					// Best-effort: do not break main UI if AMP settings init fails.
				}
			}
		});
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", start);
	} else {
		start();
	}
}

// Called by app.js after it loads all required parts.
window.PH_APP_START = init;
