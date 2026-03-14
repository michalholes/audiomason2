(() => {
	var root = /** @type {any} */ (window);

	var modal = root.AM2FlowJSONModalState;
	if (!modal) {
		return;
	}

	function $(id) {
		return document.getElementById(id);
	}

	function bindOpen(buttonId, artifact) {
		var node = $(buttonId);
		if (!node || !node.addEventListener) {
			return;
		}
		node.addEventListener("click", () => {
			void modal.openModal(artifact);
		});
	}

	bindOpen("flowOpenWizardJson", "wizard");
	bindOpen("flowOpenConfigJson", "config");
})();
