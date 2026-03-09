(() => {
	var w = /** @type {any} */ (window);
	var ui = w.AMP_PATCHHUB_UI;
	if (!ui) {
		ui = {};
		w.AMP_PATCHHUB_UI = ui;
	}

	var state = {
		key: "",
		loading: false,
		manifest: null,
		selected: {},
		modalOpen: false,
		error: "",
	};

	/**
	 * @param {string} id
	 * @returns {any}
	 */
	function el(id) {
		return /** @type {any} */ (document.getElementById(id));
	}

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

	function currentMode() {
		var node = el("mode");
		return node ? String(node.value || "patch") : "patch";
	}

	function currentPatchPath() {
		var node = el("patchPath");
		if (!node) return "";
		if (typeof normalizePatchPath !== "function") {
			return String(node.value || "").trim();
		}
		return normalizePatchPath(String(node.value || "").trim());
	}

	function currentRawCommand() {
		if (typeof getRawCommand === "function") return getRawCommand();
		return "";
	}

	function isPatchZipMode() {
		return currentMode() === "patch" && /\.zip$/i.test(currentPatchPath());
	}

	function isRawLocked() {
		return !!currentRawCommand();
	}

	function manifestEntries() {
		var manifest = state.manifest || {};
		return Array.isArray(manifest.entries) ? manifest.entries : [];
	}

	function selectedEntries() {
		var out = [];
		manifestEntries().forEach((item) => {
			var name = String(item && item.zip_member ? item.zip_member : "");
			if (!name || item.selectable !== true) return;
			if (state.selected[name] !== false) out.push(name);
		});
		return out;
	}

	function selectedRepoPaths() {
		var out = [];
		manifestEntries().forEach((item) => {
			var name = String(item && item.zip_member ? item.zip_member : "");
			var repo = String(item && item.repo_path ? item.repo_path : "");
			if (!name || !repo || item.selectable !== true) return;
			if (state.selected[name] !== false) out.push(repo);
		});
		return out;
	}

	function selectableCount() {
		return manifestEntries().filter((item) => item.selectable === true).length;
	}

	function ensureSelectionDefaults() {
		manifestEntries().forEach((item) => {
			var name = String(item && item.zip_member ? item.zip_member : "");
			if (!name || item.selectable !== true) return;
			if (!Object.hasOwn(state.selected, name)) {
				state.selected[name] = true;
			}
		});
	}

	function resetSelectionToAll() {
		state.selected = {};
		manifestEntries().forEach((item) => {
			var name = String(item && item.zip_member ? item.zip_member : "");
			if (!name || item.selectable !== true) return;
			state.selected[name] = true;
		});
	}

	function clearState() {
		state.key = "";
		state.loading = false;
		state.manifest = null;
		state.selected = {};
		state.error = "";
		renderStrip();
		closeModal();
	}

	function setModalVisible(on) {
		state.modalOpen = !!on;
		var node = el("zipSubsetModal");
		if (!node) return;
		node.classList.toggle("hidden", !state.modalOpen);
		node.setAttribute("aria-hidden", state.modalOpen ? "false" : "true");
	}

	function closeModal() {
		setModalVisible(false);
	}

	function selectionStatusText() {
		var total = selectableCount();
		var selected = selectedEntries().length;
		if (!total) return "";
		if (selected === total) return `Using uploaded zip (${total} files)`;
		return `Selected ${selected} / ${total} files`;
	}

	function renderStrip() {
		var box = el("zipSubsetStrip");
		if (!box) return;
		if (!isPatchZipMode()) {
			box.classList.add("hidden");
			box.innerHTML = "";
			return;
		}

		box.classList.remove("hidden");
		if (state.loading) {
			box.innerHTML =
				'<div class="zip-subset-strip-inner">' +
				'<div><b>ZIP patch detected</b><div class="muted">Loading target files...</div></div>' +
				'<button type="button" class="btn btn-small" disabled>Loading...</button></div>';
			return;
		}

		if (state.error) {
			box.innerHTML =
				'<div class="zip-subset-strip-inner">' +
				'<div><b>ZIP patch detected</b><div class="muted">' +
				escapeHtml(state.error) +
				"</div></div>" +
				'<button type="button" class="btn btn-small" id="zipSubsetRetryBtn">Retry</button>' +
				"</div>";
			return;
		}

		var manifest = state.manifest || {};
		var total = Number(manifest.patch_entry_count || 0);
		var selectable = manifest.selectable === true;
		ensureSelectionDefaults();
		var detail = selectable
			? selectionStatusText()
			: String(manifest.reason || "read only");
		var buttonText =
			selectable && !isRawLocked() ? "Select files to include" : "View files";
		var note = "";
		if (isRawLocked()) {
			note =
				'<div class="muted">Subset disabled while raw command is set.</div>';
		} else if (!selectable) {
			note =
				'<div class="muted">Subset available only for PM per-file zip patches.</div>';
		}
		box.innerHTML =
			'<div class="zip-subset-strip-inner">' +
			"<div><b>ZIP patch detected: " +
			escapeHtml(String(total)) +
			' target files</b><div class="muted">' +
			escapeHtml(detail) +
			"</div>" +
			note +
			"</div>" +
			'<button type="button" id="zipSubsetOpenBtn" class="btn btn-small">' +
			escapeHtml(buttonText) +
			"</button>" +
			"</div>";
	}

	function renderModal() {
		var summary = el("zipSubsetModalSummary");
		var list = el("zipSubsetModalList");
		var applyBtn = el("zipSubsetApplyBtn");
		if (!summary || !list || !applyBtn) return;

		var manifest = state.manifest || {};
		ensureSelectionDefaults();
		var rows = manifestEntries()
			.map((item) => {
				var name = String(item && item.zip_member ? item.zip_member : "");
				var repo = String(item && item.repo_path ? item.repo_path : "");
				var checked = state.selected[name] !== false;
				var disabled = item.selectable !== true || isRawLocked();
				return (
					'<label class="zip-subset-item">' +
					'<input type="checkbox" class="zip-subset-check" data-zip-entry="' +
					escapeHtml(name) +
					'" ' +
					(checked ? 'checked="checked" ' : "") +
					(disabled ? 'disabled="disabled" ' : "") +
					"/>" +
					'<span class="zip-subset-path">' +
					escapeHtml(repo || name) +
					"</span>" +
					'<span class="zip-subset-member">' +
					escapeHtml(name) +
					"</span>" +
					"</label>"
				);
			})
			.join("");

		list.innerHTML = rows || '<div class="muted">(no patch entries)</div>';
		summary.textContent = selectionStatusText() || "Using uploaded zip";
		applyBtn.disabled = selectableCount() > 0 && selectedEntries().length === 0;
	}

	function openModal() {
		if (!state.manifest) return;
		renderModal();
		setModalVisible(true);
	}

	function fetchManifestForCurrentPath() {
		var patchPath = currentPatchPath();
		state.loading = true;
		state.error = "";
		state.manifest = null;
		state.selected = {};
		renderStrip();
		apiGet(
			"/api/patches/zip_manifest?path=" + encodeURIComponent(patchPath),
		).then((r) => {
			state.loading = false;
			if (!r || r.ok === false || !r.manifest) {
				state.error = String((r && r.error) || "cannot inspect zip patch");
				state.manifest = null;
				renderStrip();
				if (typeof validateAndPreview === "function") validateAndPreview();
				return;
			}
			state.manifest = r.manifest;
			resetSelectionToAll();
			renderStrip();
			if (state.modalOpen) renderModal();
			if (typeof validateAndPreview === "function") validateAndPreview();
		});
	}

	function syncFromInputs() {
		if (!isPatchZipMode()) {
			clearState();
			return;
		}
		var key = currentMode() + "|" + currentPatchPath();
		if (state.key !== key) {
			state.key = key;
			fetchManifestForCurrentPath();
			return;
		}
		renderStrip();
		if (state.modalOpen) renderModal();
	}

	function enqueuePayload() {
		if (!state.manifest || state.loading || isRawLocked()) return {};
		if (state.manifest.selectable !== true) return {};
		var selected = selectedEntries();
		var total = selectableCount();
		if (!selected.length) {
			return { error: "no selected files" };
		}
		if (selected.length >= total) return {};
		return { selected_patch_entries: selected.slice() };
	}

	function validationState() {
		if (!isPatchZipMode()) return { ok: true, hint: "" };
		if (state.loading) return { ok: false, hint: "loading zip target files" };
		if (state.error) return { ok: false, hint: state.error };
		if (!state.manifest || state.manifest.selectable !== true)
			return { ok: true, hint: "" };
		if (isRawLocked()) return { ok: true, hint: "" };
		if (!selectedEntries().length)
			return { ok: false, hint: "no selected files" };
		return { ok: true, hint: "" };
	}

	function applyPreview(preview) {
		if (!preview || typeof preview !== "object") return preview;
		if (!state.manifest || !isPatchZipMode()) return preview;
		preview.zip_subset = {
			selectable: state.manifest.selectable === true,
			selection_status: selectionStatusText(),
			selected_patch_entries: selectedEntries(),
			selected_repo_paths: selectedRepoPaths(),
			effective_patch_kind:
				selectedEntries().length < selectableCount()
					? "derived_subset_pending"
					: "original",
		};
		return preview;
	}

	function bindEvents() {
		document.addEventListener("click", (ev) => {
			var t = /** @type {any} */ (ev && ev.target ? ev.target : null);
			if (!t) return;
			if (t.id === "zipSubsetOpenBtn") {
				openModal();
				return;
			}
			if (t.id === "zipSubsetRetryBtn") {
				fetchManifestForCurrentPath();
				return;
			}
			if (t.id === "zipSubsetCloseBtn" || t.id === "zipSubsetCancelBtn") {
				closeModal();
				return;
			}
			if (t.id === "zipSubsetSelectAllBtn") {
				resetSelectionToAll();
				renderModal();
				renderStrip();
				if (typeof validateAndPreview === "function") validateAndPreview();
				return;
			}
			if (t.id === "zipSubsetClearBtn") {
				state.selected = {};
				renderModal();
				renderStrip();
				if (typeof validateAndPreview === "function") validateAndPreview();
				return;
			}
			if (t.id === "zipSubsetResetBtn") {
				resetSelectionToAll();
				renderModal();
				renderStrip();
				if (typeof validateAndPreview === "function") validateAndPreview();
				return;
			}
			if (t.id === "zipSubsetApplyBtn") {
				closeModal();
				renderStrip();
				if (typeof validateAndPreview === "function") validateAndPreview();
			}
		});

		document.addEventListener("change", (ev) => {
			var t = /** @type {any} */ (ev && ev.target ? ev.target : null);
			if (!t || !t.classList || !t.classList.contains("zip-subset-check"))
				return;
			var name = String(t.getAttribute("data-zip-entry") || "");
			if (!name) return;
			state.selected[name] = !!t.checked;
			renderModal();
			renderStrip();
			if (typeof validateAndPreview === "function") validateAndPreview();
		});

		var backdrop = el("zipSubsetModal");
		if (backdrop) {
			backdrop.addEventListener("click", (ev) => {
				if (ev.target === backdrop) closeModal();
			});
		}
	}

	bindEvents();

	var PH = w.PH;
	if (PH && typeof PH.register === "function") {
		PH.register("zip_subset", {
			syncFromInputs,
			enqueuePayload,
			validationState,
			applyPreview,
			openModal,
		});
	}
	ui.syncZipSubsetUiFromInputs = syncFromInputs;
	ui.getZipSubsetEnqueuePayload = enqueuePayload;
	ui.getZipSubsetValidationState = validationState;
	ui.applyZipSubsetPreview = applyPreview;
	safeExport("syncZipSubsetUiFromInputs", syncFromInputs);
	safeExport("getZipSubsetEnqueuePayload", enqueuePayload);
	safeExport("getZipSubsetValidationState", validationState);
	safeExport("applyZipSubsetPreview", applyPreview);
})();
