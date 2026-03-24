(function () {
	"use strict";

	const H = window.AM2EditorHTTP;
	if (!H || !H.requestJSON) return;

	/** @param {string} url @param {AM2JsonObject} body */
	function postJSON(url, body) {
		return H.requestJSON(url, {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: JSON.stringify(body || {}),
		});
	}

	/** @param {AM2JsonObject | undefined} definition */
	function sanitizeWizardDefinitionForWire(definition) {
		const payload = /** @type {AM2JsonObject} */ (
			JSON.parse(JSON.stringify(definition === undefined ? {} : definition))
		);
		delete payload._am2_ui;
		return payload;
	}

	window.AM2DSLEditorRegistryAPI = {
		getPrimitiveRegistry: function getPrimitiveRegistry() {
			return H.requestJSON("/import/ui/primitive-registry");
		},
		getWizardDefinition: function getWizardDefinition() {
			return H.requestJSON("/import/ui/wizard-definition");
		},
		validateWizardDefinition: function validateWizardDefinition(definition) {
			return postJSON("/import/ui/wizard-definition/validate", {
				definition: sanitizeWizardDefinitionForWire(definition),
			});
		},
		saveWizardDefinition: function saveWizardDefinition(definition) {
			return postJSON("/import/ui/wizard-definition", {
				definition: sanitizeWizardDefinitionForWire(definition),
			});
		},
		activateWizardDefinition: function activateWizardDefinition() {
			return H.requestJSON("/import/ui/wizard-definition/activate", {
				method: "POST",
			});
		},
		resetWizardDefinition: function resetWizardDefinition() {
			return H.requestJSON("/import/ui/wizard-definition/reset", {
				method: "POST",
			});
		},
		listWizardDefinitionHistory: function listWizardDefinitionHistory() {
			return H.requestJSON("/import/ui/wizard-definition/history");
		},
		rollbackWizardDefinition: function rollbackWizardDefinition(id) {
			return postJSON("/import/ui/wizard-definition/rollback", { id });
		},
	};
})();
