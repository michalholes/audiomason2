(function () {
	"use strict";

	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	function renderValidation(opts) {
		const mount = opts && opts.mount;
		const countEl = opts && opts.countEl;
		const el = (opts && opts.el) || function () {};
		const text = (opts && opts.text) || function () {};
		const messages = (opts && opts.messages) || [];
		if (!mount) return;

		clear(mount);
		const msgs = Array.isArray(messages) ? messages : [];
		if (countEl) countEl.textContent = msgs.length ? String(msgs.length) : "";

		if (!msgs.length) {
			mount.appendChild(
				text("div", "wdValidationEmpty", "No validation messages."),
			);
			return;
		}

		msgs.forEach(function (m) {
			const row = el("div", "wdValidationItem");
			row.textContent = String(m || "");
			mount.appendChild(row);
		});
	}

	function renderStepDetails(opts) {
		const mount = opts && opts.mount;
		const el = (opts && opts.el) || function () {};
		const text = (opts && opts.text) || function () {};
		const selectedStepId = (opts && opts.selectedStepId) || null;
		const details = (opts && opts.details) || null;
		const loading = Boolean(opts && opts.loading);
		const error = (opts && opts.error) || null;
		if (!mount) return;

		clear(mount);

		if (!selectedStepId) {
			mount.appendChild(
				text("div", "wdStepDetailsEmpty", "Select a step to view details."),
			);
			return;
		}

		if (loading && !details) {
			mount.appendChild(text("div", "wdStepDetailsLoading", "Loading..."));
			return;
		}

		if (error && !details) {
			const msg = "Failed to load step details. " + String(error || "");
			mount.appendChild(text("div", "wdStepDetailsError", msg));
			return;
		}

		if (!details) {
			mount.appendChild(
				text("div", "wdStepDetailsEmpty", "No details available."),
			);
			return;
		}

		const head = el("div", "wdStepDetailsHeader");
		head.appendChild(
			text("div", "wdStepDetailsTitle", String(details.title || "")),
		);

		const metaParts = [
			String(details.step_id || selectedStepId || ""),
			String(details.kind || ""),
			details.pinned ? "pinned" : "not_pinned",
		].filter(Boolean);
		head.appendChild(text("div", "wdStepDetailsMeta", metaParts.join(" / ")));
		mount.appendChild(head);

		if (details.description) {
			mount.appendChild(
				text(
					"div",
					"wdStepDetailsDescription",
					String(details.description || ""),
				),
			);
		}

		const schema = details.settings_schema || {};
		const fields = Array.isArray(schema.fields) ? schema.fields : [];
		const fieldsWrap = el("div", "wdStepDetailsFields");
		fieldsWrap.appendChild(
			text("div", "wdStepDetailsSectionTitle", "settings_schema.fields"),
		);
		if (!fields.length) {
			fieldsWrap.appendChild(
				text("div", "wdStepDetailsFieldsEmpty", "(missing)"),
			);
		} else {
			fields.forEach(function (f) {
				const row = el("div", "wdStepDetailsFieldRow");
				const key = f && f.key != null ? String(f.key) : "(missing)";
				const typ = f && f.type != null ? String(f.type) : "(missing)";
				const req = f && f.required ? "required" : "optional";
				let defv = "(missing)";
				if (f && Object.prototype.hasOwnProperty.call(f, "default")) {
					defv = String(f.default);
				}
				row.appendChild(text("div", "wdStepDetailsFieldKey", key));
				row.appendChild(text("div", "wdStepDetailsFieldType", typ));
				row.appendChild(text("div", "wdStepDetailsFieldReq", req));
				row.appendChild(text("div", "wdStepDetailsFieldDefault", defv));
				fieldsWrap.appendChild(row);
			});
		}
		mount.appendChild(fieldsWrap);

		const templWrap = el("div", "wdStepDetailsTemplate");
		templWrap.appendChild(
			text("div", "wdStepDetailsSectionTitle", "defaults_template"),
		);
		const pre = el("pre", "wdStepDetailsTemplatePre");
		let jsonText = "";
		try {
			jsonText = JSON.stringify(details.defaults_template || {}, null, 2);
		} catch (e) {
			jsonText = "{}";
		}
		pre.textContent = jsonText;
		templWrap.appendChild(pre);
		mount.appendChild(templWrap);
	}

	window.AM2WDDetailsRender = {
		renderValidation: renderValidation,
		renderStepDetails: renderStepDetails,
	};
})();
