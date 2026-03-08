/** @type {any} */
var __ph_w = /** @type {any} */ (window);
var snapshotEventsSource = null;
var snapshotEventsHealthy = false;
var snapshotEventSeq = 0;

function updateSnapshotEventSigs(payload) {
	var sigs = (payload && payload.sigs) || {};
	var snapSig = String(sigs.snapshot || "");
	if (snapSig) idleSigs.snapshot = snapSig;
	var js = String(sigs.jobs || "");
	var rs = String(sigs.runs || "");
	var ws = String(sigs.workspaces || "");
	var hs = String(sigs.header || "");
	if (js) idleSigs.jobs = js;
	if (rs) idleSigs.runs = rs;
	if (ws) idleSigs.workspaces = ws;
	if (hs) idleSigs.hdr = hs;
}

function handleSnapshotEventPayload(payload) {
	var seq = Number((payload && payload.seq) || 0);
	if (!Number.isNaN(seq) && seq < snapshotEventSeq) return false;
	if (!Number.isNaN(seq)) snapshotEventSeq = seq;
	updateSnapshotEventSigs(payload);
	return true;
}

function stopSnapshotEvents() {
	if (snapshotEventsSource) {
		try {
			snapshotEventsSource.close();
		} catch (_) {}
	}
	snapshotEventsSource = null;
	snapshotEventsHealthy = false;
}

function openSnapshotEvents() {
	if (snapshotEventsSource || activeJobId || document.hidden) return;
	if (typeof EventSource !== "function") {
		snapshotEventsHealthy = false;
		return;
	}
	snapshotEventsHealthy = false;
	var es = new EventSource("/api/events");
	snapshotEventsSource = es;
	es.addEventListener("snapshot_state", (ev) => {
		var payload = null;
		try {
			payload = JSON.parse(String(ev.data || "{}"));
		} catch (_) {
			return;
		}
		handleSnapshotEventPayload(payload);
		snapshotEventsHealthy = true;
	});
	es.addEventListener("snapshot_changed", (ev) => {
		var payload = null;
		try {
			payload = JSON.parse(String(ev.data || "{}"));
		} catch (_) {
			return;
		}
		if (!handleSnapshotEventPayload(payload)) return;
		snapshotEventsHealthy = true;
		__ph_w.refreshOverviewSnapshot({ mode: "latest" }).catch((e) => {
			setUiError(e);
		});
	});
	es.onerror = () => {
		stopSnapshotEvents();
	};
}

function ensureSnapshotEvents() {
	if (activeJobId) {
		stopSnapshotEvents();
		return;
	}
	if (!snapshotEventsSource) {
		openSnapshotEvents();
	}
}

function snapshotEventsNeedPolling() {
	return !snapshotEventsHealthy;
}

__ph_w.ensureSnapshotEvents = ensureSnapshotEvents;
__ph_w.stopSnapshotEvents = stopSnapshotEvents;
__ph_w.snapshotEventsNeedPolling = snapshotEventsNeedPolling;
