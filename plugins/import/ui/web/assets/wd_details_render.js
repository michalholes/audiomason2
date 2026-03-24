(function () {
	"use strict";

	/** @param {Node | null} node */
	function clear(node) {
		while (node && node.firstChild) node.removeChild(node.firstChild);
	}

	/**
	 * @param {unknown} fn
	 * @returns {AM2DomFactoryApi}
	 */
	function asDomFactory(fn) {
		return typeof fn === "function"
			? /** @type {AM2DomFactoryApi} */ (fn)
			: function (tag, cls) {
					const node = document.createElement(tag);
					if (cls) node.className = cls;
					return node;
				};
	}

	/**
	 * @param {unknown} fn
	 * @returns {AM2TextFactoryApi}
	 */
	function asTextFactory(fn) {
		return typeof fn === "function"
			? /** @type {AM2TextFactoryApi} */ (fn)
			: function (tag, cls, value) {
					const node = document.createElement(tag);
					if (cls) node.className = cls;
					node.textContent = String(value || "");
					return node;
				};
	}

	/**
	 * @param {AM2JsonValue} value
	 * @returns {AM2FlowSettingsSchema | null}
	 */
	function asSettingsSchema(value) {
		if (!value || typeof value !== "object" || Array.isArray(value))
			return null;
		return /** @type {AM2FlowSettingsSchema} */ (value);
	}

	/**
	 * @param {{
	 * 	mount: HTMLElement,
	 * 	countEl?: HTMLElement | null,
	 * 	el?: AM2DomFactoryApi,
	 * 	text?: AM2TextFactoryApi,
	 * 	messages?: AM2JsonValue[],
	 * }} opts
	 */
	function renderValidation(opts) {
		const mount = opts && opts.mount;
		const countEl = opts && opts.countEl;
		const el = asDomFactory(opts && opts.el);
		const text = asTextFactory(opts && opts.text);
		const messages = Array.isArray(opts && opts.messages) ? opts.messages : [];
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
		msgs.forEach(function (msg) {
			const row = el("div", "wdValidationItem");
			row.textContent = String(msg || "");
			mount.appendChild(row);
		});
	}

	/**
	 * @param {{
	 * 	mount: HTMLElement,
	 * 	details?: AM2JsonObject | null,
	 * 	selectedStepId?: string | null,
	 * 	el?: AM2DomFactoryApi,
	 * 	text?: AM2TextFactoryApi,
	 * 	loading?: boolean,
	 * 	error?: AM2JsonValue,
	 * }} opts
	 */
	function renderStepDetails(opts) {
		const mount = opts && opts.mount;
		const el = asDomFactory(opts && opts.el);
		const text = asTextFactory(opts && opts.text);
		const selectedStepId = (opts && opts.selectedStepId) || null;
		const details =
			opts && opts.details && typeof opts.details === "object"
				? opts.details
				: null;
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
		const schema = asSettingsSchema(details.settings_schema || null);
		const fields = schema && Array.isArray(schema.fields) ? schema.fields : [];
		const fieldsWrap = el("div", "wdStepDetailsFields");
		fieldsWrap.appendChild(
			text("div", "wdStepDetailsSectionTitle", "settings_schema.fields"),
		);
		if (!fields.length) {
			fieldsWrap.appendChild(
				text("div", "wdStepDetailsFieldsEmpty", "(missing)"),
			);
		} else {
			fields.forEach(function (field) {
				const row = el("div", "wdStepDetailsFieldRow");
				const key =
					field && field.key != null ? String(field.key) : "(missing)";
				const typ =
					field && field.type != null ? String(field.type) : "(missing)";
				const req = field && field.required ? "required" : "optional";
				let defv = "(missing)";
				if (field && Object.prototype.hasOwnProperty.call(field, "default")) {
					defv = String(field.default);
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
