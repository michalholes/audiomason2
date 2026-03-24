(() => {
	/** @type {Window} */
	var root = window;

	var modal = root.AM2FlowJSONModalState;
	if (!modal) {
		return;
	}

	/** @param {string} id */
	function $(id) {
		return document.getElementById(id);
	}

	/** @param {string} buttonId
	 * @param {AM2FlowJSONArtifact} artifact
	 */
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
