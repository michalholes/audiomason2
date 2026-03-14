/** @type {any} */
var PH = /** @type {any} */ (window).PH;

var infoPoolOpen = false;
var infoPoolBound = false;

function infoPoolModalEl(id) {
	return el(id);
}

function infoPoolSnapshot() {
	if (typeof getInfoPoolSnapshot === "function") return getInfoPoolSnapshot();
	return {
		degradedNotes: [],
		statusLines: [],
		hints: { upload: "", enqueue: "", fs: "", parse: "" },
		latestHint: { source: "", text: "" },
	};
}

function infoPoolSummary(snapshot) {
	var degraded = Array.isArray(snapshot.degradedNotes)
		? snapshot.degradedNotes
		: [];
	if (degraded.length) {
		return "DEGRADED MODE: " + String(degraded[degraded.length - 1] || "");
	}
	if (snapshot.latestHint && snapshot.latestHint.text) {
		return String(snapshot.latestHint.text || "");
	}
	var statusLines = Array.isArray(snapshot.statusLines)
		? snapshot.statusLines
		: [];
	if (statusLines.length)
		return String(statusLines[statusLines.length - 1] || "");
	return "(idle)";
}

function infoPoolHintValue(label, value) {
	return (
		'<div class="info-pool-hint-row">' +
		'<div class="info-pool-hint-label">' +
		escapeHtml(label) +
		"</div>" +
		'<div class="info-pool-hint-value">' +
		escapeHtml(value || "(empty)") +
		"</div>" +
		"</div>"
	);
}

function infoPoolSection(title, bodyHtml) {
	return (
		'<section class="info-pool-section">' +
		'<h3 class="info-pool-section-title">' +
		escapeHtml(title) +
		"</h3>" +
		bodyHtml +
		"</section>"
	);
}

function infoPoolList(lines, emptyText) {
	var items = Array.isArray(lines) ? lines : [];
	if (!items.length) {
		return '<div class="info-pool-empty">' + escapeHtml(emptyText) + "</div>";
	}
	return (
		'<div class="info-pool-lines">' +
		items
			.map((line) => {
				return '<div class="info-pool-line">' + escapeHtml(line) + "</div>";
			})
			.join("") +
		"</div>"
	);
}

function renderInfoPoolModal() {
	var modal = infoPoolModalEl("uiStatusModal");
	var body = infoPoolModalEl("uiStatusModalBody");
	if (!modal || !body) return;
	var snapshot = infoPoolSnapshot();
	var hints = snapshot.hints || {};
	var degraded = Array.isArray(snapshot.degradedNotes)
		? snapshot.degradedNotes.slice(-1)
		: [];
	var hintHtml = [
		infoPoolHintValue("Upload", String(hints.upload || "")),
		infoPoolHintValue("Start run", String(hints.enqueue || "")),
		infoPoolHintValue("Files", String(hints.fs || "")),
		infoPoolHintValue("Advanced", String(hints.parse || "")),
	].join("");
	body.innerHTML = [
		infoPoolSection("Degraded mode", infoPoolList(degraded, "(empty)")),
		infoPoolSection(
			"Current hints",
			'<div class="info-pool-hints">' + hintHtml + "</div>",
		),
		infoPoolSection(
			"Recent status",
			infoPoolList(snapshot.statusLines || [], "(empty)"),
		),
	].join("");
	modal.classList.toggle("hidden", !infoPoolOpen);
	modal.setAttribute("aria-hidden", infoPoolOpen ? "false" : "true");
}

function renderInfoPoolUi() {
	var strip = infoPoolModalEl("uiStatusBar");
	if (!strip) return;
	var summary = infoPoolSummary(infoPoolSnapshot());
	strip.textContent = summary;
	strip.classList.add("statusbar-clickable");
	strip.classList.toggle("statusbar-idle", summary === "(idle)");
	if (infoPoolOpen) renderInfoPoolModal();
}

function setInfoPoolOpen(nextOpen) {
	infoPoolOpen = !!nextOpen;
	renderInfoPoolModal();
}

function onInfoPoolStripKeydown(event) {
	var key = event && event.key ? String(event.key) : "";
	if (key !== "Enter" && key !== " ") return;
	if (event && typeof event.preventDefault === "function") {
		event.preventDefault();
	}
	setInfoPoolOpen(true);
}

function onInfoPoolDocumentKeydown(event) {
	var key = event && event.key ? String(event.key) : "";
	if (key === "Escape") setInfoPoolOpen(false);
}

function initInfoPoolUi() {
	var strip = infoPoolModalEl("uiStatusBar");
	var modal = infoPoolModalEl("uiStatusModal");
	var closeBtn = infoPoolModalEl("uiStatusModalCloseBtn");
	if (!strip || !modal || infoPoolBound) {
		renderInfoPoolUi();
		return;
	}
	infoPoolBound = true;
	strip.addEventListener("click", () => {
		setInfoPoolOpen(true);
	});
	strip.addEventListener("keydown", onInfoPoolStripKeydown);
	if (closeBtn) {
		closeBtn.addEventListener("click", () => {
			setInfoPoolOpen(false);
		});
	}
	modal.addEventListener("click", (event) => {
		if (event && event.target === modal) setInfoPoolOpen(false);
	});
	if (document && typeof document.addEventListener === "function") {
		document.addEventListener("keydown", onInfoPoolDocumentKeydown);
	}
	renderInfoPoolUi();
}

if (PH && typeof PH.register === "function") {
	PH.register("app_part_info_pool", {
		initInfoPoolUi,
		renderInfoPoolUi,
	});
}
