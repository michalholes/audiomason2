(() => {
	var root = /** @type {any} */ (window);

	function $(id) {
		return document.getElementById(id);
	}

	var ui = {
		modal: $("flowJsonModal"),
		title: $("flowJsonModalTitle"),
		subtitle: $("flowJsonModalSubtitle"),
		editor: /** @type {HTMLTextAreaElement | null} */ (
			$("flowJsonModalEditor")
		),
		status: $("flowJsonModalStatus"),
		error: $("flowJsonModalError"),
		reread: $("flowJsonReread"),
		abort: $("flowJsonAbort"),
		save: $("flowJsonSave"),
		cancel: $("flowJsonCancel"),
		copySelected: $("flowJsonCopySelected"),
		copyAll: $("flowJsonCopyAll"),
		apply: $("flowJsonApply"),
	};

	if (!ui.modal || !ui.editor) {
		return;
	}

	function isOpen() {
		return !ui.modal.classList.contains("is-hidden");
	}

	function setOpen(open) {
		ui.modal.classList.toggle("is-hidden", open !== true);
		ui.modal.setAttribute("aria-hidden", open === true ? "false" : "true");
		if (open === true && ui.editor && ui.editor.focus) {
			ui.editor.focus();
		}
	}

	function setArtifactMeta(title, subtitle) {
		if (ui.title) ui.title.textContent = String(title || "");
		if (ui.subtitle) ui.subtitle.textContent = String(subtitle || "");
	}

	function setValue(text) {
		ui.editor.value = String(text || "");
	}

	function getValue() {
		return String(ui.editor.value || "");
	}

	function setStatus(msg, kind) {
		if (!ui.status) return;
		ui.status.textContent = String(msg || "");
		ui.status.classList.toggle("is-ok", kind === "ok");
		ui.status.classList.toggle("is-bad", kind === "bad");
	}

	function setError(msg) {
		if (!ui.error) return;
		ui.error.textContent = String(msg || "");
	}

	function clearFeedback() {
		setStatus("", "");
		setError("");
	}

	function getSelectedText() {
		var value = getValue();
		var start = Number(ui.editor.selectionStart || 0);
		var end = Number(ui.editor.selectionEnd || 0);
		if (end <= start) {
			return "";
		}
		return value.slice(start, end);
	}

	root.AM2FlowJSONModalDOM = {
		ui: ui,
		clearFeedback: clearFeedback,
		getSelectedText: getSelectedText,
		getValue: getValue,
		isOpen: isOpen,
		setArtifactMeta: setArtifactMeta,
		setError: setError,
		setOpen: setOpen,
		setStatus: setStatus,
		setValue: setValue,
	};
})();
