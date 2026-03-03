export {};

declare global {
	interface Window {
		AM2FlowEditor: any;
		AM2FlowEditorState: any; // ak používaš AM2FlowEditorState
		AM2UI: any;

		AM2WDDomIcons: any;
		AM2WDEdgesIntegrity: any;
		AM2WDStepDetailsLoader: any;

		AmpSettings: any;

		__AM_APP_LOADED__: any;
		__AM_UI_LOGS__: any;
		__AM_JS_ERRORS__: any;
		__AM_FETCH_CAPTURE_INSTALLED__: any;

		_amPushJsError: any; // podľa logu existuje toto meno
		// ak kód používa _amPushJSError, buď oprav kód na _amPushJsError, alebo sem pridaj aj alias:
		_amPushJSError?: any;

		__ph_last_enqueued_job_id: any;
		__ph_last_enqueued_mode: any;
	}

	// Ak sa to volá globálne bez window. (napr. startBookFlow())
	function startBookFlow(...args: any[]): any;
}
