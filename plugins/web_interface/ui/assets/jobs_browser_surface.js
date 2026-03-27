(() => {
	/** @param {AM2WebJobItem | null | undefined} job */
	function jobIdOf(job) {
		return String((job && (job.job_id || job.id)) || "");
	}

	/** @param {AM2WebJobItem | null | undefined} job */
	function jobMetaSource(job) {
		const meta = job && typeof job.meta === "object" ? job.meta : null;
		return meta && typeof meta.source === "string" ? meta.source : "";
	}

	/** @param {AM2WebJobItem | null | undefined} job */
	function canStartJob(job) {
		return job && job.state === "pending" && jobMetaSource(job) !== "import";
	}

	Reflect.set(window, "AMWebJobsBrowserSurface", {
		/**
		 * @param {AM2WebContent} content
		 * @param {AM2WebNotifyFn} notify
		 * @param {AM2WebSurfaceDeps} deps
		 */
		async render(content, notify, deps) {
			const { API, el, clear } = deps;
			const root = el("div", { class: "jobsLog" });
			const header = el("div", { class: "row" });
			const refreshBtn = el("button", { class: "btn", text: "Refresh jobs" });
			header.appendChild(refreshBtn);
			root.appendChild(header);

			const grid = el("div", { class: "jobsGrid" });
			const left = el("div", { class: "jobsCol" });
			const right = el("div", { class: "jobsColWide" });
			grid.appendChild(left);
			grid.appendChild(right);
			root.appendChild(grid);

			const jobsBox = el("div");
			left.appendChild(jobsBox);

			const logHeader = el("div", { class: "row" });
			const followChk = /** @type {HTMLInputElement} */ (
				el("input", { type: "checkbox" })
			);
			const followLbl = el("label", { class: "hint", text: "Follow" });
			followLbl.prepend(followChk);
			const clearBtn = el("button", { class: "btn", text: "Clear" });
			logHeader.appendChild(followLbl);
			logHeader.appendChild(clearBtn);
			right.appendChild(logHeader);

			const pre = el("pre", { class: "logBox", text: "Select a job." });
			right.appendChild(pre);

			/** @type {string | null} */
			let currentJobId = null;
			let offset = 0;
			/** @type {ReturnType<typeof setInterval> | null} */
			let followTimer = null;
			/** @type {HTMLElement | null} */
			let selectedRow = null;
			const observer = new MutationObserver(() => {
				if (document.body.contains(root)) return;
				stopFollow();
				observer.disconnect();
			});
			observer.observe(document.body, { childList: true, subtree: true });

			function stopFollow() {
				if (!followTimer) return;
				clearInterval(followTimer);
				followTimer = null;
			}

			/** @param {HTMLElement | null} row */
			function setSelectedRow(row) {
				if (selectedRow) selectedRow.style.background = "";
				selectedRow = row;
				if (selectedRow) {
					selectedRow.style.background = "rgba(255,255,255,0.06)";
				}
			}

			async function loadMore() {
				if (!currentJobId) {
					pre.textContent = "Select a job.";
					return;
				}
				try {
					const data = await API.getJson(
						`/api/jobs/${encodeURIComponent(currentJobId)}/log?offset=${offset}`,
					);
					const txt = data && typeof data.text === "string" ? data.text : "";
					pre.textContent += txt;
					offset =
						data && typeof data.next_offset === "number"
							? data.next_offset
							: offset;
					pre.scrollTop = pre.scrollHeight;
				} catch (e) {
					if (typeof notify === "function") notify(String(e));
				}
			}

			/** @param {string} jobId @param {HTMLElement} row */
			async function selectJob(jobId, row) {
				currentJobId = jobId;
				offset = 0;
				pre.textContent = "";
				setSelectedRow(row);
				await loadMore();
			}

			/** @param {string} jobId */
			async function startJob(jobId) {
				try {
					await API.sendJson(
						"POST",
						`/api/jobs/${encodeURIComponent(jobId)}/run`,
					);
					if (typeof notify === "function") notify("Started.");
					await loadJobs();
				} catch (e) {
					if (typeof notify === "function") notify(String(e));
				}
			}

			async function loadJobs() {
				clear(jobsBox);
				/** @type {AM2JsonObject} */
				let data;
				try {
					data = await API.getJson("/api/jobs");
				} catch (e) {
					jobsBox.appendChild(el("div", { class: "hint", text: String(e) }));
					return;
				}
				const items = /** @type {AM2WebJobItem[]} */ (
					Array.isArray(data.items) ? data.items : []
				);
				if (!items.length) {
					jobsBox.appendChild(el("div", { class: "hint", text: "No jobs." }));
					return;
				}

				const table = el("table", { class: "table" });
				const thead = el("thead");
				const trh = el("tr");
				/** @type {string[]} */ ([
					"job_id",
					"type",
					"state",
					"source",
					"actions",
				]).forEach((h) => {
					trh.appendChild(el("th", { text: h }));
				});
				thead.appendChild(trh);
				table.appendChild(thead);
				const tbody = el("tbody");

				for (const job of items) {
					const jid = jobIdOf(job);
					const tr = el("tr");
					tr.appendChild(el("td", { text: jid }));
					tr.appendChild(el("td", { text: String(job.type || "") }));
					tr.appendChild(el("td", { text: String(job.state || "") }));
					tr.appendChild(el("td", { text: jobMetaSource(job) }));
					const actionsTd = el("td");
					if (canStartJob(job)) {
						const startBtn = el("button", { class: "btn", text: "Start" });
						startBtn.addEventListener(
							"click",
							/** @param {MouseEvent} ev */ async (ev) => {
								ev.stopPropagation();
								await startJob(jid);
							},
						);
						actionsTd.appendChild(startBtn);
					}
					tr.appendChild(actionsTd);
					tr.addEventListener("click", async () => {
						await selectJob(jid, tr);
					});
					if (jid && jid === currentJobId) setSelectedRow(tr);
					tbody.appendChild(tr);
				}
				table.appendChild(tbody);
				jobsBox.appendChild(table);
			}

			followChk.addEventListener("change", () => {
				stopFollow();
				if (followChk.checked) followTimer = setInterval(loadMore, 1500);
			});
			clearBtn.addEventListener("click", () => {
				pre.textContent = "";
				offset = 0;
			});
			refreshBtn.addEventListener("click", loadJobs);

			void content;
			await loadJobs();
			return root;
		},
	});
})();
