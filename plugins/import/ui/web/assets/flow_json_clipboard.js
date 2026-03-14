(() => {
	var root = /** @type {any} */ (window);

	function copyTextExecCommand(payload) {
		return new Promise((resolve, reject) => {
			var ta = null;
			var ok = false;
			try {
				if (!document || !document.body || !document.createElement) {
					reject(new Error("clipboard unavailable"));
					return;
				}
				ta = document.createElement("textarea");
				ta.value = payload;
				ta.setAttribute("readonly", "true");
				ta.style.position = "absolute";
				ta.style.left = "-9999px";
				document.body.appendChild(ta);
				ta.select();
				ok = document.execCommand && document.execCommand("copy");
				document.body.removeChild(ta);
				ta = null;
				if (ok) {
					resolve(payload);
					return;
				}
				reject(new Error("execCommand(copy) returned false"));
			} catch (e) {
				if (ta) {
					try {
						document.body.removeChild(ta);
					} catch (removeErr) {
						console.error("Flow JSON copy cleanup failed:", removeErr);
					}
				}
				reject(e);
			}
		});
	}

	function copyText(text) {
		var payload = String(text || "");
		var nav = typeof navigator !== "undefined" ? navigator : null;
		if ((!nav || !nav.clipboard) && root && root.navigator) {
			nav = root.navigator;
		}
		if (nav && nav.clipboard && nav.clipboard.writeText) {
			return nav.clipboard.writeText(payload).then(
				() => payload,
				() => copyTextExecCommand(payload),
			);
		}
		return copyTextExecCommand(payload);
	}

	root.AM2FlowJSONClipboard = {
		copyText: copyText,
	};
})();
